from __future__ import annotations

import os
import re
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


PAPAGO_TRANSLATION_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"
PAPAGO_CLIENT_ID_ENV = ("NCP_PAPAGO_CLIENT_ID", "PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET_ENV = ("NCP_PAPAGO_CLIENT_SECRET", "PAPAGO_CLIENT_SECRET")

RESUME_TERM_REPLACEMENTS = {
    "self-introduction letter": "cover letter",
    "personal statement": "cover letter",
    "spec": "qualification",
    "specs": "qualifications",
    "career description": "professional experience",
    "contest exhibition": "competition",
    "external activity": "extracurricular activity",
    "club activities": "student club activities",
    "certificate": "certification",
    "information processing engineer": "Engineer Information Processing",
    "SQL developer": "SQL Developer (SQLD)",
    "Computer Specialist in Spreadsheet & Database": "Computer Specialist in Spreadsheet and Database",
}

KOREAN_RESUME_TERMS = {
    "자기소개서": "cover letter",
    "자소서": "cover letter",
    "이력서": "resume",
    "레쥬메": "resume",
    "스펙": "qualifications",
    "경력기술서": "professional experience summary",
    "대외활동": "extracurricular activities",
    "공모전": "competition",
    "동아리": "student club",
    "정보처리기사": "Engineer Information Processing",
    "SQLD": "SQL Developer (SQLD)",
    "에스큐엘디": "SQL Developer (SQLD)",
    "토익": "TOEIC",
    "오픽": "OPIc",
}


class PapagoTranslationError(RuntimeError):
    """Raised when NCP Papago returns an error response."""


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _resolve_credentials(
    client_id: str | None = None,
    client_secret: str | None = None,
) -> tuple[str, str]:
    resolved_id = client_id or _first_env(PAPAGO_CLIENT_ID_ENV)
    resolved_secret = client_secret or _first_env(PAPAGO_CLIENT_SECRET_ENV)

    if not resolved_id:
        raise ValueError(
            "Papago Client ID is required. Set NCP_PAPAGO_CLIENT_ID "
            "or pass client_id."
        )
    if not resolved_secret:
        raise ValueError(
            "Papago Client Secret is required. Set NCP_PAPAGO_CLIENT_SECRET "
            "or pass client_secret."
        )
    return resolved_id, resolved_secret


def _mask_resume_terms(text: str) -> str:
    """Keep common resume/JD terms in standard English during translation."""

    masked = text
    for korean, english in KOREAN_RESUME_TERMS.items():
        masked = re.sub(
            re.escape(korean),
            f'<span translate="no">{english}</span>',
            masked,
            flags=re.I,
        )
    return masked


def normalize_resume_english(text: str) -> str:
    """Normalize common awkward Papago outputs into resume-friendly wording."""

    normalized = text
    for source, target in RESUME_TERM_REPLACEMENTS.items():
        normalized = re.sub(re.escape(source), target, normalized, flags=re.I)
    normalized = re.sub(r"\bresume\b", "resume", normalized, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def translate_text(
    text: str,
    *,
    source: str = "ko",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    honorific: bool | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Call NCP Papago Text Translation and return the raw JSON response."""

    if not text or not text.strip():
        raise ValueError("text must not be empty.")

    resolved_id, resolved_secret = _resolve_credentials(client_id, client_secret)
    headers = {
        "X-NCP-APIGW-API-KEY-ID": resolved_id,
        "X-NCP-APIGW-API-KEY": resolved_secret,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "source": source,
        "target": target,
        "text": text,
    }
    if glossary_key:
        payload["glossaryKey"] = glossary_key
    if honorific is not None:
        payload["honorific"] = honorific

    response = requests.post(
        PAPAGO_TRANSLATION_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise PapagoTranslationError(
            f"Papago translation failed: {response.status_code} {response.text}"
        ) from exc
    return response.json()


def get_translated_text(papago_response: dict[str, Any]) -> str:
    """Extract translatedText from Papago response JSON."""

    return (
        papago_response.get("message", {})
        .get("result", {})
        .get("translatedText", "")
        .strip()
    )


def translate_to_resume_english(
    korean_text: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    use_term_masking: bool = True,
) -> str:
    """
    Translate Korean spec/cover-letter text into resume-friendly English.

    For stronger domain terminology, create a Papago Glossary in NCP and pass
    its glossary_key.
    """

    source_text = _mask_resume_terms(korean_text) if use_term_masking else korean_text
    response = translate_text(
        source_text,
        source="ko",
        target="en",
        client_id=client_id,
        client_secret=client_secret,
        glossary_key=glossary_key,
    )
    translated = get_translated_text(response)
    return normalize_resume_english(translated)


def translate_spec_text(
    text: str,
    *,
    target: str = "en",
    source: str = "ko",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
) -> str:
    """Translate generic SpecGap text and return only the translated string."""

    response = translate_text(
        text,
        source=source,
        target=target,
        client_id=client_id,
        client_secret=client_secret,
        glossary_key=glossary_key,
    )
    translated = get_translated_text(response)
    if target == "en":
        return normalize_resume_english(translated)
    return translated

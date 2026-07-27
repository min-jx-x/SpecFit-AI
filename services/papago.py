from __future__ import annotations

import os
import re
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


PAPAGO_TRANSLATION_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"
PAPAGO_CLIENT_ID_ENV = ("NCP_PAPAGO_CLIENT_ID", "PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET_ENV = (
    "NCP_PAPAGO_CLIENT_SECRET",
    "PAPAGO_CLIENT_SECRET",
)
PAPAGO_GLOSSARY_KEY_ENV = (
    "NCP_PAPAGO_GLOSSARY_KEY",
    "PAPAGO_GLOSSARY_KEY",
)

TRANSLATABLE_REPORT_KEYS = {
    "summary",
    "item",
    "category",
    "position",
    "user_value",
    "passed_avg",
    "gap",
    "priority",
    "comment",
    "analysis",
    "suggestion",
    "action",
    "reason",
    "expected_effect",
    "encouragement",
    "cover_letter",
}

BATCH_MARKER = "[[SPECGAP_FIELD_{index:04d}]]"
DEFAULT_BATCH_CHAR_LIMIT = 3000

RESUME_TERM_REPLACEMENTS = {
    "self-introduction letter": "cover letter",
    "personal statement": "cover letter",
    "career description": "professional experience",
    "contest exhibition": "competition",
    "external activity": "extracurricular activity",
    "club activities": "student club activities",
    "certificate": "certification",
    "information processing engineer": "Engineer Information Processing",
    "SQL developer": "SQL Developer (SQLD)",
    "Computer Specialist in Spreadsheet & Database": (
        "Computer Specialist in Spreadsheet and Database"
    ),
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
            "Papago Client Secret is required. "
            "Set NCP_PAPAGO_CLIENT_SECRET or pass client_secret."
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


def _contains_korean(text: str) -> bool:
    """Return whether text contains at least one Hangul syllable."""

    return bool(re.search(r"[가-힣]", text))


def normalize_resume_english(text: str) -> str:
    """Normalize common awkward Papago outputs into resume-friendly wording."""

    normalized = text
    for source, target in RESUME_TERM_REPLACEMENTS.items():
        normalized = re.sub(re.escape(source), target, normalized, flags=re.I)
    normalized = re.sub(
        r"\bspecifications?\b",
        "qualifications",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bspecs\b",
        "qualifications",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bspec\b",
        "qualification",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\bresume\b", "resume", normalized, flags=re.I)
    normalized = re.sub(
        r'</?span(?:\s+translate="no")?>',
        "",
        normalized,
        flags=re.I,
    )
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

    resolved_id, resolved_secret = _resolve_credentials(
        client_id,
        client_secret,
    )
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
    resolved_glossary_key = (
        glossary_key or _first_env(PAPAGO_GLOSSARY_KEY_ENV)
    )
    if resolved_glossary_key:
        payload["glossaryKey"] = resolved_glossary_key
    if honorific is not None:
        payload["honorific"] = honorific

    try:
        response = requests.post(
            PAPAGO_TRANSLATION_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_body = ""
        if exc.response is not None:
            response_body = exc.response.text
        raise PapagoTranslationError(
            f"Papago translation request failed: {response_body or exc}"
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise PapagoTranslationError(
            "Papago returned a non-JSON response."
        ) from exc


def get_translated_text(papago_response: dict[str, Any]) -> str:
    """Extract translatedText from Papago response JSON."""

    translated = (
        papago_response.get("message", {})
        .get("result", {})
        .get("translatedText", "")
        .strip()
    )
    if not translated:
        raise PapagoTranslationError(
            "Papago response does not contain translatedText."
        )
    return translated


def translate_to_resume_english(
    korean_text: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    use_term_masking: bool = True,
) -> str:
    """Translate Korean text into resume-friendly English."""

    if not _contains_korean(korean_text):
        return normalize_resume_english(korean_text)

    source_text = (
        _mask_resume_terms(korean_text)
        if use_term_masking
        else korean_text
    )
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


def _make_batches(
    texts: list[str],
    max_chars: int = DEFAULT_BATCH_CHAR_LIMIT,
) -> list[list[str]]:
    """Split text values into batches below the configured character limit."""

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")

    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_length = 0

    for text in texts:
        marker_length = len(BATCH_MARKER.format(index=len(current_batch)))
        estimated_length = len(text) + marker_length + 2

        if current_batch and current_length + estimated_length > max_chars:
            batches.append(current_batch)
            current_batch = []
            current_length = 0
            marker_length = len(BATCH_MARKER.format(index=0))
            estimated_length = len(text) + marker_length + 2

        current_batch.append(text)
        current_length += estimated_length

    if current_batch:
        batches.append(current_batch)

    return batches


def _translate_text_batch(
    texts: list[str],
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
) -> list[str]:
    """Translate multiple values in one Papago request using stable markers."""

    if not texts:
        return []

    combined_text = "\n".join(
        f"{BATCH_MARKER.format(index=index)}\n{text}"
        for index, text in enumerate(texts)
    )
    translated = translate_to_resume_english(
        combined_text,
        client_id=client_id,
        client_secret=client_secret,
        glossary_key=glossary_key,
    )

    marker_pattern = re.compile(r"\[\[SPECGAP_FIELD_(\d{4})\]\]\s*")
    marker_matches = list(marker_pattern.finditer(translated))
    if len(marker_matches) != len(texts):
        raise PapagoTranslationError(
            "Papago batch markers were not preserved."
        )

    results = [""] * len(texts)
    seen_indexes: set[int] = set()

    for match_position, match in enumerate(marker_matches):
        field_index = int(match.group(1))
        if field_index >= len(texts) or field_index in seen_indexes:
            raise PapagoTranslationError(
                "Papago returned invalid batch marker indexes."
            )

        start = match.end()
        end = (
            marker_matches[match_position + 1].start()
            if match_position + 1 < len(marker_matches)
            else len(translated)
        )
        field_text = translated[start:end].strip()
        if not field_text:
            raise PapagoTranslationError(
                f"Papago returned an empty batch field: {field_index}"
            )

        results[field_index] = field_text
        seen_indexes.add(field_index)

    if len(seen_indexes) != len(texts):
        raise PapagoTranslationError(
            "Papago batch response is incomplete."
        )
    return results


def _collect_translatable_texts(
    value: Any,
    parent_key: str | None = None,
) -> list[str]:
    """Collect Korean report values that should be translated."""

    collected: list[str] = []

    if isinstance(value, dict):
        for key, child in value.items():
            collected.extend(_collect_translatable_texts(child, key))
    elif isinstance(value, list):
        for child in value:
            collected.extend(_collect_translatable_texts(child, parent_key))
    elif (
        isinstance(value, str)
        and parent_key in TRANSLATABLE_REPORT_KEYS
        and value.strip()
        and _contains_korean(value)
    ):
        collected.append(value)

    return collected


def _apply_translations(
    value: Any,
    translations: dict[str, str],
    parent_key: str | None = None,
) -> Any:
    """Return a new report value with translated strings applied."""

    if isinstance(value, dict):
        return {
            key: _apply_translations(child, translations, key)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _apply_translations(child, translations, parent_key)
            for child in value
        ]
    if (
        isinstance(value, str)
        and parent_key in TRANSLATABLE_REPORT_KEYS
    ):
        return translations.get(value, value)
    return value


def translate_analysis_report(
    report: dict[str, Any],
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    max_batch_chars: int = DEFAULT_BATCH_CHAR_LIMIT,
) -> dict[str, Any]:
    """
    Translate a report in batches while preserving its original JSON shape.

    Duplicate values are translated once. If one batch fails or Papago changes
    its markers, only that batch falls back to the original Korean values.
    """

    if not isinstance(report, dict):
        raise ValueError("report must be a dictionary.")

    collected = _collect_translatable_texts(report)
    unique_texts = list(dict.fromkeys(collected))
    if not unique_texts:
        return report.copy()

    translations: dict[str, str] = {}
    for batch in _make_batches(unique_texts, max_batch_chars):
        try:
            translated_batch = _translate_text_batch(
                batch,
                client_id=client_id,
                client_secret=client_secret,
                glossary_key=glossary_key,
            )
        except (PapagoTranslationError, ValueError):
            # Preserve the Korean source values for only the failed batch.
            continue

        translations.update(zip(batch, translated_batch))

    return _apply_translations(report, translations)
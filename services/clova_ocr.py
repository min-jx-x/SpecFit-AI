from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


OCR_INVOKE_URL_ENV = ("NCP_CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_INVOKE_URL")
OCR_SECRET_ENV = ("NCP_CLOVA_OCR_SECRET", "CLOVA_OCR_SECRET")
OCR_FILE_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"}
TEXT_FILE_SUFFIXES = {".txt"}
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")

DEFAULT_TECH_KEYWORDS = {
    "backend": [
        "Java", "Spring", "Spring Boot", "Python", "FastAPI", "Django",
        "Node.js", "Express", "REST API", "GraphQL", "Docker", "Kubernetes",
        "AWS", "NCP", "GCP", "Azure", "Linux", "MySQL", "PostgreSQL",
        "MongoDB", "Redis", "Kafka", "RabbitMQ", "Git", "GitHub Actions",
        "CI/CD", "SQL",
    ],
    "data": [
        "Python", "SQL", "Pandas", "NumPy", "scikit-learn", "PyTorch",
        "TensorFlow", "LLM", "RAG", "ChromaDB", "LangChain", "Airflow", "Spark",
    ],
    "certificate": [
        "SQLD", "ADsP", "정보처리기사", "정보 처리 기사", "정처기",
        "정보보안기사", "정보 보안 기사", "정보기", "AWS SAA",
        "AWS Solutions Architect", "CKA", "CKAD", "컴퓨터활용능력",
        "컴퓨터 활용 능력", "컴활",
    ],
    "language": [
        "TOEIC", "TOEFL", "OPIc", "OPIC", "IELTS", "TEPS",
        "TOEIC Speaking", "토익", "토플", "오픽",
    ],
}


class ClovaOcrError(RuntimeError):
    """Raised when CLOVA OCR returns an error response."""


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _resolve_credentials(
    invoke_url: str | None = None,
    secret_key: str | None = None,
) -> tuple[str, str]:
    resolved_url = invoke_url or _first_env(OCR_INVOKE_URL_ENV)
    resolved_secret = secret_key or _first_env(OCR_SECRET_ENV)

    if not resolved_url:
        raise ValueError(
            "CLOVA OCR invoke URL is required. Set NCP_CLOVA_OCR_INVOKE_URL "
            "or pass invoke_url."
        )
    if not resolved_secret:
        raise ValueError(
            "CLOVA OCR secret key is required. Set NCP_CLOVA_OCR_SECRET "
            "or pass secret_key."
        )
    return resolved_url, resolved_secret


def _image_format(image_path: str | Path) -> str:
    suffix = Path(image_path).suffix.lower().lstrip(".")
    if suffix == "jpeg":
        return "jpg"
    if suffix in {"jpg", "png", "pdf", "tif", "tiff"}:
        return suffix

    guessed_type, _ = mimetypes.guess_type(str(image_path))
    if guessed_type and "/" in guessed_type:
        return guessed_type.split("/", 1)[1].replace("jpeg", "jpg")
    raise ValueError(f"Unsupported image extension: {image_path}")


def _encode_image(image_path: str | Path) -> str:
    with Path(image_path).open("rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _read_text_file(text_path: str | Path) -> str:
    path = Path(text_path)
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Unable to decode text file: {text_path}. "
        f"Supported encodings: {', '.join(TEXT_ENCODINGS)}"
    )


def build_ocr_payload(
    *,
    image_path: str | Path | None = None,
    image_url: str | None = None,
    lang: str = "ko",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build a CLOVA OCR V2 request body for a local image or public image URL."""

    if bool(image_path) == bool(image_url):
        raise ValueError("Pass exactly one of image_path or image_url.")

    image_name = Path(image_path).stem if image_path else "remote-image"
    image_format = _image_format(image_path) if image_path else "jpg"
    image: dict[str, Any] = {"format": image_format, "name": image_name}

    if image_path:
        image["data"] = _encode_image(image_path)
    else:
        image["url"] = image_url

    return {
        "version": "V2",
        "requestId": request_id or str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": lang,
        "images": [image],
    }


def request_ocr(
    *,
    image_path: str | Path | None = None,
    image_url: str | None = None,
    invoke_url: str | None = None,
    secret_key: str | None = None,
    lang: str = "ko",
    timeout: int = 30,
) -> dict[str, Any]:
    """Call NCP CLOVA OCR and return the raw JSON response."""

    resolved_url, resolved_secret = _resolve_credentials(invoke_url, secret_key)
    payload = build_ocr_payload(image_path=image_path, image_url=image_url, lang=lang)
    headers = {
        "Content-Type": "application/json",
        "X-OCR-SECRET": resolved_secret,
    }
    response = requests.post(
        resolved_url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ClovaOcrError(
            f"CLOVA OCR request failed: {response.status_code} {response.text}"
        ) from exc
    return response.json()


STRUCTURED_FIELD_LABELS = (
    "학점",
    "토익",
    "토익스피킹",
    "OPIC",
    "자격증",
    "인턴",
    "수상내역",
    "교내 사회 봉사",
    "직무",
)


def extract_structured_fields(ocr_response: dict[str, Any]) -> dict[str, str]:
    """Parse named fields from CLOVA OCR custom-template JSON."""

    field_map: dict[str, str] = {}
    for image in ocr_response.get("images", []):
        for field in image.get("fields", []):
            name = (field.get("name") or "").strip()
            value = (field.get("inferText") or "").strip()
            if name and value:
                field_map[name] = value
    return field_map


def _parse_numeric_score(raw_value: str) -> int | None:
    match = re.search(r"(\d{2,3})", raw_value)
    if match:
        return int(match.group(1))
    return None


def parse_structured_spec(
    field_map: dict[str, str],
    fallback_text: str = "",
) -> dict[str, Any]:
    """Build parsed spec data from CLOVA custom-template field names."""

    scores: dict[str, int | str] = {}
    score_field_map = {
        "toeic": "토익",
        "toefl": "토플",
        "teps": "텝스",
        "toeic_speaking": "토익스피킹",
    }
    for score_key, field_name in score_field_map.items():
        raw_value = field_map.get(field_name, "")
        if raw_value:
            parsed = _parse_numeric_score(raw_value)
            if parsed is not None:
                scores[score_key] = parsed

    opic_value = field_map.get("OPIC", "").strip()
    if opic_value:
        scores["opic"] = opic_value

    cert_raw = field_map.get("자격증", "").strip()
    certifications = [
        part.strip()
        for part in re.split(r"[,/|·\n]", cert_raw)
        if part.strip()
    ] if cert_raw else []

    lines = []
    for label in STRUCTURED_FIELD_LABELS:
        value = field_map.get(label)
        if value:
            lines.append(f"- {label}: {value}")

    structured_text = "\n".join(lines).strip()
    text = structured_text or fallback_text

    keywords = extract_keywords(text)
    if not keywords.get("certificate") and certifications:
        keywords["certificate"] = sorted(set(certifications), key=str.lower)

    return {
        "text": text,
        "lines": [line for line in lines if line],
        "keywords": keywords,
        "scores": scores,
        "certifications": certifications or parse_certifications(text),
        "structured_fields": field_map,
    }


def extract_lines(ocr_response: dict[str, Any]) -> list[str]:
    """Extract line-like text from CLOVA OCR response fields."""

    lines: list[str] = []
    current_line: list[str] = []

    for image in ocr_response.get("images", []):
        for field in image.get("fields", []):
            text = (field.get("inferText") or "").strip()
            if not text:
                continue
            current_line.append(text)
            if field.get("lineBreak"):
                lines.append(" ".join(current_line).strip())
                current_line = []

    if current_line:
        lines.append(" ".join(current_line).strip())
    if lines:
        return lines

    return [
        (field.get("inferText") or "").strip()
        for image in ocr_response.get("images", [])
        for field in image.get("fields", [])
        if (field.get("inferText") or "").strip()
    ]


def extract_text(ocr_response: dict[str, Any]) -> str:
    """Return OCR text joined by newline."""

    return "\n".join(extract_lines(ocr_response))


def extract_keywords(
    text: str,
    keyword_groups: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Find known spec/JD keywords in OCR text."""

    groups = keyword_groups or DEFAULT_TECH_KEYWORDS
    normalized_text = re.sub(r"\s+", " ", text)
    found: dict[str, list[str]] = {}

    for group, keywords in groups.items():
        matches: list[str] = []
        for keyword in keywords:
            escaped = re.escape(keyword)
            if re.search(
                rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])",
                normalized_text,
                re.I,
            ):
                matches.append(keyword)
        if matches:
            found[group] = sorted(set(matches), key=str.lower)
    return found


def parse_scores(text: str) -> dict[str, int | str]:
    """Parse common language-test scores from OCR text."""

    patterns = {
        "toeic": r"(?:TOEIC|토익)\D{0,20}([0-9]{3})",
        "toefl": r"(?:TOEFL|토플)\D{0,20}([0-9]{2,3})",
        "teps": r"(?:TEPS|텝스)\D{0,20}([0-9]{3})",
        "opic": r"(?:OPIc|OPIC|오픽)\D{0,20}(AL|IH|IM3|IM2|IM1|IL)",
    }
    scores: dict[str, int | str] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            value = match.group(1)
            scores[name] = int(value) if value.isdigit() else value
    return scores


def parse_certifications(text: str) -> list[str]:
    """Parse common certificates from OCR text."""

    certifications = []
    for keyword in DEFAULT_TECH_KEYWORDS["certificate"]:
        if re.search(re.escape(keyword), text, re.I):
            certifications.append(keyword)
    return sorted(set(certifications), key=str.lower)


def parse_ocr_response(ocr_response: dict[str, Any]) -> dict[str, Any]:
    """Create a SpecGap-friendly parsed result from raw CLOVA OCR output."""

    fallback_text = extract_text(ocr_response)
    field_map = extract_structured_fields(ocr_response)

    if field_map:
        parsed = parse_structured_spec(field_map, fallback_text=fallback_text)
        return {
            **parsed,
            "source_type": "ocr_template",
            "raw": ocr_response,
        }

    return {
        "text": fallback_text,
        "lines": extract_lines(ocr_response),
        "keywords": extract_keywords(fallback_text),
        "scores": parse_scores(fallback_text),
        "certifications": parse_certifications(fallback_text),
        "structured_fields": {},
        "source_type": "ocr",
        "raw": ocr_response,
    }


def parse_ocr_json_content(ocr_response: dict[str, Any]) -> dict[str, Any]:
    """Parse a saved CLOVA OCR JSON response file."""

    if not ocr_response.get("images"):
        raise ValueError("OCR JSON must contain an 'images' array.")
    return parse_ocr_response(ocr_response)


def parse_text_content(text: str) -> dict[str, Any]:
    """Parse plain text using the same spec rules as OCR output."""

    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("Text file must not be empty.")

    stripped = normalized_text.lstrip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(normalized_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("images"):
            return parse_ocr_json_content(payload)

    return {
        "text": normalized_text,
        "lines": [
            line.strip()
            for line in normalized_text.splitlines()
            if line.strip()
        ],
        "keywords": extract_keywords(normalized_text),
        "scores": parse_scores(normalized_text),
        "certifications": parse_certifications(normalized_text),
        "structured_fields": {},
        "source_type": "text",
        "raw": {},
    }


def extract_spec_from_image(
    image_path: str | Path,
    *,
    invoke_url: str | None = None,
    secret_key: str | None = None,
    lang: str = "ko",
) -> dict[str, Any]:
    """OCR a local file and return parsed text, keywords, scores, and certificates."""

    response = request_ocr(
        image_path=image_path,
        invoke_url=invoke_url,
        secret_key=secret_key,
        lang=lang,
    )
    return parse_ocr_response(response)


def _read_json_file(json_path: str | Path) -> dict[str, Any]:
    path = Path(json_path)
    for encoding in TEXT_ENCODINGS:
        try:
            return json.loads(path.read_text(encoding=encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(
        f"Unable to decode OCR JSON file: {json_path}. "
        f"Supported encodings: {', '.join(TEXT_ENCODINGS)}"
    )


def extract_spec_from_file(
    file_path: str | Path,
    *,
    invoke_url: str | None = None,
    secret_key: str | None = None,
    lang: str = "ko",
) -> dict[str, Any]:
    """Extract specs from TXT directly or OCR-supported files through CLOVA OCR."""

    suffix = Path(file_path).suffix.lower()
    if suffix == ".json":
        return parse_ocr_json_content(_read_json_file(file_path))
    if suffix in TEXT_FILE_SUFFIXES:
        return parse_text_content(_read_text_file(file_path))
    if suffix in OCR_FILE_SUFFIXES:
        return extract_spec_from_image(
            file_path,
            invoke_url=invoke_url,
            secret_key=secret_key,
            lang=lang,
        )
    supported = ", ".join(sorted(TEXT_FILE_SUFFIXES | OCR_FILE_SUFFIXES))
    raise ValueError(
        f"Unsupported file extension: {suffix or '(none)'}. "
        f"Supported extensions: {supported}"
    )


def extract_text_from_image(
    image_path: str | Path,
    *,
    invoke_url: str | None = None,
    secret_key: str | None = None,
    lang: str = "ko",
) -> str:
    """OCR a local file and return only the extracted text."""

    return extract_spec_from_image(
        image_path,
        invoke_url=invoke_url,
        secret_key=secret_key,
        lang=lang,
    )["text"]


def extract_text_from_file(
    file_path: str | Path,
    *,
    invoke_url: str | None = None,
    secret_key: str | None = None,
    lang: str = "ko",
) -> str:
    """Return text from TXT directly or an OCR-supported file."""

    return extract_spec_from_file(
        file_path,
        invoke_url=invoke_url,
        secret_key=secret_key,
        lang=lang,
    )["text"]
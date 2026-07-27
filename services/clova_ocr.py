from __future__ import annotations

import base64
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

DEFAULT_TECH_KEYWORDS = {
    "backend": [
        "Java",
        "Spring",
        "Spring Boot",
        "Python",
        "FastAPI",
        "Django",
        "Node.js",
        "Express",
        "REST API",
        "GraphQL",
        "Docker",
        "Kubernetes",
        "AWS",
        "NCP",
        "GCP",
        "Azure",
        "Linux",
        "MySQL",
        "PostgreSQL",
        "MongoDB",
        "Redis",
        "Kafka",
        "RabbitMQ",
        "Git",
        "GitHub Actions",
        "CI/CD",
        "SQL",
    ],
    "data": [
        "Python",
        "SQL",
        "Pandas",
        "NumPy",
        "scikit-learn",
        "PyTorch",
        "TensorFlow",
        "LLM",
        "RAG",
        "ChromaDB",
        "LangChain",
        "Airflow",
        "Spark",
    ],
    "certificate": [
        "SQLD",
        "ADsP",
        "정보처리기사",
        "정보 처리 기사",
        "정처기",
        "정보보안기사",
        "정보 보안 기사",
        "정보기",
        "AWS SAA",
        "AWS Solutions Architect",
        "CKA",
        "CKAD",
        "컴퓨터활용능력",
        "컴퓨터 활용 능력",
        "컴활",
    ],
    "language": [
        "TOEIC",
        "TOEFL",
        "OPIc",
        "OPIC",
        "IELTS",
        "TEPS",
        "TOEIC Speaking",
        "토익",
        "토플",
        "오픽",
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
    image: dict[str, Any] = {
        "format": image_format,
        "name": image_name,
    }

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

    words = [
        (field.get("inferText") or "").strip()
        for image in ocr_response.get("images", [])
        for field in image.get("fields", [])
        if (field.get("inferText") or "").strip()
    ]
    return words


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
            if re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", normalized_text, re.I):
                matches.append(keyword)
        if matches:
            found[group] = sorted(set(matches), key=str.lower)

    return found


def parse_scores(text: str) -> dict[str, int]:
    """Parse common language-test scores from OCR text."""

    patterns = {
        "toeic": r"(?:TOEIC|토익)\D{0,20}([0-9]{3})",
        "toefl": r"(?:TOEFL|토플)\D{0,20}([0-9]{2,3})",
        "teps": r"(?:TEPS|텝스)\D{0,20}([0-9]{3})",
    }
    scores: dict[str, int] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            scores[name] = int(match.group(1))
    return scores


def parse_certifications(text: str) -> list[str]:
    """Parse common certificates from OCR text."""

    keywords = DEFAULT_TECH_KEYWORDS["certificate"]
    certifications = []
    for keyword in keywords:
        if re.search(re.escape(keyword), text, re.I):
            certifications.append(keyword)
    return sorted(set(certifications), key=str.lower)


def parse_ocr_response(ocr_response: dict[str, Any]) -> dict[str, Any]:
    """Create a SpecGap-friendly parsed result from raw CLOVA OCR output."""

    text = extract_text(ocr_response)
    return {
        "text": text,
        "lines": extract_lines(ocr_response),
        "keywords": extract_keywords(text),
        "scores": parse_scores(text),
        "certifications": parse_certifications(text),
        "raw": ocr_response,
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

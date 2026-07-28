from __future__ import annotations

import base64
import io
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from PIL import Image


load_dotenv()


TEXT_TRANSLATION_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"
DOC_TRANSLATE_URL = "https://papago.apigw.ntruss.com/doc-trans/v1/translate"
DOC_STATUS_URL = "https://papago.apigw.ntruss.com/doc-trans/v1/status"
DOC_DOWNLOAD_URL = "https://papago.apigw.ntruss.com/doc-trans/v1/download"
IMAGE_TRANSLATION_URL = (
    "https://papago.apigw.ntruss.com/image-to-image/v1/translate"
)

PAPAGO_CLIENT_ID_ENV = ("NCP_PAPAGO_CLIENT_ID", "PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET_ENV = (
    "NCP_PAPAGO_CLIENT_SECRET",
    "PAPAGO_CLIENT_SECRET",
)
PAPAGO_GLOSSARY_KEY_ENV = (
    "NCP_PAPAGO_GLOSSARY_KEY",
    "PAPAGO_GLOSSARY_KEY",
)

TEXT_FILE_SUFFIXES = {".txt"}
DOCUMENT_FILE_SUFFIXES = {".docx", ".pptx", ".xlsx", ".pdf", ".hwp"}
IMAGE_FILE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
SUPPORTED_FILE_SUFFIXES = (
    TEXT_FILE_SUFFIXES | DOCUMENT_FILE_SUFFIXES | IMAGE_FILE_SUFFIXES
)

TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
TEXT_CHUNK_LIMIT = 3000
TEXT_TRANSLATION_MAX_ATTEMPTS = 3
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_FILE_BYTES = 100 * 1024 * 1024
MAX_IMAGE_FILE_BYTES = 20 * 1024 * 1024


class PapagoFileTranslationError(RuntimeError):
    """Raised when Papago cannot translate or return an uploaded file."""


@dataclass(frozen=True)
class TranslatedFile:
    content: bytes
    filename: str
    media_type: str
    source_type: str


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
            "NCP_PAPAGO_CLIENT_ID 또는 PAPAGO_CLIENT_ID가 필요합니다."
        )
    if not resolved_secret:
        raise ValueError(
            "NCP_PAPAGO_CLIENT_SECRET 또는 PAPAGO_CLIENT_SECRET이 필요합니다."
        )
    return resolved_id, resolved_secret


def _auth_headers(
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict[str, str]:
    resolved_id, resolved_secret = _resolve_credentials(
        client_id,
        client_secret,
    )
    return {
        "X-NCP-APIGW-API-KEY-ID": resolved_id,
        "X-NCP-APIGW-API-KEY": resolved_secret,
    }


def _response_error(response: requests.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        body = response.text[:1000] if response.text else ""
        raise PapagoFileTranslationError(
            f"{action} 실패: HTTP {response.status_code} {body}"
        ) from exc


def _response_json(
    response: requests.Response,
    action: str,
) -> dict[str, Any]:
    _response_error(response, action)
    try:
        payload = response.json()
    except ValueError as exc:
        raise PapagoFileTranslationError(
            f"{action} 응답이 JSON 형식이 아닙니다."
        ) from exc
    if not isinstance(payload, dict):
        raise PapagoFileTranslationError(
            f"{action} 응답 형식이 올바르지 않습니다."
        )
    return payload


def _translated_filename(filename: str, target: str) -> str:
    safe_name = Path(filename).name
    path = Path(safe_name)
    return f"{path.stem}_{target}{path.suffix.lower()}"


def _decode_text_file(content: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "TXT 파일 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949를 사용하세요."
    )


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_at = max(
            remaining.rfind(" ", 0, max_chars),
            remaining.rfind(".", 0, max_chars),
            remaining.rfind(",", 0, max_chars),
        )
        if split_at < max_chars // 2:
            split_at = max_chars
        else:
            split_at += 1

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    return chunks


def translate_text(
    text: str,
    *,
    source: str = "auto",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    timeout: int = 30,
) -> str:
    """Translate one text chunk and return only translatedText."""

    if not text or not text.strip():
        return text

    headers = {
        **_auth_headers(client_id, client_secret),
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "source": source,
        "target": target,
        "text": text,
    }
    resolved_glossary = glossary_key or _first_env(PAPAGO_GLOSSARY_KEY_ENV)
    if resolved_glossary:
        payload["glossaryKey"] = resolved_glossary

    response: requests.Response | None = None
    for attempt in range(TEXT_TRANSLATION_MAX_ATTEMPTS):
        try:
            response = requests.post(
                TEXT_TRANSLATION_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt == TEXT_TRANSLATION_MAX_ATTEMPTS - 1:
                raise PapagoFileTranslationError(
                    f"Papago TXT 번역 네트워크 오류: {exc}"
                ) from exc
            time.sleep(2**attempt)
            continue

        if response.status_code != 429 and response.status_code < 500:
            break
        if attempt < TEXT_TRANSLATION_MAX_ATTEMPTS - 1:
            time.sleep(2**attempt)

    if response is None:
        raise PapagoFileTranslationError(
            "Papago TXT 번역 응답을 받지 못했습니다."
        )

    result = _response_json(response, "Papago TXT 번역")
    translated = (
        result.get("message", {})
        .get("result", {})
        .get("translatedText", "")
    )
    if not isinstance(translated, str) or not translated.strip():
        raise PapagoFileTranslationError(
            "Papago TXT 번역 응답에 translatedText가 없습니다."
        )
    return translated


def translate_txt_file(
    content: bytes,
    filename: str,
    *,
    source: str = "auto",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
) -> TranslatedFile:
    """Translate TXT while preserving the original number of lines."""

    if len(content) > MAX_TEXT_FILE_BYTES:
        raise ValueError("TXT 파일은 5MB 이하여야 합니다.")

    source_text = _decode_text_file(content)
    if not source_text.strip():
        raise ValueError("빈 TXT 파일은 번역할 수 없습니다.")

    translated_lines: list[str] = []
    effective_source = "ko" if source == "auto" else source
    for raw_line in source_text.splitlines(keepends=True):
        body = raw_line.rstrip("\r\n")
        line_ending = raw_line[len(body):]

        if not body.strip():
            translated_lines.append(raw_line)
            continue

        # 날짜, 이메일, URL, 자격증명처럼 한국어가 없는 줄은
        # 자동 언어 감지 오류를 피하기 위해 원문 그대로 유지합니다.
        if source == "auto" and not re.search(r"[가-힣]", body):
            translated_lines.append(raw_line)
            continue

        translated_parts = [
            translate_text(
                chunk,
                source=effective_source,
                target=target,
                client_id=client_id,
                client_secret=client_secret,
                glossary_key=glossary_key,
            )
            for chunk in _split_long_text(body, TEXT_CHUNK_LIMIT)
        ]
        translated_lines.append(" ".join(translated_parts) + line_ending)

    translated_text = "".join(translated_lines)
    return TranslatedFile(
        content=translated_text.encode("utf-8"),
        filename=_translated_filename(filename, target),
        media_type="text/plain; charset=utf-8",
        source_type="text",
    )


def _request_document_translation(
    content: bytes,
    filename: str,
    *,
    source: str,
    target: str,
    client_id: str | None,
    client_secret: str | None,
    glossary_key: str | None,
    timeout: int,
) -> str:
    headers = _auth_headers(client_id, client_secret)
    data: dict[str, str] = {
        "source": source,
        "target": target,
    }
    resolved_glossary = glossary_key or _first_env(PAPAGO_GLOSSARY_KEY_ENV)
    if resolved_glossary:
        data["glossaryKey"] = resolved_glossary

    upload_name = Path(filename).name
    media_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
    files = {"file": (upload_name, content, media_type)}

    try:
        response = requests.post(
            DOC_TRANSLATE_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise PapagoFileTranslationError(
            f"Papago 문서 번역 요청 네트워크 오류: {exc}"
        ) from exc

    payload = _response_json(response, "Papago 문서 번역 요청")
    request_id = payload.get("data", {}).get("requestId")
    if not isinstance(request_id, str) or not request_id:
        raise PapagoFileTranslationError(
            "Papago 문서 번역 응답에 requestId가 없습니다."
        )
    return request_id


def _wait_for_document(
    request_id: str,
    *,
    client_id: str | None,
    client_secret: str | None,
    wait_timeout: int,
    poll_interval: float,
) -> None:
    headers = _auth_headers(client_id, client_secret)
    deadline = time.monotonic() + wait_timeout

    while time.monotonic() < deadline:
        try:
            response = requests.get(
                DOC_STATUS_URL,
                headers=headers,
                params={"requestId": request_id},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise PapagoFileTranslationError(
                f"Papago 문서 상태 확인 네트워크 오류: {exc}"
            ) from exc

        payload = _response_json(response, "Papago 문서 상태 확인")
        data = payload.get("data", {})
        status = data.get("status")

        if status == "COMPLETE":
            return
        if status == "FAILED":
            raise PapagoFileTranslationError(
                "Papago 문서 번역 실패: "
                f"{data.get('errCode', '')} {data.get('errMsg', '')}".strip()
            )
        if status not in {"WAITING", "PROGRESS"}:
            raise PapagoFileTranslationError(
                f"알 수 없는 Papago 문서 번역 상태입니다: {status}"
            )

        time.sleep(poll_interval)

    raise PapagoFileTranslationError(
        f"Papago 문서 번역이 {wait_timeout}초 안에 완료되지 않았습니다."
    )


def _download_document(
    request_id: str,
    *,
    client_id: str | None,
    client_secret: str | None,
) -> tuple[bytes, str]:
    headers = _auth_headers(client_id, client_secret)
    try:
        response = requests.get(
            DOC_DOWNLOAD_URL,
            headers=headers,
            params={"requestId": request_id},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise PapagoFileTranslationError(
            f"Papago 문서 다운로드 네트워크 오류: {exc}"
        ) from exc

    _response_error(response, "Papago 문서 다운로드")
    if not response.content:
        raise PapagoFileTranslationError(
            "Papago 문서 다운로드 결과가 비어 있습니다."
        )
    media_type = (
        response.headers.get("Content-Type")
        or "application/octet-stream"
    ).split(";", 1)[0]
    return response.content, media_type


def translate_document_file(
    content: bytes,
    filename: str,
    *,
    source: str = "auto",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
    request_timeout: int = 60,
    wait_timeout: int = 300,
    poll_interval: float = 2.0,
) -> TranslatedFile:
    """Translate Office/PDF/HWP and return the downloaded file bytes."""

    if len(content) > MAX_DOCUMENT_FILE_BYTES:
        raise ValueError("문서 파일은 100MB 이하여야 합니다.")

    request_id = _request_document_translation(
        content,
        filename,
        source=source,
        target=target,
        client_id=client_id,
        client_secret=client_secret,
        glossary_key=glossary_key,
        timeout=request_timeout,
    )
    _wait_for_document(
        request_id,
        client_id=client_id,
        client_secret=client_secret,
        wait_timeout=wait_timeout,
        poll_interval=poll_interval,
    )
    translated_content, response_media_type = _download_document(
        request_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    output_name = _translated_filename(filename, target)
    output_media_type = (
        mimetypes.guess_type(output_name)[0]
        or response_media_type
        or "application/octet-stream"
    )
    return TranslatedFile(
        content=translated_content,
        filename=output_name,
        media_type=output_media_type,
        source_type="document",
    )


def _convert_image_to_original_suffix(
    rendered_image: bytes,
    suffix: str,
) -> bytes:
    output = io.BytesIO()
    target_format = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }[suffix]

    try:
        with Image.open(io.BytesIO(rendered_image)) as image:
            if target_format == "JPEG" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(output, format=target_format)
    except Exception as exc:
        raise PapagoFileTranslationError(
            "번역 이미지 결과를 원본 확장자로 변환하지 못했습니다."
        ) from exc
    return output.getvalue()


def translate_image_file(
    content: bytes,
    filename: str,
    *,
    source: str = "auto",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout: int = 120,
) -> TranslatedFile:
    """Translate image text and return the rendered translated image."""

    if len(content) > MAX_IMAGE_FILE_BYTES:
        raise ValueError("이미지 파일은 20MB 이하여야 합니다.")

    suffix = Path(filename).suffix.lower()
    upload_suffix = ".tiff" if suffix == ".tif" else suffix
    upload_name = f"{Path(filename).stem}{upload_suffix}"
    media_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"

    headers = _auth_headers(client_id, client_secret)
    files = {"image": (upload_name, content, media_type)}
    data = {"source": source, "target": target}

    try:
        response = requests.post(
            IMAGE_TRANSLATION_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise PapagoFileTranslationError(
            f"Papago 이미지 번역 네트워크 오류: {exc}"
        ) from exc

    payload = _response_json(response, "Papago 이미지 번역")
    encoded_image = payload.get("data", {}).get("renderedImage")
    if not isinstance(encoded_image, str) or not encoded_image:
        raise PapagoFileTranslationError(
            "Papago 이미지 응답에 renderedImage가 없습니다."
        )

    try:
        rendered_image = base64.b64decode(encoded_image, validate=True)
    except (ValueError, TypeError) as exc:
        raise PapagoFileTranslationError(
            "Papago renderedImage Base64 디코딩에 실패했습니다."
        ) from exc

    converted_image = _convert_image_to_original_suffix(
        rendered_image,
        suffix,
    )
    output_name = _translated_filename(filename, target)
    output_media_type = (
        mimetypes.guess_type(output_name)[0] or "application/octet-stream"
    )
    return TranslatedFile(
        content=converted_image,
        filename=output_name,
        media_type=output_media_type,
        source_type="image",
    )


def translate_resume_file(
    content: bytes,
    filename: str,
    *,
    source: str = "auto",
    target: str = "en",
    client_id: str | None = None,
    client_secret: str | None = None,
    glossary_key: str | None = None,
) -> TranslatedFile:
    """Route an uploaded resume to Text, Doc, or Image Translation."""

    if not content:
        raise ValueError("빈 파일은 번역할 수 없습니다.")

    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_FILE_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_FILE_SUFFIXES))
        raise ValueError(
            f"지원하지 않는 번역 파일 형식입니다: {suffix or '확장자 없음'}. "
            f"지원 형식: {supported}"
        )

    if suffix in TEXT_FILE_SUFFIXES:
        return translate_txt_file(
            content,
            safe_name,
            source=source,
            target=target,
            client_id=client_id,
            client_secret=client_secret,
            glossary_key=glossary_key,
        )
    if suffix in DOCUMENT_FILE_SUFFIXES:
        return translate_document_file(
            content,
            safe_name,
            source=source,
            target=target,
            client_id=client_id,
            client_secret=client_secret,
            glossary_key=glossary_key,
        )
    return translate_image_file(
        content,
        safe_name,
        source=source,
        target=target,
        client_id=client_id,
        client_secret=client_secret,
    )
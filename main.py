import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from rag.build_rag import search_vector_db
from services.clova_ocr import (
    ClovaOcrError,
    extract_spec_from_file,
    parse_text_content,
)
from services.llm_engine import analyze_spec_gap, generate_cover_letter
from services.papago import (
    PapagoFileTranslationError,
    SUPPORTED_FILE_SUFFIXES,
    translate_resume_file,
)

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpecFit-Main")

ALLOWED_FILE_SUFFIXES = {
    ".txt",
    ".docx",
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".tif",
    ".tiff",
}
MAX_ANALYSIS_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TRANSLATION_UPLOAD_BYTES = 100 * 1024 * 1024

app = FastAPI(
    title="SpecFit-AI Backend API",
    description=(
        "NCP CLOVA OCR, Cloud DB for PostgreSQL(pgvector), "
        "CLOVA Studio, Papago 파일 번역 기반 SpecFit API"
    ),
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_CREDENTIAL = os.getenv("API_KEY_CREDENTIAL", "specfit-secret-key")


def verify_api_key(x_api_key: Optional[str]) -> None:
    if not x_api_key or x_api_key != API_KEY_CREDENTIAL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key 인증입니다.",
        )


def process_uploaded_file(file_path: str, suffix: str) -> dict:
    """Extract and parse TXT, DOCX, PDF, or image content."""

    suffix = suffix.lower()

    if suffix in {".txt", ".docx"}:
        return extract_spec_from_file(file_path)

    if suffix == ".pdf":
        pdf_text = ""
        if PdfReader is not None:
            try:
                reader = PdfReader(file_path)
                extracted_pages = [
                    page_text
                    for page in reader.pages
                    if (page_text := page.extract_text())
                ]
                pdf_text = "\n".join(extracted_pages).strip()
            except Exception as exc:
                logger.warning("[PDF] pypdf 읽기 실패: %s", exc)

        if not pdf_text:
            logger.info(
                "[File/Parser] PDF 직접 추출 실패 -> CLOVA OCR 시도"
            )
            return extract_spec_from_file(file_path)

        parsed = parse_text_content(pdf_text)
        parsed["source_type"] = "pdf_document"
        return parsed

    return extract_spec_from_file(file_path)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "SpecFit-AI Backend Server is running",
    }


@app.post("/api/translate-file")
async def translate_file_endpoint(
    file: UploadFile = File(...),
    source: str = Form("auto"),
    target: str = Form("en"),
    x_api_key: Optional[str] = Header(None),
):
    """Translate an uploaded resume and return a downloadable file."""

    verify_api_key(x_api_key)

    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_FILE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "지원하지 않는 번역 파일 형식입니다: "
                f"{suffix or '확장자 없음'}"
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(content) > MAX_TRANSLATION_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="번역 파일은 최대 100MB까지 업로드할 수 있습니다.",
        )

    try:
        translated = translate_resume_file(
            content,
            filename,
            source=source,
            target=target,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PapagoFileTranslationError as exc:
        logger.error("Papago 파일 번역 실패: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Papago 파일 번역에 실패했습니다: {str(exc)[:500]}",
        ) from exc

    encoded_name = quote(translated.filename)
    response_headers = {
        "Content-Disposition": (
            f"attachment; filename*=UTF-8''{encoded_name}"
        ),
        "X-Translated-Filename": encoded_name,
    }
    return StreamingResponse(
        io.BytesIO(translated.content),
        media_type=translated.media_type,
        headers=response_headers,
    )


@app.post("/api/analyze")
async def analyze_spec_endpoint(
    file: UploadFile = File(...),
    company: str = Form(...),
    position: str = Form(...),
    x_api_key: Optional[str] = Header(None),
):
    """
    1. TXT/PDF/DOCX 직접 추출 또는 CLOVA OCR 이미지 텍스트 추출
    2. PostgreSQL/pgvector 합격자 유사 스펙 검색
    3. CLOVA Studio 스펙 갭 분석
    4. CLOVA Studio 한국어 자기소개서 생성
    """

    verify_api_key(x_api_key)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_FILE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"지원하지 않는 파일 형식입니다: {suffix or '확장자 없음'}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(content) > MAX_ANALYSIS_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="분석 파일은 10MB 이하여야 합니다.",
        )

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        logger.info("[File/OCR] 문서 분석 중 (확장자: %s)", suffix)
        extraction_result = process_uploaded_file(tmp_path, suffix)

        extracted_text = extraction_result.get("text", "")
        extracted_keywords = extraction_result.get("keywords", {})
        extracted_scores = extraction_result.get("scores", {})
        extracted_certs = extraction_result.get("certifications", [])
        structured_fields = extraction_result.get("structured_fields", {})
        source_type = extraction_result.get("source_type", "unknown")

        if not extracted_text.strip():
            raise ValueError("파일에서 분석할 텍스트를 찾지 못했습니다.")

        logger.info(
            "[File/OCR] 추출 완료 (source=%s, chars=%d, fields=%d)",
            source_type,
            len(extracted_text),
            len(structured_fields),
        )

        formatted_user_spec = f"""
[추출된 전체 서류 텍스트]
{extracted_text}

[파싱된 주요 핵심 키워드]
- 기술/도구: {json.dumps(extracted_keywords, ensure_ascii=False)}
- 어학 성적: {json.dumps(extracted_scores, ensure_ascii=False)}
- 보유 자격증: {', '.join(extracted_certs) if extracted_certs else '없음'}
"""

        rag_query = (
            f"기업명: {company} | 직무: {position} | "
            f"핵심스펙: {extracted_text[:200]}"
        )
        retrieved_db_results = search_vector_db(
            query=rag_query,
            company_filter=company,
            top_k=3,
        )
        if not retrieved_db_results:
            retrieved_db_results = search_vector_db(
                query=rag_query,
                company_filter=None,
                top_k=3,
            )

        retrieved_specs_list = [
            (
                f"기업: {item.get('company')}, "
                f"직무: {item.get('job_category')}\n"
                f"학점: {item.get('gpa')}, "
                f"토익: {item.get('toeic')}, "
                f"자격증: {item.get('certificate')}, "
                f"인턴: {item.get('internship')}\n"
                f"경험 상세: {item.get('experience_summary')}"
            )
            for item in retrieved_db_results
        ]

        analysis_report = analyze_spec_gap(
            user_spec=formatted_user_spec,
            retrieved_specs=retrieved_specs_list,
            company=company,
            position=position,
        )

        try:
            cover_letter_result = generate_cover_letter(
                user_spec=formatted_user_spec,
                company=company,
                position=position,
                gap_analysis=analysis_report,
            )
        except Exception as exc:
            logger.warning("자기소개서 생성 실패: %s", exc)
            cover_letter_result = "자기소개서 초안 생성에 실패했습니다."

        return {
            "status": "success",
            "parsed_user_spec": {
                "source_type": source_type,
                "extracted_text": extracted_text,
                "structured_fields": structured_fields,
                "keywords": extracted_keywords,
                "scores": extracted_scores,
                "certifications": extracted_certs,
            },
            "retrieved_reference_count": len(retrieved_specs_list),
            "analysis_report": analysis_report,
            "cover_letter": cover_letter_result,
        }

    except ClovaOcrError as exc:
        logger.error("CLOVA OCR 처리 오류: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="OCR 처리에 실패했습니다.",
        ) from exc
    except ValueError as exc:
        logger.warning("파일 처리 오류: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("파이프라인 전체 오류: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="서버 내부 분석 오류가 발생했습니다.",
        ) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
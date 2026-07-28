import json
import logging
import os
import tempfile
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from rag.build_rag import search_vector_db
from services.clova_ocr import ClovaOcrError, extract_spec_from_file
from services.llm_engine import analyze_spec_gap, generate_cover_letter
from services.papago import (
    PapagoTranslationError,
    translate_analysis_report,
)


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpecFit-Main")

ALLOWED_FILE_SUFFIXES = {
    ".txt", ".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(
    title="SpecFit-AI Backend API",
    description=(
        "NCP CLOVA OCR, Cloud DB for PostgreSQL(pgvector), "
        "CLOVA Studio, Papago 기반 스펙 갭 분석 API"
    ),
    version="1.0.0",
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


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "SpecFit-AI Backend Server is running"}


@app.post("/api/analyze")
async def analyze_spec_endpoint(
    file: UploadFile = File(...),
    company: str = Form(...),
    position: str = Form(...),
    x_api_key: Optional[str] = Header(None),
):
    """
    1. TXT 직접 읽기 또는 CLOVA OCR 이미지 텍스트 추출
    2. PostgreSQL/pgvector 합격자 유사 스펙 검색
    3. CLOVA Studio 스펙 갭 분석
    4. Papago 전체 분석 리포트 영문 번역
    """

    verify_api_key(x_api_key)
    filename = file.filename or ""
    suffix = os.path.splitext(filename)[1].lower()

    if suffix not in ALLOWED_FILE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"지원하지 않는 파일 형식입니다: {suffix or '확장자 없음'}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일은 10MB 이하여야 합니다.")

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        logger.info("[File/OCR] 스펙 서류 분석 중")
        extraction_result = extract_spec_from_file(tmp_path)
        extracted_text = extraction_result.get("text", "")
        extracted_keywords = extraction_result.get("keywords", {})
        extracted_scores = extraction_result.get("scores", {})
        extracted_certs = extraction_result.get("certifications", [])
        source_type = extraction_result.get("source_type", "unknown")

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

        retrieved_specs_list = []
        for item in retrieved_db_results:
            retrieved_specs_list.append(
                f"기업: {item.get('company')}, "
                f"직무: {item.get('job_category')}\n"
                f"학점: {item.get('gpa')}, "
                f"토익: {item.get('toeic')}, "
                f"자격증: {item.get('certificate')}, "
                f"인턴: {item.get('internship')}\n"
                f"경험 상세: {item.get('experience_summary')}"
            )

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

        try:
            english_report = translate_analysis_report(analysis_report)
        except (PapagoTranslationError, ValueError) as exc:
            logger.warning("Papago 전체 리포트 번역 실패: %s", exc)
            english_report = {}

        return {
            "status": "success",
            "parsed_user_spec": {
                "source_type": source_type,
                "keywords": extracted_keywords,
                "scores": extracted_scores,
                "certifications": extracted_certs,
            },
            "retrieved_reference_count": len(retrieved_specs_list),
            "analysis_report": analysis_report,
            "cover_letter": cover_letter_result,
            "translated_english": english_report,
        }

    except ClovaOcrError as exc:
        logger.error("CLOVA OCR 처리 오류: %s", exc)
        raise HTTPException(status_code=502, detail="OCR 처리에 실패했습니다.") from exc
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
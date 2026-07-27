import os
import json
import logging
import tempfile
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 모듈 Import
from services.clova_ocr import extract_spec_from_image, ClovaOcrError
from services.llm_engine import analyze_spec_gap
from services.papago import translate_to_resume_english, PapagoTranslationError
from rag.build_rag import search_vector_db

load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpecFit-Main")

app = FastAPI(
    title="SpecFit-AI Backend API",
    description="NCP CLOVA OCR, Cloud DB for PostgreSQL(pgvector), CLOVA Studio, Papago 기반 스펙 갭 분석 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 보안을 위한 API Key 검증
API_KEY_CREDENTIAL = os.getenv("API_KEY_CREDENTIAL", "specfit-secret-key")

def verify_api_key(x_api_key: Optional[str]):
    if not x_api_key or x_api_key != API_KEY_CREDENTIAL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key 인증입니다."
        )


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "SpecFit-AI Backend Server is running"}


@app.post("/api/analyze")
async def analyze_spec_endpoint(
    file: UploadFile = File(...),
    company: str = Form(...),
    position: str = Form(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    1. CLOVA OCR: 이력서/스펙 이미지 텍스트 및 키워드 추출
    2. PostgreSQL (pgvector): 목표 기업/직무 기준 합격자 유사 스펙 RAG 검색
    3. CLOVA Studio (HCX-005): 스펙 갭 정량/정성 분석 및 Fit Score 산출
    4. Papago: 분석 결과 영어 레쥬메 스타일 번역
    """
    # 1. API Key 검증
    verify_api_key(x_api_key)
    logger.info(f"🚀 스펙 분석 요청 수신 - 목표 기업: {company}, 목표 직무: {position}")

    # 2. 임시 파일 생성 및 CLOVA OCR 처리
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info("1️⃣ [CLOVA OCR] 스펙 서류 분석 중...")
        ocr_result = extract_spec_from_image(tmp_path)
        extracted_text = ocr_result.get("text", "")
        extracted_keywords = ocr_result.get("keywords", {})
        extracted_scores = ocr_result.get("scores", {})
        extracted_certs = ocr_result.get("certifications", [])

        # LLM 프롬프트용 텍스트 구성
        formatted_user_spec = f"""
[추출된 전체 서류 텍스트]
{extracted_text}

[파싱된 주요 핵심 키워드]
- 기술/도구: {json.dumps(extracted_keywords, ensure_ascii=False)}
- 어학 성적: {json.dumps(extracted_scores, ensure_ascii=False)}
- 보유 자격증: {', '.join(extracted_certs) if extracted_certs else '없음'}
"""
        logger.info("✅ CLOVA OCR 처리 완료")

        # 3. [RAG] PostgreSQL (pgvector) 합격자 스펙 검색
        logger.info("2️⃣ [PostgreSQL pgvector] 합격자 유사 스펙 RAG 검색 중...")
        rag_query = f"기업명: {company} | 직무: {position} | 핵심스펙: {extracted_text[:200]}"
        
        # 1차: 기업명 필터링 검색
        retrieved_db_results = search_vector_db(query=rag_query, company_filter=company, top_k=3)
        
        # Fallback: 특정 기업 데이터가 적을 경우 전체 유사 검색
        if not retrieved_db_results:
            logger.info("기업 지정 검색 결과 없음 -> 전체 DB 대상 유사도 검색 수행")
            retrieved_db_results = search_vector_db(query=rag_query, company_filter=None, top_k=3)

        # RAG 검색 결과를 LLM 입력용 문자열 리스트로 재구성
        retrieved_specs_list = []
        for item in retrieved_db_results:
            spec_str = (
                f"기업: {item.get('company')}, 직무: {item.get('job_category')}\n"
                f"학점: {item.get('gpa')}, 토익: {item.get('toeic')}, "
                f"자격증: {item.get('certificate')}, 인턴: {item.get('internship')}\n"
                f"경험 상세: {item.get('experience_summary')}"
            )
            retrieved_specs_list.append(spec_str)

        logger.info(f"✅ RAG 검색 완료 ({len(retrieved_specs_list)}건 가져옴)")

        # 4. [LLM] CLOVA Studio (HCX-005) 갭 분석
        logger.info("3️⃣ [CLOVA Studio] HyperCLOVA X 스펙 갭 분석 실행 중...")
        analysis_report = analyze_spec_gap(
            user_spec=formatted_user_spec,
            retrieved_specs=retrieved_specs_list,
            company=company,
            position=position
        )
        logger.info("✅ CLOVA Studio 분석 완료")

        # 5. [Papago] 주요 분석 요약 영문 번역
        logger.info("4️⃣ [Papago] 요약 결과 영문 번역 중...")
        english_summary = ""
        english_encouragement = ""
        
        if "summary" in analysis_report:
            try:
                english_summary = translate_to_resume_english(analysis_report["summary"])
            except PapagoTranslationError as pe:
                logger.warning(f"Papago summary 번역 실패: {pe}")
                english_summary = analysis_report["summary"]

        if "encouragement" in analysis_report:
            try:
                english_encouragement = translate_to_resume_english(analysis_report["encouragement"])
            except PapagoTranslationError as pe:
                logger.warning(f"Papago encouragement 번역 실패: {pe}")
                english_encouragement = analysis_report["encouragement"]

        logger.info("✅ Papago 번역 완료")

        # 6. 최종 응답 반환
        return {
            "status": "success",
            "parsed_user_spec": {
                "keywords": extracted_keywords,
                "scores": extracted_scores,
                "certifications": extracted_certs
            },
            "retrieved_reference_count": len(retrieved_specs_list),
            "analysis_report": analysis_report,
            "translated_english": {
                "summary": english_summary,
                "encouragement": english_encouragement
            }
        }

    except ClovaOcrError as e:
        logger.error(f"CLOVA OCR 처리 오류: {e}")
        raise HTTPException(status_code=500, detail=f"OCR 오류: {str(e)}")
    except Exception as e:
        logger.error(f"파이프라인 전체 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 내부 분석 오류: {str(e)}")
    finally:
        # 임시 파일 삭제
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
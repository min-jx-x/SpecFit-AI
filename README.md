# 🚀 SpecFit-AI
> **Target 기업 합격자 DB 기반 맞춤형 스펙 갭 분석 & AI 이력서·자소서 생성 플랫폼**

---

##  1. 프로젝트 개요
* **서비스명:** SpecFit-AI
* **목적:** 취업 준비생의 목표 기업/직무 대비 정량·정성 스펙 위치를 객관적으로 분석하고, 부족한 역량을 보완하는 AI 맞춤형 로드맵 및 영문 이력서를 자동 생성하는 서비스입니다.

---

##  2. 주요 기능
* **스펙 & 공고 이미지 파싱:** NCP CLOVA OCR 기반 자격증/성적표/공고 자동 파싱
* **3자 비교 RAG 분석:** NCP Cloud DB for PostgreSQL(pgvector) 내 기업별 합격자 스펙 DB와 내 스펙 정량/정성 비교
* **AI 보완 로드맵 & 자소서 생성:** LLM 기반 단기/중기 스펙 타임라인 및 JD 맞춤 자소서 생성
* **글로벌 영문 변환:** NCP Papago API 기반 직무 전문 용어 적용 영문 이력서 변환

---

##  3. 기술 스택 (Tech Stack)
* **Language:** Python 3.10+
* **Backend:** FastAPI, Uvicorn
* **Frontend:** Streamlit
* **Vector DB:** NCP Cloud DB for PostgreSQL + pgvector
* **NCP AI Services:** CLOVA OCR, Papago Translation API
* **Deployment:** NAVER Cloud Platform Compute Server (2vCPU, 4GB RAM, Ubuntu 24.04 LTS)

---

##  4. 시스템 아키텍처 (System Architecture)

```text
[User Screen] (Streamlit / Port 8501)
       │
       ▼ (HTTP POST /api/analyze)
[Backend Core] (FastAPI / Port 8000)
       │
       ├─► [1. OCR Module] ------► NCP CLOVA OCR API (이미지 텍스트 파싱)
       ├─► [2. RAG Module] ------► PostgreSQL/pgvector Search (합격자 DB 유사도 검색)
       ├─► [3. LLM Module] ------► OpenAI/LLM Engine (스펙 갭 분석 및 자소서 생성)
       └─► [4. Translation] ----► NCP Papago API (영문 Resume 변환)

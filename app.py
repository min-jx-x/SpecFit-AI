import os
import requests
import streamlit as st
from PIL import Image  # TIF, TIFF를 포함한 이미지 처리를 담당합니다.

# 1. 페이지 설정 및 커스텀 CSS (흰 바탕 + 파란색 포인트)
st.set_page_config(page_title="SpecGap AI", page_icon="🤖", layout="centered")

st.markdown("""
    <style>
        .stApp { background-color: #FFFFFF; color: #333333; }
        div.stButton > button:first-child {
            background-color: #0066CC !important; color: white !important;
            border: none; border-radius: 6px; padding: 0.5rem 2rem;
            font-weight: bold; transition: background-color 0.3s ease;
        }
        div.stButton > button:first-child:hover { background-color: #004C99 !important; }
        h1, h2, h3 { color: #0066CC !important; }
        .stAlert { border-left: 5px solid #0066CC !important; }
        .cover-letter-box {
            background-color: #F8FAFC; padding: 20px; 
            border-radius: 8px; border: 1px solid #E2E8F0;
            line-height: 1.6; white-space: pre-wrap;
        }
    </style>
""", unsafe_allow_html=True)
API_KEY = os.getenv("API_KEY", "specfit-secret-key")
API_URL = "http://localhost:8000/api/analyze"



# 2. 타이틀
st.title("🤖 SpecGap AI 문서 분석기")
st.markdown("지원 기업 및 직무 맞춤형 **역량 진단**부터 합격을 위한 **자기소개서 초안**까지 한 번에 확인하세요.")

# 3. 사용자 입력 섹션
st.subheader("📋 지원 정보 입력")
col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input("🎯 지원 기업명", placeholder="예: 네이버, 카카오")
with col2:
    job_position = st.text_input("💼 지원 직무", placeholder="예: 백엔드 개발자, 서비스 기획")

# 4. 파일 업로드 (tif, tiff 형식 추가)
st.subheader("📁 내 문서 및 이미지 업로드")
uploaded_file = st.file_uploader(
    "분석 및 자소서 변환을 할 서류를 첨부해 주세요. (문서 및 이미지 파일 지원)",
    type=["txt", "pdf", "docx", "png", "jpg", "jpeg", "tif", "tiff"]
)

# 5. 파일 처리 및 시각화
if uploaded_file is not None:
    # 파일 확장자 확인
    file_extension = uploaded_file.name.split(".")[-1].lower()

    # 이미지 파일 그룹 정의 (tif, tiff 포함)
    image_extensions = ["png", "jpg", "jpeg", "tif", "tiff"]

    # 이미지 파일일 경우 화면에 미리보기 출력
    if file_extension in image_extensions:
        st.info(f"📸 이미지 파일이 로드되었습니다: {uploaded_file.name}")
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="업로드된 이미지 미리보기", use_container_width=True)
        except Exception as e:
            st.error(f"⚠️ 이미지를 화면에 표시하는 중 오류가 발생했습니다: {e}")
            st.warning("화면 표시에는 실패했지만, API 분석 전송은 가능합니다.")
    else:
        st.info(f"📂 문서 파일이 정상적으로 로드되었습니다: {uploaded_file.name}")

    # 6. 분석 및 자소서 생성 로직 구동
    if st.button("🚀 SpecGap AI 분석 및 자소서 추천"):
        if not API_KEY:
            st.error("좌측 사이드바에 API Key를 먼저 입력해 주세요.")
        elif not company_name or not job_position:
            st.warning("지원 기업명과 직무를 모두 입력해야 정확한 맞춤 자소서가 나옵니다.")
        else:
            with st.spinner(f"⏳ {company_name} [{job_position}] 맞춤 분석 및 자기소개서 작성 중..."):
                try:
                    # 전송 데이터 구성
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}#:file = {"file":(파일의 이름, 파일의 실제 데이터, 파일 형식)}
                    data = {"company": company_name, "position": job_position}#data = {"company":지원 기업명,"position": 지원 직무}
                    headers = {
                    "x-api-key": API_KEY, # :point_left: 백엔드가 읽는 헤더 명칭(x-api-key)으로 변경!
                    "Accept": "application/json"
                    }#headers = {"Authorization": f"Bearer {API 인증키}","Accept":json응답만 받음}

                    # API 요청
                    response = requests.post(API_URL, files=files, data=data, headers=headers, timeout=300)#서버 데이터 보낼 때 씀,(API_URL:FAST API 서버 링크, files=files, data=data, headers=headers, timeout=60:대기 제한 시간)

                    if response.status_code == 200:
                        try:
                            st.success("✅ 정밀 진단 및 자기소개서 작성이 완료되었습니다!")
                            res = response.json()  # 백엔드 반환 결과 딕셔너리 전체

                            # [결과 화면 렌더링 시작]
                            st.markdown("---")
                            st.header("📊 SpecGap AI 종합 보고서")
                            st.caption(f"**대상 기업**: {company_name} | **대상 직무**: {job_position}")

                            # ----------------------------------------------------
                            # 1. 유저 스펙 파싱 정보 (parsed_user_spec) 데이터 시각화
                            # ----------------------------------------------------
                            user_spec = res.get("parsed_user_spec", {})

                            st.subheader("🔍 추출된 내 스펙 분석 결과")

                            # (1) 유저의 키워드 (keywords) 가로 배치 태그 출력
                            keywords = user_spec.get("keywords", [])
                            if keywords:
                                st.markdown("**핵심 역량 키워드**")
                                st.write(" ".join([f"`{kw}`" for kw in keywords]))

                            # (2) 유저의 스코어 (scores) 메트릭(Metric) 형태로 출력
                            scores = user_spec.get("scores", {})
                            if scores:
                                st.markdown("**부문별 역량 점수**")
                                score_cols = st.columns(len(scores))  # 스코어 개수만큼 가로 칸 생성
                                for col, (score_name, score_val) in zip(score_cols, scores.items()):
                                    with col:
                                        st.metric(label=score_name, value=f"{score_val}점")

                            # (3) 유저의 자격증 (certifications) 리스트 출력
                            certifications = user_spec.get("certifications", [])
                            if certifications:
                                st.markdown("**보유 자격증 정보**")
                                # 자격증들을 작은 블록 형태로 나열
                                st.write(" ".join([f"🔒 :blue[{cert}]" for cert in certifications]))

                            # ----------------------------------------------------
                            # 2. 합격자 참고 개수 및 전체 분석 결과 출력
                            # ----------------------------------------------------
                            st.markdown("---")
                            ref_count = res.get("retrieved_reference_count", 0)
                            st.info(f"💡 이번 분석을 위해 시스템이 참고한 실제 합격자 데이터: **{ref_count}개**")

                            st.subheader("📝 SpecGap AI 전반적 분석 리포트")
                            analysis_report = res.get("analysis_report", "분석 결과 리포트를 불러올 수 없습니다.")

                            # 백엔드에서 온 마크다운 기반의 전체 분석 결과(리포트 + 자소서 초안 포함) 출력
                            st.markdown(analysis_report)

                            # ----------------------------------------------------
                            # 3. 영어 번역 정보 출력 (translated_english)
                            # ----------------------------------------------------
                            eng_data = res.get("translated_english", {})
                            if eng_data:
                                st.markdown("---")
                                with st.expander("🌐 English Summary & Encouragement (영어 분석 및 격려)", expanded=False):
                                    # 영어로 번역된 요약 분석 결과 (summary)
                                    if eng_data.get("summary"):
                                        st.markdown("**[English Summary]**")
                                        st.info(eng_data.get("summary"))

                                    # 영어로 번역된 격려 메시지 (encouragement)
                                    if eng_data.get("encouragement"):
                                        st.markdown("**[AI Message]**")
                                        st.success(f"🍀 {eng_data.get('encouragement')}")

                        except ValueError:  # JSONDecodeError 등을 포함하는 예외
                            st.error("❌ 서버가 올바른 데이터(JSON)를 반환하지 않았습니다. 관리자에게 문의하세요.")
                    else:
                        st.error(f"❌ API 연결 오류 (코드: {response.status_code})")
                        st.text(response.text)

                except requests.exceptions.Timeout:
                    st.error("⏳ 서버 응답 시간이 초과되었습니다. (60초 초과)")
                except requests.exceptions.ConnectionError:
                    st.error("🌐 API 서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인해 주세요.")

                except Exception as e:
                    st.error(f"🔍 알 수 없는 에러가 발생했습니다: {e}")
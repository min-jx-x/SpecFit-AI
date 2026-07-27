import streamlit as st
import requests

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
        /* 자기소개서 박스 스타일 */
        .cover-letter-box {
            background-color: #F8FAFC; padding: 20px; 
            border-radius: 8px; border: 1px solid #E2E8F0;
            line-height: 1.6; white-space: pre-wrap;
        }
    </style>
""", unsafe_allow_html=True)

# 2. 타이틀
st.title("🤖 SpecGap AI 문서 분석기")
st.markdown("지원 기업 및 직무 맞춤형 **역량 진단**부터 합격을 위한 **자기소개서 초안**까지 한 번에 확인하세요.")

# 사이드바 설정
with st.sidebar:
    st.subheader("⚙️ API Configuration")
    API_KEY = st.text_input("API Key", type="password", help="SpecGap AI API Key")
    API_URL = "https://specgap.ai"

# 3. 사용자 입력 섹션
st.subheader("📋 지원 정보 입력")
col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input("🎯 지원 기업명", placeholder="예: 네이버, 카카오")
with col2:
    job_position = st.text_input("💼 지원 직무", placeholder="예: 백엔드 개발자, 서비스 기획")

# 4. 파일 업로드
st.subheader("📁 내 문서 업로드 (기존 이력서 또는 이력 기술서)")
uploaded_file = st.file_uploader("분석 및 자소서 변환을 할 서류를 첨부해 주세요.", type=["txt", "pdf", "docx"])

# 5. 분석 및 자소서 생성 로직 구동
if uploaded_file is not None:
    st.info(f"📂 파일이 준비되었습니다: {uploaded_file.name}")

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
                    headers = {"Authorization": f"Bearer {API_KEY}"}#headers = {"Authorization": f"Bearer {API 인증키}"}

                    # API 요청
                    response = requests.post(API_URL, files=files, data=data, headers=headers, timeout=60)#서버 데이터 보낼 때 씀,(API_URL:FAST API 서버 링크, files=files, data=data, headers=headers, timeout=60:대기 제한 시간)

                    if response.status_code == 200:
                        st.success("✅ 정밀 진단 및 자기소개서 작성이 완료되었습니다!")
                        res = response.json()#반환 결과

                        # [결과 화면 렌더링]
                        st.markdown("---")
                        st.header("📊 SpecGap AI 종합 보고서")
                        st.caption(f"**대상 기업**: {company_name} | **대상 직무**: {job_position}")

                        # 1. 부족한 점 vs 준비할 점 레이아웃
                        col_gap, col_plan = st.columns(2)
                        with col_gap:
                            st.subheader("❌ 현재 부족한 역량 (Gap)")
                            # 반환결과의 값 중 "gaps"키 값을 가져옵니다. 콤마(,)뒤에는 결과가 없을 때 기본값(현재 부족한 역량)
                            gaps = res.get("gaps",
                                           ["• 직무 핵심 기술 스택에 대한 구체적 성과 기재 부족", "• 해당 기업 인재상(도전정신 등)을 뒷받침할 에피소드 보완 필요"])

                            for gap in gaps:
                                st.error(gap)

                        with col_plan:
                            st.subheader("💡 합격을 위한 준비 전략")
                            # 반환결과의 값 중 "prepares"키 값을 가져옵니다. 콤마(,)뒤에는 결과가 없을 때 기본값(합격을 위한 전략)
                            prepares = res.get("prepares",
                                               ["• 프로젝트 내 본인의 기여도와 수치적 성과 중심 재구성", "• 기업의 최근 기술 블로그 비즈니스 방향성 연계 강조"])

                            for prep in prepares:
                                st.success(prep)

                        # 2. 종합 피드백 전문
                        if "detailed_feedback" in res:
                            st.subheader("📝 AI 종합 피드백")
                            # 반환결과의 값 중 "detailed_feedback"키 값을 가져옵니다.(AI 종합 피드백)
                            st.info(res["detailed_feedback"])

                        # 3. 추가된 파트: 맞춤형 자기소개서 추천 결과
                        st.markdown("---")
                        st.subheader("✍️ SpecGap AI 추천 자기소개서 (초안)")
                        st.markdown(f"업로드한 문서와 {company_name}의 {job_position} 직무 핵심 역량을 결합하여 작성된 추천 자소서 문항입니다.")

                        # API 결과 내 'cover_letter' 필드가 있다고 가정 (없을 시 예시 템플릿 제공)
                        default_letter = f"""[지원동기 및 포부: {company_name}의 기술 성장을 함께 이끌 원동력]

기존에 진행했던 프로젝트에서 부족했던 역량을 {company_name}의 {job_position} 직무 환경 안에서 해결하고 기여하고자 지원했습니다. 저는 기존 서류에서 드러난 것 이상으로 시스템 최적화와 팀 협업에 강점을 가지고 있습니다. 

{company_name}이 최근 집중하고 있는 비즈니스 방향성에 맞춰, 제가 가진 기술적 기반을 바탕으로 입사 후 부족한 실무 프로세스를 빠르게 체득하여 가시적인 성과를 내겠습니다."""

                        # 반환결과의 값 중"cover_letter"키 값을 가져옵니다. 콤마(,)뒤에는 결과가 없을 때 기본값(자소서 내용)
                        cover_letter = res.get("cover_letter", default_letter)

                        # 텍스트 박스 형태로 이쁘게 출력
                        st.markdown(f'<div class="cover-letter-box">{cover_letter}</div>', unsafe_allow_html=True)

                        # 사용자가 바로 복사해서 쓸 수 있도록 복사 편의기능 제공
                        st.text_area("📋 텍스트 복사용 칸 (수정 및 복사가 가능합니다)", value=cover_letter, height=200)

                    else:
                        st.error(f"❌ API 연결 오류 (코드: {response.status_code})")
                        st.text(response.text)

                except requests.exceptions.Timeout:
                    st.error("⏳ 서버 응답 시간이 초과되었습니다.")
                except requests.exceptions.RequestException as e:
                    st.error(f"🔌 네트워크 에러가 발생했습니다: {e}")

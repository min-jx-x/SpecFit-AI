import os
import re
import requests
import streamlit as st
import plotly.graph_objects as go
from PIL import Image  # TIF, TIFF를 포함한 이미지 처리를 담당합니다.
from streamlit_float import float_init, float_parent


#streamlit run app.py

float_init()

# 1. 페이지 설정 및 커스텀 CSS (흰 바탕 + 파란색 포인트 및 커스텀 크기/카드 스타일 통합)
st.set_page_config(page_title="SpecGap AI", page_icon="🤖", layout="centered")

st.markdown("""
    <style>
        /* 기본 공통 레이아웃 */
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

        /* 크기 규칙 스타일 및 블루 톤/교차 배경 정의 */
        .size-largest { font-size: 28px; font-style: italic; font-weight: normal; color: #1E3A8A; margin-bottom: 5px; }
        .size-large-bold { font-size: 22px; font-weight: bold; color: #0F172A; margin-top: 30px; margin-bottom: 12px; border-left: 5px solid #3B82F6; padding-left: 10px; }
        .size-normal { font-size: 15px; font-weight: normal; line-height: 1.6; color: #334155; }

        /* 세부 정렬 구성 */
        .space-close { margin-bottom: 4px; }
        .space-far { margin-bottom: 35px; }

        /* 반복문 컴포넌트용 카드 및 교차 배경 스타일 */
        .data-card {
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 14px; 
            border: 1px solid #E2E8F0;
        }
        .bg-blue-light { background-color: #F8FAFC; border-left: 4px solid #93C5FD; } 
        .bg-blue-contrast { background-color: #EFF6FF; border-left: 4px solid #3B82F6; } 

        /* 요약 섹션 특화 */
        .summary-box { background-color: #F1F5F9; padding: 14px; border-radius: 6px; margin-bottom: 18px; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)




API_KEY = os.getenv("API_KEY_CREDENTIAL", os.getenv("API_KEY", "specfit-secret-key"))
API_URL = os.getenv("API_URL", "http://localhost:8000/api/analyze")

MOCK_ANALYSIS_REPORT = {
    'target': {'company': '네이버', 'position': '백엔드 개발자'},
    'summary': '사용자의 현재 스펙은 데이터/AI 엔지니어로서의 역량을 갖추고 있으나, 목표 직무인 백엔드 개발자로 전환하기 위해서는 일부 기술적 보완이 필요합니다.',
    'quantitative_gaps': [
        {
            'item': '어학 점수',
            'user_value': 'TOEFL 95 / TEPS 340',
            'passed_avg': '없음 (비교 대상 없음)',
            'gap': '해당 정보가 없어 비교 불가능',
            'priority': '중',
            'comment': '일반적으로 IT 기업의 경우 어학 점수는 필수 요건이 아닐 수 있지만, 글로벌 기업에서는 중요하게 볼 수 있습니다.'
        },
        {
            'item': '관련 자격증',
            'user_value': 'ADsP, SQLD, 정보보안기사',
            'passed_avg': '없음 (비교 대상 없음)',
            'gap': '해당 정보가 없어 비교 불가능',
            'priority': '중',
            'comment': '현재 보유한 자격증들은 데이터 분석 및 보안 관련이지만, 백엔드 개발에 필요한 자격증(예: AWS, Azure 인증 등) 취득이 필요할 수 있습니다.'
        }
    ],
    'qualitative_gaps': [
        {
            'category': '기술 스택의 일치 여부',
            'analysis': '사용자는 주로 데이터 분석 및 머신러닝 관련 기술을 보유하고 있으며, 백엔드 개발에 필요한 Java, Spring 등의 기술은 언급되지 않았습니다.',
            'suggestion': '백엔드 개발에 자주 사용되는 프레임워크나 언어(JAVA, Spring 등) 학습 후 포트폴리오에 반영하여 경험을 확장하십시오.'
        },
        {
            'category': '실제 프로젝트 경험',
            'analysis': '사용자는 다양한 프로젝트를 진행했으나, 백엔드 개발과 직접적으로 관련된 프로젝트는 보이지 않습니다.',
            'suggestion': '백엔드와 관련된 프로젝트(RESTful API 설계 및 구현, 데이터베이스 최적화 등)를 추가로 진행하여 실무 경험을 쌓으십시오.'
        }
    ],
    'priority_actions': [
        {
            'rank': 1,
            'action': 'JAVA 및 Spring Framework 학습 시작',
            'reason': '백엔드 개발에서 JAVA와 Spring은 매우 중요한 기술이며, 이를 통해 사용자님의 기술적 범위를 넓힐 수 있습니다.',
            'expected_effect': '목표 직무로의 전환 가능성을 높이고, 면접에서의 질문 대응력을 강화할 수 있습니다.'
        }
    ],
    'Fit_score': '60점',
    'encouragement': '현재 보유한 기술과 경험은 훌륭하나, 목표 직무에 맞도록 약간의 기술적 보완이 필요합니다. 새로운 기술을 배우고 관련 프로젝트를 진행한다면 충분히 경쟁력을 갖출 수 있을 것입니다!'
}

EN_MOCK_ANALYSIS_REPORT = {
  "target": {
    "company": "NAVER",
    "position": "Backend Developer"
  },
  "summary": "The user's current specifications demonstrate capabilities as a Data/AI Engineer. However, some technical supplements are required to transition into the target role of a Backend Developer.",
  "quantitative_gaps": [
    {
      "item": "Language Test Score",
      "user_value": "TOEFL 95 / TEPS 340",
      "passed_avg": "None (No comparison group)",
      "gap": "Incomparable due to lack of information",
      "priority": "Medium",
      "comment": "In general, language scores may not be a mandatory requirement for IT companies, but they can be considered important in global companies."
    },
    {
      "item": "Relevant Certifications",
      "user_value": "ADsP, SQLD, Information Security Engineer",
      "passed_avg": "None (No comparison group)",
      "gap": "Incomparable due to lack of information",
      "priority": "Medium",
      "comment": "The currently held certifications are focused on data analysis and security. Acquiring certifications required for backend development (e.g., AWS, Azure certifications, etc.) may be necessary."
    }
  ],
  "qualitative_gaps": [
    {
      "category": "Tech Stack Alignment",
      "analysis": "The user mainly possesses technologies related to data analysis and machine learning. Technologies required for backend development, such as Java and Spring, are not mentioned.",
      "suggestion": "Expand your experience by learning frameworks or languages frequently used in backend development (Java, Spring, etc.) and reflecting them in your portfolio."
    },
    {
      "category": "Actual Project Experience",
      "analysis": "The user has conducted various projects, but no projects directly related to backend development are observed.",
      "suggestion": "Gain practical experience by undertaking additional backend-related projects, such as RESTful API design and implementation, and database optimization."
    }
  ],
  "priority_actions": [
    {
      "rank": 1,
      "action": "Start learning Java and Spring Framework",
      "reason": "Java and Spring are highly critical technologies in backend development. Learning them will broaden your technical scope.",
      "expected_effect": "It will increase the possibility of transitioning to the target job and strengthen your ability to respond to questions during interviews."
    }
  ],
  "Fit_score": "60 points",
  "encouragement": "Your current skills and experiences are excellent, but a slight technical supplement is needed to align with the target role. If you learn new technologies and conduct relevant projects, you will surely be competitive enough!"
}

if "button_text" not in st.session_state:
    st.session_state.button_text = "English"

# 3. 우측 하단 고정 버튼 영역
button_container = st.container()
with button_container:
    # 💡 버튼의 라벨에 세션 상태 변수를 그대로 넣어줍니다.
    if st.button(st.session_state.button_text, key="floating_btn", type="primary"):
        # 버튼이 클릭될 때마다 글자를 교체 (토글)
        if st.session_state.button_text == "한글":
            st.session_state.button_text = "English"
        else:
            st.session_state.button_text = "한글"

        # 글자 변경을 화면에 즉시 반영하기 위해 새로고침
        st.rerun()

    # 우측 하단 고정 CSS 적용
    float_parent(css="position: fixed; bottom: 30px; right: 30px; z-index: 9999;")

# 2. 타이틀
kr_text=["지원 기업 및 직무 맞춤형 **역량 진단**부터 합격을 위한 **자기소개서 초안**까지 한 번에 확인하세요.",
         "📋 지원 정보 입력",
         "🎯 지원 기업명",
        "예: 네이버, 카카오",
         "💼 지원 직무",
         "예: 백엔드 개발자, 서비스 기획",
         "📁 내 문서 및 이미지 업로드",
         "분석 및 자소서 변환을 할 서류를 첨부해 주세요. (문서 및 이미지 파일 지원)",
         "📸 이미지 파일이 로드되었습니다: ",
         "업로드된 이미지 미리보기",
         "️ 이미지를 화면에 표시하는 중 오류가 발생했습니다: ",
         "화면 표시에는 실패했지만, API 분석 전송은 가능합니다.",
         "📂 문서 파일이 정상적으로 로드되었습니다:",
         "🚀 SpecFit AI 분석 및 자소서 추천",
         "지원 기업명과 직무를 모두 입력해야 정확한 맞춤 자소서가 나옵니다.",
         "맞춤 분석 및 자기소개서 작성 중...",
         "✅ API 정밀 진단 및 자기소개서 작성이 완료되었습니다!",
         "❌ 서버가 올바른 데이터(JSON)를 반환하지 않았습니다.",
         "⚠️ API 서버 오류 (코드: ",
         "). 로컬 예시 데이터를 불러옵니다.",
         "🌐 API 서버에 연결할 수 없거나 응답 시간이 초과되었습니다. 테스트용 기존 리포트 데이터를 불러옵니다.",
         "🔍 알 수 없는 에러가 발생했습니다: ",
         "기업",
         "직책",
         "점수",
         "점",
         "스펙비교",
         "우선순위",
         "사용자",
         "합격자 평균",
         "분석리포트",
         "개선 방안",
         "결론",
         "자기소개서"]
en_text = [
    "Check everything at once, from **competency diagnosis** tailored to your target company and role, to a **draft cover letter** for passing.",
    "📋 Input Application Information",
    "🎯 Target Company Name",
    "e.g., Naver, Kakao",
    "💼 Target Job/Role",
    "e.g., Backend Developer, Service Planning",
    "📁 Upload My Documents & Images",
    "Please attach the documents to be analyzed and converted into a cover letter. (Supports document and image files)",
    "📸 Image file has been loaded: ",
    "Preview Uploaded Image",
    "⚠️ An error occurred while displaying the image on the screen: ",
    "Display failed, but transmission for API analysis is still possible.",
    "📂 Document file has been loaded successfully:",
    "🚀 SpecFit AI Analysis & Cover Letter Recommendation",
    "You must enter both the target company and role to get an accurate, tailored cover letter.",
    "Analyzing and writing your tailored cover letter...",
    "✅ API precision diagnosis and cover letter generation completed!",
    "❌ The server did not return valid data (JSON).",
    "⚠️ API Server Error (Code: ",
    "). Loading local sample data.",
    "🌐 Unable to connect to the API server or connection timed out. Loading existing report data for testing.",
    "🔍 An unknown error has occurred: ",
    "Company",
    "Position",
    "Score",
    "Score",
    "Spec Comparison",
    "Priority",
    "User",
    "Accepted Applicants Average",
    "Analysis Report",
    "Improvement Plan",
    "Conclusion",
    "Cover Letter"
]
text_source = en_text if st.session_state.button_text  == "한글" else kr_text
st.title("SpecFit AI")
st.markdown(f"{text_source[0]}")

# 3. 사용자 입력 섹션
st.subheader(f"{text_source[1]}")
col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input(f"{text_source[2]}", placeholder=f"{text_source[3]}")
with col2:
    job_position = st.text_input(f"{text_source[4]}", placeholder=f"{text_source[5]}")

# 4. 파일 업로드 (tif, tiff 형식 추가)
st.subheader(f"{text_source[6]}")
uploaded_file = st.file_uploader(
    f"{text_source[7]}",
    type=["txt", "pdf", "docx", "png", "jpg", "jpeg", "tif", "tiff"]
)

# 5. 파일 처리 및 시각화
if uploaded_file is not None:
    file_extension = uploaded_file.name.split(".")[-1].lower()
    image_extensions = ["png", "jpg", "jpeg", "tif", "tiff"]

    if file_extension in image_extensions:
        st.info(f"{text_source[8]} {uploaded_file.name}")
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption=f"{text_source[9]}", use_container_width=True)
        except Exception as e:
            st.error(f"{text_source[10]} {e}")
            st.warning(f"{text_source[11]}")
    else:
        st.info(f"{text_source[12]} {uploaded_file.name}")

    # 6. 분석 및 자소서 생성 로직 구동
    if st.button(f"{text_source[13]}"):
        if not company_name or not job_position:
            st.warning(f"{text_source[14]}")
        else:
            analysis_report = None
            with st.spinner(f"⏳ {company_name} [{job_position}] {text_source[15]}"):
                try:
                    # 전송 데이터 구성
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {"company": company_name, "position": job_position}
                    headers = {"x-api-key": API_KEY}

                    # API 요청
                    response = requests.post(API_URL, files=files, data=data, headers=headers, timeout=120)

                    if response.status_code == 200:
                        try:
                            res = response.json()
                            if st.session_state.button_text == "한글":
                                analysis_report = res.get("translated_english") or res.get("analysis_report")
                                cover_letter=res.get("cover_letter")
                            else:
                                analysis_report = res.get("analysis_report")

                            if not isinstance(analysis_report, dict) or not analysis_report.get("summary"):
                                st.error(f"{text_source[17]}")
                                analysis_report = None
                            else:
                                st.success(f"{text_source[16]}")

                        except ValueError:
                            st.error(f"{text_source[17]}")
                    else:
                        error_detail = response.text[:200]
                        st.warning(
                            f"{text_source[18]}{response.status_code}). "
                            f"{error_detail or text_source[19]}"
                        )

                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                    st.warning(f"{text_source[20]}")
                    analysis_report = MOCK_ANALYSIS_REPORT
                    cover_letter=None
                except Exception as e:
                    st.error(f"{text_source[21]} {e}")

                if isinstance(analysis_report, dict):
                    company = analysis_report['target']['company']
                    position = analysis_report['target']['position']
                    fit_score_str = analysis_report['Fit_score']

                    # '60점' 문자열에서 숫자 추출
                    try:
                        score_value = int(re.sub(r'[^0-9]', '', fit_score_str))
                    except ValueError:
                        score_value = 0

                    col1, col2 = st.columns([0.6, 0.4])

                    with col1:
                        st.markdown(
                            f'<div class="size-largest" style="margin-top: 40px;">{text_source[22]} {company}, {text_source[23]} {position}<br> {text_source[24]} {fit_score_str}</div>',
                            unsafe_allow_html=True)

                    with col2:
                        # go.Indicator 내부 font 속성 수정 완료 ('fontfamily' -> 'family')
                        fig = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=score_value,
                            domain={'x': [0, 1], 'y': [0, 1]},
                            number={'suffix': f"{text_source[25]}",
                                    'font': {'color': '#1E3A8A', 'size': 32, 'family': 'sans-serif'}},
                            gauge={
                                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#1E3A8A"},
                                'bar': {'color': "#1E3A8A"},
                                'bgcolor': "#E2E8F0",
                                'borderwidth': 0,
                                'steps': [
                                    {'range': [0, 40], 'color': '#EFF6FF'},
                                    {'range': [40, 70], 'color': '#DBEAFE'},
                                    {'range': [70, 100], 'color': '#93C5FD'}
                                ],
                            }
                        ))

                        fig.update_layout(
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=160,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)'
                        )
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                    st.markdown('<div class="space-far"></div>', unsafe_allow_html=True)

                    # --- 스펙비교 영역 ---
                    st.markdown(f'<div class="size-large-bold">{text_source[26]}</div>', unsafe_allow_html=True)

                    for idx, q_gap in enumerate(analysis_report['quantitative_gaps']):
                        bg_class = "bg-blue-contrast" if idx % 2 == 1 else "bg-blue-light"

                        item = q_gap['item']
                        priority = q_gap['priority']
                        user_val = q_gap['user_value']
                        passed_avg = q_gap['passed_avg']
                        gap_val = q_gap['gap']
                        comment = q_gap['comment']

                        st.markdown(f"""
                        <div class="data-card {bg_class}">
                            <div class="size-normal space-close" style="font-weight: 600; color: #1E40AF;">{item}-{text_source[27]} {priority}</div>
                            <div class="size-normal space-close">{text_source[28]}: {user_val} &nbsp;&nbsp;|&nbsp;&nbsp; {text_source[29]}: {passed_avg}</div>
                            <div class="size-normal" style="color: #475569;">{gap_val} &middot; {comment}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    # --- 분석리포트 영역 ---
                    st.markdown(f'<div class="size-large-bold">{text_source[30]}</div>', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="size-normal summary-box">&bull; {analysis_report["summary"]}</div>',
                        unsafe_allow_html=True)

                    for idx, qual_gap in enumerate(analysis_report['qualitative_gaps']):
                        bg_class = "bg-blue-contrast" if idx % 2 == 1 else "bg-blue-light"

                        category = qual_gap['category']
                        analysis = qual_gap['analysis']
                        suggestion = qual_gap['suggestion']

                        st.markdown(f"""
                        <div class="data-card {bg_class}">
                            <div class="size-normal space-close" style="font-weight: 600; color: #1E40AF;">{category}</div>
                            <div class="size-normal" style="color: #334155;">{analysis} {suggestion}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    # --- 개선 방안 영역 ---
                    st.markdown(f'<div class="size-large-bold">{text_source[31]}</div>', unsafe_allow_html=True)

                    for action_item in analysis_report['priority_actions']:
                        action = action_item['action']
                        reason = action_item['reason']
                        effect = action_item['expected_effect']

                        st.markdown(f"""
                        <div class="data-card" style="background-color: #F8FAFC; border-left: 4px solid #1E3A8A;">
                            <div class="size-normal space-close" style="font-weight: bold; color: #1E3A8A;">{action}</div>
                            <div class="size-normal" style="color: #334155;">{reason} {effect}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    # --- 결론 영역 ---
                    st.markdown(f'<div class="size-large-bold">{text_source[32]}</div>', unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class="data-card" style="background-color: #EFF6FF; border: 1px dashed #3B82F6;">
                        <div class="size-normal" style="font-weight: 500; color: #1E40AF;">{analysis_report['encouragement']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(f'<div class="size-large-bold">{text_source[33]}</div>', unsafe_allow_html=True)
                    st.markdown(f"""
                                            <div class="data-card" style="background-color: #F8FAFC; border-left: 4px solid #1E3A8A;">
                                                <div class="size-normal" style="color: #334155;">{cover_letter}</div>
                                            </div>
                                            """, unsafe_allow_html=True)
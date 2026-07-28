import os
import re
import requests
import streamlit as st
import plotly.graph_objects as go
from PIL import Image
from streamlit_float import float_init, float_parent

float_init()

# 1. 페이지 설정
st.set_page_config(page_title="SpecFit AI — 스펙 비교 분석", page_icon="🎯", layout="wide")

# 2. React (TanStack Router) 기반 스타일을 구현한 커스텀 CSS
st.markdown("""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        
        * { font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif; }
        
        /* 기본 레이아웃 및 무채색 테마 */
        .stApp { background-color: #0F172A; color: #F8FAFC; }
        
        /* Streamlit 기본 사이드바 스타일링 */
        section[data-testid="stSidebar"] {
            background-color: #1E293B !important;
            border-right: 1px solid #334155 !important;
        }
        
        /* 사이드바 내부 텍스트 및 카드 */
        .sidebar-brand {
            font-size: 20px; font-weight: 700; color: #F8FAFC;
            display: flex; align-items: center; gap: 8px; margin-bottom: 24px;
        }
        .pro-card {
            background-color: rgba(51, 65, 85, 0.4); border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px; padding: 16px; margin-top: auto;
        }

        /* 입력 폼 및 메인 카드 컨테이너 */
        .main-card {
            background-color: #1E293B; border: 1px solid #334155;
            border-radius: 12px; padding: 24px; margin-bottom: 24px;
        }
        .card-title-lg { font-size: 18px; font-weight: 600; color: #F8FAFC; margin-bottom: 4px; }
        .card-sub-sm { font-size: 14px; color: #94A3B8; margin-bottom: 20px; }

        /* Streamlit 인풋 요소 커스텀 */
        .stTextInput > label, .stFileUploader > label {
            font-size: 12px !important; font-weight: 600 !important;
            color: #94A3B8 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important;
        }
        .stTextInput input {
            background-color: #0F172A !important; border: 1px solid #334155 !important;
            color: #F8FAFC !important; border-radius: 6px !important;
        }
        
        /* 분석 버튼 */
        div.stButton > button:first-child {
            background-color: #3B82F6 !important; color: #FFFFFF !important;
            border: none; border-radius: 6px; padding: 0.75rem 1.5rem;
            font-weight: 600; font-size: 14px; width: 100%; transition: all 0.2s;
        }
        div.stButton > button:first-child:hover { background-color: #2563EB !important; }

        /* 우선순위 뱃지 (React PriorityBadge 동일) */
        .badge-high { background-color: rgba(244, 63, 94, 0.2); color: #FDA4AF; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }
        .badge-mid { background-color: rgba(245, 158, 11, 0.2); color: #FDE68A; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }
        .badge-low { background-color: rgba(16, 185, 129, 0.2); color: #6EE7B7; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }

        /* 정량/정성 리포트 박스 */
        .report-summary-box {
            background-color: rgba(51, 65, 85, 0.5); border-radius: 8px;
            padding: 16px; font-size: 14px; color: #F8FAFC; line-height: 1.6; margin-bottom: 20px;
        }
        .qualitative-card {
            background-color: rgba(51, 65, 85, 0.3); border: 1px solid #334155;
            border-radius: 8px; padding: 16px; margin-bottom: 12px;
        }
        
        /* 자기소개서 문서 박스 */
        .cover-letter-paper {
            background-color: rgba(51, 65, 85, 0.4); border: 1px solid #334155;
            border-radius: 8px; padding: 20px; font-size: 14px; line-height: 1.8;
            color: #E2E8F0; white-space: pre-wrap;
        }
    </style>
""", unsafe_allow_html=True)

# 3. 환경 변수 및 Mock 설정
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

MOCK_COVER_LETTER = """저는 데이터 기반 문제 해결에 강점을 가진 지원자로서, 네이버의 백엔드 개발자 직무에 지원하게 되었습니다. 다양한 데이터 분석 및 머신러닝 프로젝트를 통해 대용량 데이터를 다루는 경험을 쌓았으며, 이러한 경험은 안정적이고 확장 가능한 서비스 구현에 밑거름이 될 것이라 확신합니다.

앞으로 Java와 Spring Framework에 대한 학습을 심화하여 백엔드 개발자로서의 역량을 완성하고, RESTful API 설계 및 데이터베이스 최적화 프로젝트를 통해 실무 감각을 확장해 나가겠습니다. 네이버의 서비스가 수많은 사용자에게 더 나은 경험을 제공할 수 있도록, 데이터와 시스템 양쪽 시야를 가진 개발자로 기여하고 싶습니다."""

# 5. 사이드바 (React Sidebar 구현)
with st.sidebar:
    st.markdown('<div class="sidebar-brand">📊 <span>SpecFit AI</span></div>', unsafe_allow_html=True)
    
    st.markdown("""
        <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px;">
            <div style="padding: 8px 12px; background-color: rgba(51,65,85,0.5); border-radius: 6px; font-weight: 600; font-size: 14px; color: #3B82F6;">📊 Market Dashboard</div>
            <div style="padding: 8px 12px; font-size: 14px; color: #94A3B8;">🗄️ Skill Repository</div>
            <div style="padding: 8px 12px; font-size: 14px; color: #94A3B8;">🎯 Target Mapping</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
        <div class="pro-card">
            <p style="font-size: 11px; font-weight: 700; color: #3B82F6; text-transform: uppercase; margin-bottom: 4px;">Pro Account</p>
            <p style="font-size: 13px; color: #CBD5E1; margin-bottom: 12px; line-height: 1.4;">합격자 벤치마크로 스펙을 진단하세요.</p>
            <button style="width: 100%; padding: 6px; background-color: #3B82F6; color: white; border: none; border-radius: 6px; font-size: 12px; font-weight: 600;">Upgrade Plan</button>
        </div>
    """, unsafe_allow_html=True)

# 6. 메인 헤더
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 1px solid #334155; margin-bottom: 24px;">
        <h2 style="font-size: 20px; font-weight: 600; color: #F8FAFC; margin:0;">스펙 비교 분석 · 자기소개서 추천</h2>
        <span style="font-size: 13px; background-color: #334155; padding: 6px 12px; border-radius: 6px; color: #F8FAFC;">🔗 Share Report</span>
    </div>
""", unsafe_allow_html=True)

# 7. 지원 정보 입력 섹션 (React Input Section)
st.markdown('<div class="card-title-lg">지원 정보 입력</div>', unsafe_allow_html=True)
st.markdown('<div class="card-sub-sm">지원 기업 및 직무 맞춤형 <b style="color:#F8FAFC;">역량 진단</b>부터 <b style="color:#F8FAFC;">자기소개서 초안</b>까지 한 번에 확인하세요.</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input("🎯 지원 기업명", placeholder="예: 네이버, 카카오")
with col2:
    job_position = st.text_input("💼 지원 직무", placeholder="예: 백엔드 개발자, 서비스 기획")

uploaded_file = st.file_uploader(
    "📁 내 문서 및 이미지 업로드",
    type=["txt", "pdf", "docx", "png", "jpg", "jpeg", "tif", "tiff"]
)

if uploaded_file is not None:
    file_extension = uploaded_file.name.split(".")[-1].lower()
    image_extensions = ["png", "jpg", "jpeg", "tif", "tiff"]

    if file_extension in image_extensions:
        st.info(f"📸 이미지 파일이 로드되었습니다: **{uploaded_file.name}**")
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="업로드 미리보기", width=250)
        except Exception as e:
            st.error(f"이미지 미리보기 실패: {e}")
    else:
        st.info(f"📂 문서 파일이 정상적으로 로드되었습니다: **{uploaded_file.name}**")

# 8. 분석 구동 및 백엔드 API 연동
st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)
if st.button("🚀 SpecFit AI 분석 및 자소서 추천"):
    if not company_name or not job_position:
        st.warning("지원 기업명과 직무를 모두 입력해야 정확한 맞춤 자소서가 나옵니다.")
    elif uploaded_file is None:
        st.warning("분석할 서류 파일을 첨부해 주세요.")
    else:
        analysis_report = None
        cover_letter = None

        with st.spinner(f"⏳ {company_name} [{job_position}] 맞춤 분석 및 자기소개서 작성 중..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"company": company_name, "position": job_position}
                headers = {"x-api-key": API_KEY}

                response = requests.post(API_URL, files=files, data=data, headers=headers, timeout=120)

                if response.status_code == 200:
                    res = response.json()
                    analysis_report = res.get("analysis_report") or res.get("translated_english")
                    cover_letter = res.get("cover_letter") or MOCK_COVER_LETTER
                    st.success("✅ API 정밀 진단 및 자기소개서 작성이 완료되었습니다!")
                else:
                    st.warning(f"⚠️ API 서버 오류 (코드: {response.status_code}). 예시 데이터를 불러옵니다.")
                    analysis_report = MOCK_ANALYSIS_REPORT
                    cover_letter = MOCK_COVER_LETTER

            except Exception as e:
                st.error(f"연결 오류 발생 ({e}). 예시 리포트 데이터를 표시합니다.")
                analysis_report = MOCK_ANALYSIS_REPORT
                cover_letter = MOCK_COVER_LETTER

        # 9. 결과 리포트 출력 (React Report Component 1:1 매핑)
        if isinstance(analysis_report, dict):
            company = analysis_report['target']['company']
            position = analysis_report['target']['position']
            fit_score_str = analysis_report['Fit_score']

            try:
                digits_only = re.sub(r'[^0-9]', '', str(fit_score_str))
                score_value = int(digits_only) if digits_only else 0
            except ValueError:
                score_value = 0

            # --- Score Header & Gauge ---
            st.markdown("<hr style='border:none; border-top:1px solid #334155; margin: 32px 0;'>", unsafe_allow_html=True)
            # 게이지 차트가 들어갈 왼쪽 컬럼 폭을 조금 더 늘려주고 간격을 여유있게 배치
            r_col1, r_col2 = st.columns([0.45, 0.55])

            with r_col1:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=score_value,
                    domain={'x': [0.05, 0.95], 'y': [0.05, 0.95]},
                    number={
                        'suffix': "점",
                        'font': {'color': '#F8FAFC', 'size': 26, 'family': 'Pretendard, sans-serif'}  # 폰트 크기를 32 -> 26으로 조절하여 짤림 방지
                    },
                    gauge={
                        'axis': {
                            'range': [0, 100],
                            'tickwidth': 1,
                            'tickcolor': "#475569",
                            'tickfont': {'size': 11, 'color': '#94A3B8'}  # 축 눈금 글자 크기 축소
                        },
                        'bar': {'color': "#3B82F6", 'thickness': 0.6},
                        'bgcolor': "#1E293B",
                        'borderwidth': 0,
                        'steps': [
                            {'range': [0, 40], 'color': 'rgba(244, 63, 94, 0.25)'},
                            {'range': [40, 70], 'color': 'rgba(245, 158, 11, 0.25)'},
                            {'range': [70, 100], 'color': 'rgba(16, 185, 129, 0.25)'}
                        ],
                    }
                ))
                
                # 여백(margin)과 높이(height)를 200px로 넉넉하게 지정하여 100% 확대 시에도 깨짐 방지
                fig.update_layout(
                    margin=dict(l=25, r=25, t=25, b=15),
                    height=190,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            with r_col2:
                st.markdown(f"""
                    <div style="padding-top: 20px;">
                        <span style="font-size: 11px; text-transform: uppercase; tracking-wider: 0.1em; color: #94A3B8;">TARGET</span>
                        <h2 style="font-size: 28px; font-weight: 500; color: #F8FAFC; margin: 4px 0;">
                            기업 <span style="color: #3B82F6;">{company}</span> &middot; 직책 <span style="color: #3B82F6;">{position}</span>
                        </h2>
                        <p style="font-size: 14px; color: #94A3B8;">종합 적합도 점수는 <b style="color: #F8FAFC;">{fit_score_str}</b> 입니다.</p>
                    </div>
                """, unsafe_allow_html=True)

            # --- 스펙 비교 테이블 ---
            st.markdown('<div class="card-title-lg" style="margin-top: 32px; margin-bottom: 16px;">스펙 비교</div>', unsafe_allow_html=True)
            
            # Table Header
            t_col1, t_col2, t_col3, t_col4 = st.columns([0.35, 0.25, 0.25, 0.15])
            t_col1.markdown("<span style='font-size:12px; font-weight:600; color:#94A3B8;'>항목</span>", unsafe_allow_html=True)
            t_col2.markdown("<span style='font-size:12px; font-weight:600; color:#94A3B8;'>사용자</span>", unsafe_allow_html=True)
            t_col3.markdown("<span style='font-size:12px; font-weight:600; color:#94A3B8;'>합격자 평균</span>", unsafe_allow_html=True)
            t_col4.markdown("<span style='font-size:12px; font-weight:600; color:#94A3B8;'>우선순위</span>", unsafe_allow_html=True)
            st.markdown("<hr style='border:none; border-top:1px solid #334155; margin: 8px 0 16px 0;'>", unsafe_allow_html=True)

            for g in analysis_report.get('quantitative_gaps', []):
                # 키가 존재하지 않을 때를 대비해 .get() 사용 및 기본값 부여
                item = g.get('item', '-')
                comment = g.get('comment') or g.get('analysis') or g.get('gap', '-')
                user_val = g.get('user_value') or g.get('user_val') or g.get('user') or '-'
                passed_avg = g.get('passed_avg') or g.get('avg') or g.get('target_avg') or '-'
                priority = g.get('priority', '중')

                c1, c2, c3, c4 = st.columns([0.35, 0.25, 0.25, 0.15])
                with c1:
                    st.markdown(f"<b style='font-size:14px; color:#F8FAFC;'>{item}</b><p style='font-size:12px; color:#94A3B8; margin-top:2px;'>{comment}</p>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<span style='font-size:14px; color:#E2E8F0;'>{user_val}</span>", unsafe_allow_html=True)
                with c3:
                    st.markdown(f"<span style='font-size:14px; color:#94A3B8;'>{passed_avg}</span>", unsafe_allow_html=True)
                with c4:
                    b_class = "badge-high" if priority == "상" else ("badge-mid" if priority == "중" else "badge-low")
                    st.markdown(f"<span class='{b_class}'>우선순위 {priority}</span>", unsafe_allow_html=True)
                st.markdown("<hr style='border:none; border-top:1px solid rgba(51,65,85,0.4); margin: 8px 0;'>", unsafe_allow_html=True)
                

            # --- 분석 리포트 ---
            st.markdown('<div class="card-title-lg" style="margin-top: 32px; margin-bottom: 12px;">분석 리포트</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="report-summary-box">&bull; {analysis_report["summary"]}</div>', unsafe_allow_html=True)

            q_col1, q_col2 = st.columns(2)
            for idx, q in enumerate(analysis_report.get('qualitative_gaps', [])):
                category = q.get('category', '분석 항목')
                analysis = q.get('analysis', '')
                suggestion = q.get('suggestion', '')
                
                target_col = q_col1 if idx % 2 == 0 else q_col2
                with target_col:
                    st.markdown(f"""
                        <div class="qualitative-card">
                            <p style="font-size:14px; font-weight:600; color:#3B82F6; margin-bottom:6px;">{category}</p>
                            <p style="font-size:13.5px; color:#F8FAFC; line-height:1.5; margin-bottom:8px;">{analysis}</p>
                            <p style="font-size:12px; color:#94A3B8; line-height:1.4;">💡 {suggestion}</p>
                        </div>
                    """, unsafe_allow_html=True)

            # --- 개선 방안 ---
            st.markdown('<div class="card-title-lg" style="margin-top: 32px; margin-bottom: 16px;">개선 방안</div>', unsafe_allow_html=True)
            for action in analysis_report['priority_actions']:
                st.markdown(f"""
                    <div style="display:flex; gap:16px; background-color:rgba(51,65,85,0.2); border:1px solid #334155; border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="width:32px; height:32px; border-radius:50%; background-color:#3B82F6; color:white; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; shrink-0;">
                            {str(action['rank']).zfill(2)}
                        </div>
                        <div>
                            <p style="font-size:14px; font-weight:600; color:#F8FAFC; margin-bottom:4px;">{action['action']}</p>
                            <p style="font-size:12px; color:#CBD5E1; margin-bottom:2px;">{action['reason']}</p>
                            <p style="font-size:12px; color:#94A3B8;">기대 효과 &middot; {action['expected_effect']}</p>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            # --- 결론 ---
            st.markdown('<div class="card-title-lg" style="margin-top: 32px; margin-bottom: 12px;">결론</div>', unsafe_allow_html=True)
            st.markdown(f"""
                <div style="background-color:rgba(59,130,246,0.1); border:1px dashed #3B82F6; border-radius:8px; padding:16px; font-size:14px; color:#F8FAFC; line-height:1.6;">
                    {analysis_report['encouragement']}
                </div>
            """, unsafe_allow_html=True)

            # --- 자기소개서 ---
            if cover_letter:
                st.markdown('<div class="card-title-lg" style="margin-top: 32px; margin-bottom: 12px;">자기소개서</div>', unsafe_allow_html=True)
                st.markdown(f"""
                    <div class="cover-letter-paper">
{cover_letter}
                    </div>
                """, unsafe_allow_html=True)
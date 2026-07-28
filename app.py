import base64
import io
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from streamlit_float import float_init


# set_page_config는 첫 Streamlit 명령이어야 합니다.
st.set_page_config(
    page_title="SpecFit AI — 스펙 비교 분석",
    page_icon="🎯",
    layout="wide",
)
float_init()

# 현재 팀 UI CSS를 그대로 유지합니다.
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

        /* 우선순위 뱃지 */
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

# 기존 분석 API와 새 파일 번역 API
API_KEY = os.getenv(
    "API_KEY_CREDENTIAL",
    os.getenv("API_KEY", "specfit-secret-key"),
)
API_URL = os.getenv(
    "API_URL",
    "http://localhost:8000/api/analyze",
)
DEFAULT_API_BASE = (
    API_URL.rsplit("/api/", 1)[0]
    if "/api/" in API_URL
    else "http://localhost:8000"
)
TRANSLATE_API_URL = os.getenv(
    "TRANSLATE_API_URL",
    f"{DEFAULT_API_BASE}/api/translate-file",
)


def _extract_docx_preview(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
    except (KeyError, OSError, ValueError, zipfile.BadZipFile):
        return ""

    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(
            node.text or ""
            for node in paragraph.findall(".//w:t", namespace)
        )
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _show_translated_resume_preview(translated_resume: dict) -> None:
    content = translated_resume["content"]
    suffix = Path(translated_resume["filename"]).suffix.lower()

    st.markdown(
        '<div class="card-title-lg" style="margin-top:20px;">'
        "웹 미리보기</div>",
        unsafe_allow_html=True,
    )

    if suffix == ".txt":
        st.text_area(
            "번역 결과",
            value=content.decode("utf-8-sig", errors="replace"),
            height=420,
            disabled=True,
            key="translated_txt_preview",
        )
        return

    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        st.image(content, caption="번역 이미지", use_container_width=True)
        return

    if suffix == ".pdf":
        if len(content) > 20 * 1024 * 1024:
            st.info("20MB를 초과한 PDF는 다운로드로 확인해 주세요.")
            return
        encoded_pdf = base64.b64encode(content).decode("ascii")
        components.html(
            f'<iframe src="data:application/pdf;base64,{encoded_pdf}" '
            'width="100%" height="760" style="border:0;"></iframe>',
            height=780,
            scrolling=True,
        )
        return

    if suffix == ".docx":
        preview_text = _extract_docx_preview(content)
        if preview_text:
            st.text_area(
                "번역 결과",
                value=preview_text,
                height=520,
                disabled=True,
                key="translated_docx_preview",
            )
            st.caption(
                "DOCX 웹 미리보기는 텍스트 확인용이며, 원본 배치는 "
                "다운로드한 파일에서 확인할 수 있습니다."
            )
        else:
            st.info("DOCX 미리보기를 생성하지 못했습니다. 다운로드로 확인해 주세요.")
        return

    st.info(
        "이 형식은 브라우저 미리보기를 지원하지 않습니다. "
        "다운로드한 파일로 확인해 주세요."
    )

MOCK_ANALYSIS_REPORT = {
    "target": {"company": "네이버", "position": "백엔드 개발자"},
    "summary": (
        "사용자의 현재 스펙은 데이터/AI 엔지니어 역량을 갖추고 있으나, "
        "백엔드 개발자로 전환하기 위해 일부 기술적 보완이 필요합니다."
    ),
    "quantitative_gaps": [
        {
            "item": "어학 점수",
            "user_value": "TOEFL 95 / TEPS 340",
            "passed_avg": "없음 (비교 대상 없음)",
            "gap": "해당 정보가 없어 비교 불가능",
            "priority": "중",
            "comment": "충분한 비교 데이터가 필요합니다.",
        },
        {
            "item": "관련 자격증",
            "user_value": "ADsP, SQLD, 정보보안기사",
            "passed_avg": "없음 (비교 대상 없음)",
            "gap": "해당 정보가 없어 비교 불가능",
            "priority": "중",
            "comment": "직무 관련 자격과 프로젝트 경험을 함께 보완하세요.",
        },
    ],
    "qualitative_gaps": [
        {
            "category": "기술 스택의 일치 여부",
            "analysis": "Java와 Spring 등 백엔드 기술 보완이 필요합니다.",
            "suggestion": "학습 결과를 포트폴리오 프로젝트에 반영하세요.",
        },
        {
            "category": "실제 프로젝트 경험",
            "analysis": "백엔드 직무와 직접 연결되는 프로젝트가 부족합니다.",
            "suggestion": "REST API와 데이터베이스 최적화 프로젝트를 추가하세요.",
        },
    ],
    "priority_actions": [
        {
            "rank": 1,
            "action": "Java 및 Spring Framework 학습 시작",
            "reason": "백엔드 개발 직무의 핵심 기술입니다.",
            "expected_effect": "직무 적합도와 면접 대응력이 높아집니다.",
        }
    ],
    "Fit_score": "60점",
    "encouragement": "목표 직무에 맞춘 기술과 프로젝트를 구체적으로 보완하세요.",
}

MOCK_COVER_LETTER = """저는 데이터 기반 문제 해결 경험을 바탕으로 백엔드 개발자 직무에 지원했습니다.

앞으로 Java와 Spring Framework 학습을 심화하고 REST API 설계 및 데이터베이스 최적화 경험을 쌓아, 안정적인 서비스 구현에 기여하겠습니다."""

# 현재 사이드바 UI 유지
with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand">📊 <span>SpecFit AI</span></div>',
        unsafe_allow_html=True,
    )
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

# 현재 메인 헤더 UI 유지
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 1px solid #334155; margin-bottom: 24px;">
        <h2 style="font-size: 20px; font-weight: 600; color: #F8FAFC; margin:0;">스펙 비교 분석 · 자기소개서 추천</h2>
        <span style="font-size: 13px; background-color: #334155; padding: 6px 12px; border-radius: 6px; color: #F8FAFC;">🔗 Share Report</span>
    </div>
""", unsafe_allow_html=True)

# 현재 지원 정보 UI 유지
st.markdown(
    '<div class="card-title-lg">지원 정보 입력</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="card-sub-sm">지원 기업 및 직무 맞춤형 '
    '<b style="color:#F8FAFC;">역량 진단</b>부터 '
    '<b style="color:#F8FAFC;">자기소개서 초안</b>까지 한 번에 확인하세요.</div>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input(
        "🎯 지원 기업명",
        placeholder="예: 네이버, 카카오",
    )
with col2:
    job_position = st.text_input(
        "💼 지원 직무",
        placeholder="예: 백엔드 개발자, 서비스 기획",
    )

uploaded_file = st.file_uploader(
    "📁 내 문서 및 이미지 업로드",
    type=[
        "txt",
        "pdf",
        "docx",
        "png",
        "jpg",
        "jpeg",
        "tif",
        "tiff",
    ],
    key="analysis_file",
)

if uploaded_file is not None:
    file_extension = Path(uploaded_file.name).suffix.lower()
    image_extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

    if file_extension in image_extensions:
        st.info(f"📸 이미지 파일이 로드되었습니다: **{uploaded_file.name}**")
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="업로드 미리보기", width=250)
        except Exception as exc:
            st.error(f"이미지 미리보기 실패: {exc}")
    else:
        st.info(
            f"📂 문서 파일이 정상적으로 로드되었습니다: "
            f"**{uploaded_file.name}**"
        )

# 기존 분석 버튼과 결과 UI 유지
st.markdown(
    "<div style='margin-top: 16px;'></div>",
    unsafe_allow_html=True,
)
if st.button(
    "🚀 SpecFit AI 분석 및 자소서 추천",
    key="analyze_button",
):
    if not company_name or not job_position:
        st.warning(
            "지원 기업명과 직무를 모두 입력해야 정확한 맞춤 자소서가 나옵니다."
        )
    elif uploaded_file is None:
        st.warning("분석할 서류 파일을 첨부해 주세요.")
    else:
        with st.spinner(
            f"⏳ {company_name} [{job_position}] "
            "맞춤 분석 및 자기소개서 작성 중..."
        ):
            try:
                response = requests.post(
                    API_URL,
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type,
                        )
                    },
                    data={
                        "company": company_name,
                        "position": job_position,
                    },
                    headers={"x-api-key": API_KEY},
                    timeout=180,
                )

                if response.status_code == 200:
                    result = response.json()
                    analysis_report = result.get("analysis_report")
                    cover_letter = (
                        result.get("cover_letter") or MOCK_COVER_LETTER
                    )
                    if not isinstance(analysis_report, dict):
                        raise ValueError("analysis_report 형식이 올바르지 않습니다.")
                    st.success(
                        "✅ API 정밀 진단 및 자기소개서 작성이 완료되었습니다!"
                    )
                else:
                    st.warning(
                        f"⚠️ API 서버 오류 (코드: {response.status_code}). "
                        "예시 데이터를 불러옵니다."
                    )
                    analysis_report = MOCK_ANALYSIS_REPORT
                    cover_letter = MOCK_COVER_LETTER

            except Exception as exc:
                st.error(
                    f"연결 오류 발생 ({exc}). "
                    "예시 리포트 데이터를 표시합니다."
                )
                analysis_report = MOCK_ANALYSIS_REPORT
                cover_letter = MOCK_COVER_LETTER

        if isinstance(analysis_report, dict):
            company = analysis_report["target"]["company"]
            position = analysis_report["target"]["position"]
            fit_score_str = analysis_report["Fit_score"]

            digits_only = re.sub(
                r"[^0-9]",
                "",
                str(fit_score_str),
            )
            score_value = int(digits_only) if digits_only else 0

            st.markdown(
                "<hr style='border:none; border-top:1px solid #334155; "
                "margin: 32px 0;'>",
                unsafe_allow_html=True,
            )
            r_col1, r_col2 = st.columns([0.45, 0.55])

            with r_col1:
                fig = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=score_value,
                        domain={"x": [0.05, 0.95], "y": [0.05, 0.95]},
                        number={
                            "suffix": "점",
                            "font": {
                                "color": "#F8FAFC",
                                "size": 26,
                                "family": "Pretendard, sans-serif",
                            },
                        },
                        gauge={
                            "axis": {
                                "range": [0, 100],
                                "tickwidth": 1,
                                "tickcolor": "#475569",
                                "tickfont": {
                                    "size": 11,
                                    "color": "#94A3B8",
                                },
                            },
                            "bar": {
                                "color": "#3B82F6",
                                "thickness": 0.6,
                            },
                            "bgcolor": "#1E293B",
                            "borderwidth": 0,
                            "steps": [
                                {
                                    "range": [0, 40],
                                    "color": "rgba(244,63,94,0.25)",
                                },
                                {
                                    "range": [40, 70],
                                    "color": "rgba(245,158,11,0.25)",
                                },
                                {
                                    "range": [70, 100],
                                    "color": "rgba(16,185,129,0.25)",
                                },
                            ],
                        },
                    )
                )
                fig.update_layout(
                    margin={"l": 25, "r": 25, "t": 25, "b": 15},
                    height=190,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )

            with r_col2:
                st.markdown(f"""
                    <div style="padding-top: 20px;">
                        <span style="font-size: 11px; text-transform: uppercase; tracking-wider: 0.1em; color: #94A3B8;">TARGET</span>
                        <h2 style="font-size: 28px; font-weight: 500; color: #F8FAFC; margin: 4px 0;">
                            기업 <span style="color: #3B82F6;">{company}</span> · 직책 <span style="color: #3B82F6;">{position}</span>
                        </h2>
                        <p style="font-size: 14px; color: #94A3B8;">종합 적합도 점수는 <b style="color: #F8FAFC;">{fit_score_str}</b> 입니다.</p>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown(
                '<div class="card-title-lg" style="margin-top: 32px; '
                'margin-bottom: 16px;">스펙 비교</div>',
                unsafe_allow_html=True,
            )
            t_col1, t_col2, t_col3, t_col4 = st.columns(
                [0.35, 0.25, 0.25, 0.15]
            )
            t_col1.markdown(
                "<span style='font-size:12px;font-weight:600;"
                "color:#94A3B8;'>항목</span>",
                unsafe_allow_html=True,
            )
            t_col2.markdown(
                "<span style='font-size:12px;font-weight:600;"
                "color:#94A3B8;'>사용자</span>",
                unsafe_allow_html=True,
            )
            t_col3.markdown(
                "<span style='font-size:12px;font-weight:600;"
                "color:#94A3B8;'>합격자 평균</span>",
                unsafe_allow_html=True,
            )
            t_col4.markdown(
                "<span style='font-size:12px;font-weight:600;"
                "color:#94A3B8;'>우선순위</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<hr style='border:none;border-top:1px solid #334155;"
                "margin:8px 0 16px 0;'>",
                unsafe_allow_html=True,
            )

            for gap in analysis_report.get("quantitative_gaps", []):
                item = gap.get("item", "-")
                comment = (
                    gap.get("comment")
                    or gap.get("analysis")
                    or gap.get("gap", "-")
                )
                user_value = (
                    gap.get("user_value")
                    or gap.get("user_val")
                    or gap.get("user")
                    or "-"
                )
                passed_average = (
                    gap.get("passed_avg")
                    or gap.get("avg")
                    or gap.get("target_avg")
                    or "-"
                )
                priority = gap.get("priority", "중")

                c1, c2, c3, c4 = st.columns(
                    [0.35, 0.25, 0.25, 0.15]
                )
                c1.markdown(
                    f"<b style='font-size:14px;color:#F8FAFC;'>{item}</b>"
                    f"<p style='font-size:12px;color:#94A3B8;"
                    f"margin-top:2px;'>{comment}</p>",
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f"<span style='font-size:14px;color:#E2E8F0;'>"
                    f"{user_value}</span>",
                    unsafe_allow_html=True,
                )
                c3.markdown(
                    f"<span style='font-size:14px;color:#94A3B8;'>"
                    f"{passed_average}</span>",
                    unsafe_allow_html=True,
                )
                badge_class = (
                    "badge-high"
                    if priority == "상"
                    else "badge-mid"
                    if priority == "중"
                    else "badge-low"
                )
                c4.markdown(
                    f"<span class='{badge_class}'>"
                    f"우선순위 {priority}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<hr style='border:none;border-top:1px solid "
                    "rgba(51,65,85,0.4);margin:8px 0;'>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div class="card-title-lg" style="margin-top:32px;'
                'margin-bottom:12px;">분석 리포트</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="report-summary-box">• '
                f'{analysis_report["summary"]}</div>',
                unsafe_allow_html=True,
            )

            q_col1, q_col2 = st.columns(2)
            for index, gap in enumerate(
                analysis_report.get("qualitative_gaps", [])
            ):
                target_column = q_col1 if index % 2 == 0 else q_col2
                with target_column:
                    st.markdown(f"""
                        <div class="qualitative-card">
                            <p style="font-size:14px; font-weight:600; color:#3B82F6; margin-bottom:6px;">{gap.get("category", "분석 항목")}</p>
                            <p style="font-size:13.5px; color:#F8FAFC; line-height:1.5; margin-bottom:8px;">{gap.get("analysis", "")}</p>
                            <p style="font-size:12px; color:#94A3B8; line-height:1.4;">💡 {gap.get("suggestion", "")}</p>
                        </div>
                    """, unsafe_allow_html=True)

            st.markdown(
                '<div class="card-title-lg" style="margin-top:32px;'
                'margin-bottom:16px;">개선 방안</div>',
                unsafe_allow_html=True,
            )
            for action in analysis_report.get("priority_actions", []):
                st.markdown(f"""
                    <div style="display:flex; gap:16px; background-color:rgba(51,65,85,0.2); border:1px solid #334155; border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="width:32px; height:32px; border-radius:50%; background-color:#3B82F6; color:white; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700;">
                            {str(action.get("rank", "")).zfill(2)}
                        </div>
                        <div>
                            <p style="font-size:14px; font-weight:600; color:#F8FAFC; margin-bottom:4px;">{action.get("action", "")}</p>
                            <p style="font-size:12px; color:#CBD5E1; margin-bottom:2px;">{action.get("reason", "")}</p>
                            <p style="font-size:12px; color:#94A3B8;">기대 효과 · {action.get("expected_effect", "")}</p>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown(
                '<div class="card-title-lg" style="margin-top:32px;'
                'margin-bottom:12px;">결론</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"""
                <div style="background-color:rgba(59,130,246,0.1); border:1px dashed #3B82F6; border-radius:8px; padding:16px; font-size:14px; color:#F8FAFC; line-height:1.6;">
                    {analysis_report.get("encouragement", "")}
                </div>
            """, unsafe_allow_html=True)

            if cover_letter:
                st.markdown(
                    '<div class="card-title-lg" style="margin-top:32px;'
                    'margin-bottom:12px;">자기소개서</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"""
                    <div class="cover-letter-paper">
{cover_letter}
                    </div>
                """, unsafe_allow_html=True)

# 새 기능만 기존 UI 아래에 추가
st.markdown(
    "<hr style='border:none;border-top:1px solid #334155;"
    "margin:32px 0;'>",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="card-title-lg">영문 이력서 파일 만들기</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="card-sub-sm">원본 파일의 형식을 유지한 영문 이력서를 생성합니다.</div>',
    unsafe_allow_html=True,
)

translation_file = st.file_uploader(
    "📁 영문으로 번역할 이력서 업로드",
    type=[
        "txt",
        "docx",
        "pptx",
        "xlsx",
        "pdf",
        "hwp",
        "jpg",
        "jpeg",
        "png",
        "tif",
        "tiff",
    ],
    key="resume_translation_file",
)

if translation_file is not None:
    if st.button(
        "🌐 영문 이력서 파일 생성",
        key="translate_resume_button",
    ):
        with st.spinner(
            "파일 번역 중입니다. 문서는 수 분이 걸릴 수 있습니다."
        ):
            try:
                response = requests.post(
                    TRANSLATE_API_URL,
                    files={
                        "file": (
                            translation_file.name,
                            translation_file.getvalue(),
                            translation_file.type,
                        )
                    },
                    data={"source": "auto", "target": "en"},
                    headers={"x-api-key": API_KEY},
                    timeout=360,
                )

                if response.status_code == 200:
                    encoded_name = response.headers.get(
                        "X-Translated-Filename",
                        "",
                    )
                    if encoded_name:
                        output_name = unquote(encoded_name)
                    else:
                        source_path = Path(translation_file.name)
                        output_name = (
                            f"{source_path.stem}_en"
                            f"{source_path.suffix.lower()}"
                        )

                    st.session_state.translated_resume = {
                        "content": response.content,
                        "filename": output_name,
                        "media_type": (
                            response.headers.get(
                                "Content-Type",
                                "application/octet-stream",
                            ).split(";", 1)[0]
                        ),
                        "source_name": translation_file.name,
                    }
                    st.success("영문 이력서 파일 생성이 완료되었습니다.")
                else:
                    st.session_state.pop("translated_resume", None)
                    st.error(
                        "파일 번역 실패 "
                        f"(HTTP {response.status_code}): "
                        f"{response.text[:500]}"
                    )

            except requests.exceptions.Timeout:
                st.error("파일 번역 요청 시간이 초과되었습니다.")
            except requests.exceptions.ConnectionError:
                st.error("파일 번역 API 서버에 연결할 수 없습니다.")
            except Exception as exc:
                st.error(f"파일 번역 중 오류가 발생했습니다: {exc}")

translated_resume = st.session_state.get("translated_resume")
if (
    translated_resume
    and translation_file is not None
    and translated_resume.get("source_name") == translation_file.name
):
    st.download_button(
        label="⬇️ 영문 이력서 다운로드",
        data=translated_resume["content"],
        file_name=translated_resume["filename"],
        mime=translated_resume["media_type"],
        key="download_translated_resume",
    )
    _show_translated_resume_preview(translated_resume)
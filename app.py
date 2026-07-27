import os
import re

import plotly.graph_objects as go
import requests
import streamlit as st
from PIL import Image
from streamlit_float import float_init, float_parent


st.set_page_config(page_title="SpecFit AI", page_icon="🤖", layout="centered")
float_init()

API_KEY = os.getenv("API_KEY", "specfit-secret-key")
API_URL = os.getenv(
    "BACKEND_API_URL",
    "http://localhost:8000/api/analyze",
)

UI_TEXT = {
    "ko": {
        "intro": "지원 기업 및 직무 맞춤형 역량 진단 결과를 확인하세요.",
        "input": "📋 지원 정보 입력",
        "company": "🎯 지원 기업명",
        "company_placeholder": "예: 네이버, 카카오",
        "position": "💼 지원 직무",
        "position_placeholder": "예: 백엔드 개발자",
        "upload": "📁 내 문서 및 이미지 업로드",
        "upload_help": "분석할 TXT, PDF 또는 이미지 파일을 첨부해 주세요.",
        "analyze": "🚀 SpecFit AI 분석",
        "working": "맞춤 분석을 진행하고 있습니다...",
        "complete": "분석이 완료되었습니다.",
        "comparison": "스펙 비교",
        "report": "분석 리포트",
        "actions": "개선 방안",
        "conclusion": "결론",
        "user": "사용자",
        "average": "합격자 평균",
        "priority": "우선순위",
        "api_error": "API 요청에 실패했습니다.",
    },
    "en": {
        "intro": "Review a competency analysis tailored to your target role.",
        "input": "📋 Application Information",
        "company": "🎯 Target Company",
        "company_placeholder": "e.g., NAVER, Kakao",
        "position": "💼 Target Role",
        "position_placeholder": "e.g., Backend Developer",
        "upload": "📁 Upload Documents and Images",
        "upload_help": "Attach a TXT, PDF, or image file for analysis.",
        "analyze": "🚀 Analyze with SpecFit AI",
        "working": "Running your tailored analysis...",
        "complete": "Analysis completed.",
        "comparison": "Qualification Comparison",
        "report": "Analysis Report",
        "actions": "Priority Actions",
        "conclusion": "Conclusion",
        "user": "Applicant",
        "average": "Accepted Applicant Average",
        "priority": "Priority",
        "api_error": "The API request failed.",
    },
}

if "english_mode" not in st.session_state:
    st.session_state.english_mode = False
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

language_container = st.container()
with language_container:
    st.session_state.english_mode = st.toggle(
        "English",
        value=st.session_state.english_mode,
    )
    float_parent(
        css="position: fixed; bottom: 30px; right: 30px; z-index: 9999;"
    )

language = "en" if st.session_state.english_mode else "ko"
text = UI_TEXT[language]

st.title("SpecFit AI")
st.markdown(text["intro"])
st.subheader(text["input"])

col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input(
        text["company"],
        placeholder=text["company_placeholder"],
    )
with col2:
    job_position = st.text_input(
        text["position"],
        placeholder=text["position_placeholder"],
    )

st.subheader(text["upload"])
uploaded_file = st.file_uploader(
    text["upload_help"],
    type=["txt", "pdf", "png", "jpg", "jpeg", "tif", "tiff"],
)

if uploaded_file is not None:
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension in {"png", "jpg", "jpeg", "tif", "tiff"}:
        try:
            st.image(
                Image.open(uploaded_file),
                caption=uploaded_file.name,
                use_container_width=True,
            )
        except Exception as exc:
            st.warning(str(exc))
    else:
        st.info(uploaded_file.name)

    if st.button(text["analyze"]):
        if not company_name or not job_position:
            st.warning("기업명과 직무를 모두 입력해 주세요.")
        else:
            with st.spinner(text["working"]):
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
                        headers={
                            "X-API-Key": API_KEY,
                            "Accept": "application/json",
                        },
                        timeout=180,
                    )
                    response.raise_for_status()
                    st.session_state.analysis_result = response.json()
                    st.success(text["complete"])
                except requests.RequestException as exc:
                    st.error(f'{text["api_error"]} {exc}')
                except ValueError:
                    st.error("서버가 올바른 JSON을 반환하지 않았습니다.")

result = st.session_state.analysis_result
if isinstance(result, dict):
    korean_report = result.get("analysis_report", {})
    english_report = result.get("translated_english", {})

    report = (
        english_report
        if st.session_state.english_mode and english_report
        else korean_report
    )

    if not report:
        st.warning("표시할 분석 결과가 없습니다.")
        st.stop()

    target = report.get("target", korean_report.get("target", {}))
    fit_score = str(report.get("Fit_score", "0"))
    score_match = re.search(r"\d+", fit_score)
    score_value = int(score_match.group()) if score_match else 0

    st.caption(
        f'{target.get("company", company_name)} · '
        f'{target.get("position", job_position)}'
    )

    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score_value,
            number={"suffix": " points" if language == "en" else "점"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#1E3A8A"},
                "steps": [
                    {"range": [0, 40], "color": "#EFF6FF"},
                    {"range": [40, 70], "color": "#DBEAFE"},
                    {"range": [70, 100], "color": "#93C5FD"},
                ],
            },
        )
    )
    figure.update_layout(
        height=180,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.subheader(text["comparison"])
    for gap in report.get("quantitative_gaps", []):
        st.markdown(
            f'**{gap.get("item", "")} · '
            f'{text["priority"]} {gap.get("priority", "")}**'
        )
        st.write(
            f'{text["user"]}: {gap.get("user_value", "")} | '
            f'{text["average"]}: {gap.get("passed_avg", "")}'
        )
        st.caption(f'{gap.get("gap", "")} · {gap.get("comment", "")}')

    st.subheader(text["report"])
    st.info(report.get("summary", ""))
    for gap in report.get("qualitative_gaps", []):
        st.markdown(
            f'**{gap.get("category") or gap.get("item", "")}**'
        )
        st.write(gap.get("analysis", ""))
        st.success(gap.get("suggestion", ""))

    st.subheader(text["actions"])
    for action in report.get("priority_actions", []):
        with st.expander(
            f'{action.get("rank", "-")}. {action.get("action", "")}'
        ):
            st.write(action.get("reason", ""))
            st.write(action.get("expected_effect", ""))

    st.subheader(text["conclusion"])
    st.info(report.get("encouragement", ""))
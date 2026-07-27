import os
import re
import json
import logging
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("CLOVA_STUDIO_API_KEY")
BASE_URL = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005"
REQUEST_TIMEOUT = 60


class LLMCallError(Exception):
    """CLOVA Studio API 호출/파싱 관련 예외를 나타내는 커스텀 예외."""
    pass


# ====================== 시스템 프롬프트 (모듈 레벨 상수) ======================

GAP_ANALYSIS_SYSTEM_PROMPT = """당신은 취업 스펙 분석 전문 AI입니다.
사용자가 목표로 하는 기업과 직무에 대해, 사용자의 현재 스펙과 해당 기업/직무에 실제 합격한 사람들의 스펙을 비교 분석합니다.

분석 시 다음을 반드시 포함하세요:
1. 정량적 갭 분석 (학점, 어학점수, 자격증 개수, 인턴/프로젝트 경험 수 등)
2. 정성적 갭 분석 (경험의 질, 관련성, 스토리텔링, 키워드 매칭 등)
3. 부족한 점과 그 우선순위
4. 구체적으로 어떻게 보완해야 하는지에 대한 실행 로드맵 제안

Gap 필드 작성 원칙 (반드시 '지원자 관점의 부족분' 기준):
- 주어는 항상 '지원자'입니다. 지원자가 부족한 점을 명확한 단어로 서술하세요.
- 잘못된 예: "모두 있음", "동일함" (맥락에 맞지 않는 단어 사용 금지)
- 올바른 예: "실무 경험 미보유(1회 이상 필요)", "전공 관련 기사 자격증 미보유"

정량적 gap을 작성할 때 아래 규칙을 반드시 준수할 것:
- 숫자로 비교 가능한 항목(학점, 토익, OPIc 등) → 수치 차이와 함께 표기 (예: "3.2 / 3.7 (0.5 부족)", "750점 / 850점 (100점 부족)")
- OPIC 등급 순서: [AL > IH > IM3 > IM2 > IM1 > IL]
- 자격증, 수상, 인턴 등 비수치/건수 항목의 유무는 무슨 차이가 있는지 요약하고 퍼센트(%)는 사용하지말것.
- 모든 수치 데이터에는 반드시 단위(점, 개, 학점 등)를 포함하여 작성할것. (예: "900" (X) → "900점" (O))
- 여러 스펙을 한 칸에 합성해서 쓰지 마세요. 만약 여러 어학 점수가 있다면 항목을 나누거나, "토익 900점 / 오픽 IH"처럼 명확한 구분자와 함께 작성하세요.

정성적 gap을 작성할 때 아래 규칙을 준수할 것:
-교육 과정의 실무성(부트캠프/기업연수/어학연수)과 최종 프로젝트/성과물의 깊이를 평가.
-단순히 수상 유무가 아니라 [수상의 규모(전국/교내/기업주관)]와 [목표 직무와의 직접적 연관성]을 기준으로 평가하세요.

중요: JSON의 모든 값(value)은 반드시 문자열(쌍따옴표로 감싸기)로 작성하세요.
숫자도 "850", "3.5"처럼 문자열로 쓰고, "1회", "3~4회" 같은 표현도 반드시 쌍따옴표로 감싸세요.
답변은 반드시 아래 JSON 형식으로만 출력하세요. JSON 외의 다른 텍스트는 절대 포함하지 마세요.

{
  "target": {
    "company": "목표 기업",
    "position": "목표 직무"
  },
  "summary": "전체 분석 결과를 정리및 분석해서 요약한 설명",
  "quantitative_gaps": [
    {
      "item": "항목명",
      "user_value": "사용자 수치 또는 상태",
      "passed_avg": "합격자 평균 또는 상태",
      "gap": "차이 설명",
      "priority": "상/중/하",
      "comment": "간단한 코멘트"
    }
  ],
  "qualitative_gaps": [
    {
      "category": "정성 분석 항목 (예: 수상 경력의 실무 연관성, 교육 과정의 깊이, 프로젝트 성과 지표 등)",
      "analysis": "합격자 대비 질적 차이 분석 (왜, 어떤 점에서 부족한지)",
      "suggestion": "경험의 질 및 스토리텔링 보완 전략 (단순 경험 추가가 아닌 퀄리티적 디벨롭 방향)"
    }
  ],
  "priority_actions": [
    {
      "rank": 1,
      "action": "당장 해야 할 구체적 행동",
      "reason": "이 행동이 중요한 이유",
      "expected_effect": "행동 달성시 기대되는 효과"
    }
  ],
  "Fit_score": "합격자와 비교해 목표 기업에 합격할 수 있는 객관적인 확률에 대한 점수 (0~100 점)",
  "encouragement": "사용자에 대한 현실적이면서도 동기부여가 되는 격려 메시지"
}"""

COVER_LETTER_SYSTEM_PROMPT = """당신은 취업 자기소개서 작성 전문 AI입니다.
사용자의 스펙과 지원 기업/직무에 맞춰 설득력 있는 자기소개서 초안을 작성할것.

작성 원칙:
- 지원동기, 직무 관련 경험, 입사 후 포부를 자연스럽게 연결할 것
- 과장하지 말고, 감정이나 태도 대신 '실제 취한 행동'과 '구체적 사실'로 역량을 증명하세요.
- 간결하고 명확한 두괄식 문장 구조 사용
- 400~700자 내외의 완결된 자기소개서 형태로 작성할 것
- 본문 마지막은 반드시 직무 기여 다짐이나 성장 포부를 담은 일반 문장(~겠습니다, ~하고자 합니다)으로 깔끔하게 마침표를 찍고 끝낼것
- 문장 끝에 'OOO 드림', '지원자 OOO', '[이름] 올림', '제출합니다', 작성 날짜 등 편지 형태의 마무리 표현은 절대로 출력하지 말것
"""


# ====================== 공통 유틸 ======================

def _extract_json(text: str) -> str:
    """
    모델 응답에서 JSON 부분만 추출.
    ```json ... ``` 코드블록, ``` ... ``` 코드블록, 순수 JSON을 모두 처리.
    본문 안에 백틱(```)이 들어있는 경우에도 안전하게 동작하도록 정규식 사용.
    """
    text = text.strip()

    # ```json { ... } ``` 또는 ``` { ... } ``` 형태
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 코드블록이 없는 경우, 첫 '{' 부터 마지막 '}' 까지만 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return text


def call_llm(
    messages: List[Dict],
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    CLOVA Studio API 호출.
    네트워크 오류, HTTP 오류, 응답 스키마 오류를 모두 LLMCallError로 통일해서 던짐.
    """
    if not API_KEY:
        raise LLMCallError("CLOVA_STUDIO_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "messages": messages,
        "temperature": temperature,
        "maxTokens": max_tokens,
        "topP": 0.8,
        "repeatPenalty": 1.1,
    }

    try:
        response = requests.post(
            BASE_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
    except requests.exceptions.Timeout as e:
        raise LLMCallError(f"API 요청 시간 초과 ({REQUEST_TIMEOUT}초)") from e
    except requests.exceptions.RequestException as e:
        raise LLMCallError(f"API 요청 중 네트워크 오류 발생: {e}") from e

    if response.status_code != 200:
        # 응답 본문은 로그로만 남기고, 예외 메시지는 짧게 유지
        logger.error("CLOVA API 오류 응답 (status=%s): %s", response.status_code, response.text)
        raise LLMCallError(f"API 호출 실패: status_code={response.status_code}")

    try:
        result = response.json()
    except ValueError as e:
        raise LLMCallError(f"API 응답이 유효한 JSON이 아닙니다: {e}") from e

    try:
        return result["result"]["message"]["content"]
    except (KeyError, TypeError) as e:
        logger.error("예상치 못한 응답 스키마: %s", result)
        raise LLMCallError(f"API 응답에서 content를 찾을 수 없습니다: {e}") from e


# ====================== 갭 분석 ======================

def analyze_spec_gap(
    user_spec: str,
    retrieved_specs: List[str],
    company: str = "",
    position: str = "",
) -> Dict:
    """
    사용자 스펙과 합격자 스펙을 비교하여 갭 분석 및 Fit_score 결과를 반환.

    Raises:
        LLMCallError: API 호출 자체가 실패한 경우 (네트워크, 인증, 스키마 오류 등)
        ValueError: API 호출은 성공했지만 응답을 JSON으로 파싱할 수 없는 경우
    """
    if not user_spec or not user_spec.strip():
        raise ValueError("user_spec은 비어 있을 수 없습니다.")

    if retrieved_specs:
        context = "\n\n".join(
            f"[합격자 스펙 예시 {i + 1}]\n{spec}" for i, spec in enumerate(retrieved_specs)
        )
    else:
        context = "참고할 합격자 스펙 데이터가 없습니다."

    user_prompt = f"""
[목표 정보]
기업: {company if company else "미지정"}
직무: {position if position else "미지정"}

[사용자 현재 스펙]
{user_spec}

[참고용 합격자 스펙]
{context}

위 정보를 바탕으로 사용자의 스펙이 목표 기업/직무의 합격자 스펙과 얼마나 차이가 나는지 분석하고, 부족한 점과 보완 방법을 JSON 형식으로 알려주세요.
"""

    messages = [
        {"role": "system", "content": GAP_ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # LLMCallError는 여기서 잡지 않고 그대로 위로 던짐 (호출부에서 통일 처리)
    response_text = call_llm(messages, temperature=0.2, max_tokens=2000)

    cleaned = _extract_json(response_text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("갭 분석 JSON 파싱 실패. 원본 응답: %s", response_text)
        raise ValueError(f"모델 응답을 JSON으로 파싱하지 못했습니다: {e}") from e


# ====================== 자기소개서 생성 ======================

def generate_cover_letter(
    user_spec: str,
    company: str,
    position: str,
    gap_analysis: Optional[Dict] = None,
) -> str:
    """
    사용자 스펙 + 목표 기업/직무 + (선택) 갭 분석 결과를 바탕으로
    맞춤 자기소개서 초안을 생성.

    Raises:
        LLMCallError: API 호출이 실패한 경우
    """
    if not user_spec or not user_spec.strip():
        raise ValueError("user_spec은 비어 있을 수 없습니다.")
    if not company or not position:
        raise ValueError("company와 position은 반드시 지정해야 합니다.")

    gap_text = ""
    # gap_analysis가 있고, 파싱 실패 케이스(error 키)가 아니고, summary가 실제로 있을 때만 포함
    if gap_analysis and "error" not in gap_analysis and gap_analysis.get("summary"):
        gap_text = f"""
[갭 분석 참고]
요약: {gap_analysis["summary"]}
"""

    user_prompt = f"""
[지원 정보]
목표 기업: {company}
목표 직무: {position}

[사용자 스펙]
{user_spec}
{gap_text}

위 정보를 바탕으로 {company} {position} 직무에 지원하는 자기소개서 초안을 작성할 것.
"""

    messages = [
        {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    return call_llm(messages, temperature=0.5, max_tokens=2000)


# ====================== 테스트용 코드 데모 ======================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_user_spec = """
    - 학점: 3.4 / 4.5
    - 어학: 토익 700점, 오픽 IM2
    - 수상: 없음
    - 연수: 없음
    - 자격증: 컴퓨터 활용능력 1급
    - 인턴 경험: 없음
    - 프로젝트: 교내 웹 프로젝트 1회
    - 사용 가능한 기술: Python, HTML/CSS
    """

    test_retrieved_specs = [
        """
        - 학점: 3.8 / 4.5
        - 어학: 토익 920점
        - 수상: 2024.09 | 2024 오픈소스 해커톤 | 우수상 (2위) (주관: 과학기술정보통신부)
        - 연수: 2024.01 - 2024.07 | SSAFY (삼성청년SW아카데미) | Python/React 웹 개발자 과정 (800시간)
        - 자격증: 정보처리기사, SQLD, 전기기사
        - 인턴 경험: 대기업 IT인턴 6개월
        - 프로젝트: 실제 서비스 배포 경험 2회
        - 사용 가능한 기술: Python, Django, React, AWS
        """,
        """
        - 학점: 3.7 / 4.5
        - 어학: 900점, 오픽 IH
        - 수상: 2023.12 | 데이콘(DACON) 금융 데이터 예측 AI 경진대회 | Top 5% (입선)
        - 연수: 2023.05 - 2023.08 | 멋쟁이사자처럼 | 백엔드 부트캠프 8기 수료
        - 자격증: 정보처리기사, 무선설비기사
        - 인턴 경험: 스타트업 백엔드 인턴 4개월
        - 프로젝트: 팀 프로젝트 3회, 개인 포트폴리오 사이트
        - 사용 가능한 기술: Java, Spring, MySQL
        """,
    ]

    try:
        print("1. FIT-SCORE 분석 테스트 중...")
        gap_result = analyze_spec_gap(
            user_spec=test_user_spec,
            retrieved_specs=test_retrieved_specs,
            company="",
            position=""
        )
        print(json.dumps(gap_result, indent=2, ensure_ascii=False))

        print("\n2. 자기소개서 생성 테스트 중...")
        cover_letter = generate_cover_letter(
            user_spec=test_user_spec,
            company="테스트기업",
            position="테스트직무",
            gap_analysis=gap_result,
        )
        print(cover_letter)

    except (LLMCallError, ValueError) as e:
        print(f"실행 중 오류 발생: {e}")

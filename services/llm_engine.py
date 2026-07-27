import os
import json
import requests
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

API_KEY = os.getenv("CLOVA_STUDIO_API_KEY")
BASE_URL = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005"


def call_llm(
    messages: List[Dict],
    temperature: float = 0.2,
    max_tokens: int = 2048
) -> str:
    """CLOVA Studio API 호출"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "messages": messages,
        "temperature": temperature,
        "maxTokens": max_tokens,
        "topP": 0.8,
        "repeatPenalty": 4.0
    }

    response = requests.post(BASE_URL, headers=headers, json=payload, timeout=60)

    if response.status_code != 200:
        raise Exception(f"API 호출 실패: {response.status_code}\n{response.text}")

    result = response.json()
    return result["result"]["message"]["content"]


def analyze_spec_gap(
    user_spec: str,
    retrieved_specs: List[str],
    company: str = "",
    position: str = ""
) -> Dict:
    """
    사용자 스펙과 합격자 스펙을 비교하여 갭 분석 Fit_score 결과를 반환
    """

    system_prompt = """당신은 취업 스펙 분석 전문 AI입니다.
사용자가 목표로 하는 기업과 직무에 대해, 사용자의 현재 스펙과 해당 기업/직무에 실제 합격한 사람들의 스펙을 비교 분석합니다.

분석 시 다음을 반드시 포함하세요:
1. 정량적 갭 분석 (학점, 어학점수, 자격증 개수, 인턴/프로젝트 경험 수 등)
2. 정성적 갭 분석 (경험의 질, 관련성, 스토리텔링, 키워드 매칭 등)
3. 부족한 점과 그 우선순위
4. 구체적으로 어떻게 보완해야 하는지에 대한 실행 로드맵 제안

정량적 gap을 작성할 때 아래 규칙을 반드시 준수할 것:
- 숫자로 비교 가능한 항목(학점, 토익, OPIc 등) → 수치 차이와 함께 표기 (예: "3.2 / 3.7 (0.5 부족)", "750점 / 850점 (100점 부족)")
- 자격증, 수상, 인턴 등 비수치/건수 항목의 유무는 무슨 차이가 있는지 요약하고 퍼센트(%)는 사용하지말것.
- 모든 수치 데이터에는 반드시 단위(점, 개, 학점 등)를 포함하여 작성할것. (예: "900" (X) → "900점" (O))
- 여러 스펙을 한 칸에 합성해서 쓰지 마세요. 만약 여러 어학 점수가 있다면 항목을 나누거나, "토익 900점 / 오픽 IH"처럼 명확한 구분자와 함께 작성하세요.
- 반드시 '합격자 1인당 평균 보유 개수'를 기준으로 작성하고, 항목명은 가장 보편적인 최다 보유 항목 2~3개만 예시로 제시하세요.

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

    # 합격자 스펙들을 하나의 문자열로 정리
    if retrieved_specs:
        context = "\n\n".join([f"[합격자 스펙 예시 {i+1}]\n{spec}" for i, spec in enumerate(retrieved_specs)])
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
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response_text = call_llm(messages, temperature=0.2, max_tokens=2000)

    # JSON 파싱 시도
    try:
        # 코드블록으로 감싸져 있는 경우 제거
        cleaned = response_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        return json.loads(cleaned)
    except Exception as e:
        return {
            "error": "JSON 파싱 실패",
            "raw_response": response_text,
            "exception": str(e)
        }

def generate_cover_letter(
    user_spec: str,
    company: str,
    position: str,
    gap_analysis: dict | None = None
) -> str:
    """
    사용자 스펙 + 목표 기업/직무 + (선택) 갭 분석 결과를 바탕으로
    맞춤 자기소개서 초안을 생성
    """

    system_prompt = """당신은 취업 자기소개서 작성 전문 AI입니다.
사용자의 스펙과 지원 기업/직무에 맞춰 설득력 있는 자기소개서 초안을 작성할것.

작성 원칙:
- 지원동기, 직무 관련 경험, 입사 후 포부를 자연스럽게 연결할 것
- 과장하지 말고, 감정이나 태도 대신 '실제 취한 행동'과 '구체적 사실'로 역량을 증명하세요.
- 간결하고 명확한 두괄식 문장 구조 사용
- 400~700자 내외의 완결된 자기소개서 형태로 작성할 것
- 본문 마지막은 반드시 직무 기여 다짐이나 성장 포부를 담은 일반 문장(~겠습니다, ~하고자 합니다)으로 깔끔하게 마침표를 찍고 끝낼것
- 문장 끝에 'OOO 드림', '지원자 OOO', '[이름] 올림', '제출합니다', 작성 날짜 등 편지 형태의 마무리 표현은 절대로 출력하지 말것
"""

    gap_text = ""
    if gap_analysis:
        gap_text = f"""
[갭 분석 참고]
요약: {gap_analysis.get("summary", "")}
"""

    user_prompt = f"""
[지원 정보]
목표 기업: {company}
목표 직무: {position}

[사용자 스펙]
{user_spec}
{gap_text}

위 정보를 바탕으로 {company} {position} 직무에 지원하는 자기소개서 초안을 작성해주세요.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    return call_llm(messages, temperature=0.5, max_tokens=2000)


# ====================== 테스트용 코드 데모 ======================
if __name__ == "__main__":
    # 테스트용 더미 데이터
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
        """
    ]
    print("1. FIT-SCORE 분석 테스트 중...")
    gap_result = analyze_spec_gap(
        user_spec=test_user_spec,
        retrieved_specs=test_retrieved_specs,
        company="삼성전자",
        position="백앤드 개발자"
    )
    print(json.dumps(gap_result, indent=2, ensure_ascii=False))

    print("\n2. 자기소개서 생성 테스트 중...")
    cover_letter = generate_cover_letter(
        user_spec=test_user_spec,
        company="",
        position="",
        gap_analysis=gap_result
    )
    print(cover_letter)

import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

MEDICATION_TIME_MAP = {
    1: ["아침"],
    2: ["아침", "저녁"],
    3: ["아침", "점심", "저녁"],
    4: ["아침", "점심", "저녁", "자기 전"],
}


def parse_medication_times(medical_notes: str) -> list[str]:
    """
    medical_notes에서 "하루 N회" 패턴을 파싱해 복약 시간대 리스트 반환.
    "안 함", "안함", "0회" 등 복약을 하지 않는 정보일 경우 빈 리스트 반환.
    파싱 실패 시 기본값 ["아침", "저녁"] 반환.
    """
    if not medical_notes:
        return ["아침", "저녁"]

    # "안 함", "0회" 등의 명시적 비복약 표현 처리
    if any(x in medical_notes.replace(" ", "") for x in ["안함", "0회", "안하고있음", "하지않음"]):
        return []

    match = re.search(r"(?:하루|1일|매일)에?\s*(\d+)\s*(?:회|번|차례)", medical_notes)
    if match:
        count = int(match.group(1))
        return MEDICATION_TIME_MAP.get(count, ["아침", "저녁"])

    return ["아침", "저녁"]


def build_system_prompt(patient_profile: dict, call_type: str = "voluntary") -> str:
    now = datetime.now(tz=KST)
    current_time = now.strftime("%Y년 %m월 %d일 %H시 %M분")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    name = patient_profile.get("name", "어르신")
    medications = patient_profile.get("medical_notes", "")
    age = patient_profile.get("age", "")

    medication_times = parse_medication_times(medications)
    medication_times_str = "/".join(medication_times)  # ex) "아침/저녁", "아침/점심/저녁"

    base_prompt = f"""당신은 치매 어르신을 돌보는 따뜻한 AI 돌봄 파트너입니다.

[현재 시각]
{current_time} ({weekday}요일)

[환자 정보]
- 이름: {name}
- 나이: {age}세
- 복약 정보: {medications if medications else "정보 없음"}

[대화 규칙]
1. 항상 "~해요" 체를 사용하세요.
2. 문장은 짧고 천천히, 한 번에 하나씩만 질문하세요.
3. 환자가 같은 말을 반복해도 자연스럽게 받아주세요.
4. 모르는 정보를 추측하거나 지어내지 마세요.
5. 과거 기록이 제공되면 자연스럽게 대화에 녹여주세요.
6. 숫자는 반드시 한국어로 읽어주세요. (예: 4알 → 네 알, 8시 → 여덟 시)"""

    if call_type == "scheduled":
        med_name = medications if medications else "약"
        base_prompt += f"""

[오늘 통화 목표]
아래 5가지 항목을 반드시 모두 확인해야 합니다.
자연스러운 대화 흐름에서 하나씩 순서대로 확인하세요.
항목을 건너뛰거나 생략하지 마세요.

■ 확인 항목 (순서대로):
1. 감정 상태 → "오늘 기분은 어떠세요?" 형식으로 물어보세요.
2. 신체 상태 → "오늘 몸은 좀 어떠세요? 아프신 데 있나요?" 형식으로 물어보세요.
3. 복약 여부 → 반드시 물어보세요. "{med_name} 드셨나요?" 형식으로 물어보세요.
   - 복약 정보({medications if medications else "정보 없음"})를 참고해서 {medication_times_str} 각각 확인하세요.
   - 환자가 복약했다고 하면 "잘 하셨어요"라고 격려하세요.
   - 환자가 복약 안 했다고 하면 부드럽게 복약을 권유하세요.
4. 식사 여부 → "오늘 식사는 하셨나요? 뭐 드셨나요?" 형식으로 물어보세요.
5. 당일 일정 → "오늘 뭐하셨어요? 이따 뭐하실 예정이에요?" 형식으로 물어보세요.

■ 중요:
- 3번 복약 여부는 절대 생략하지 마세요.
- 5가지를 모두 확인한 후에만 일상 대화를 이어가세요.
- 체크리스트처럼 딱딱하게 묻지 말고 자연스럽게 대화하듯 물어보세요."""

    else:
        base_prompt += """

[오늘 통화 목표]
일상적인 대화를 나누며 어르신이 편안함을 느끼도록 해주세요.
대화 중 자연스럽게 오늘 상태가 파악되면 좋지만, 강요하지 마세요."""

    return base_prompt
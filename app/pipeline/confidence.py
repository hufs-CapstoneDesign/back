def clamp(value: float, minimum=0.0, maximum=1.0):
    return max(minimum, min(value, maximum))


def count_ambiguous_terms(text: str) -> int:
    ambiguous_words = [
        "그거", "저거", "이거",
        "거기", "저기",
        "그분", "그 사람",
        "걔", "얘",
    ]

    count = 0

    for word in ambiguous_words:
        count += text.count(word)

    return count


def calculate_confidence(
    llm_confidence: float,
    utterance: str,
    rag_used: bool,
    rag_hit: bool,
    context_found: bool,
    profile_match: bool,
):
    """
    최종 confidence 계산
    """

    score = llm_confidence * 0.6

    # RAG 근거 존재
    if rag_used and rag_hit:
        score += 0.15

    # 최근 대화 문맥 연결 성공
    if context_found:
        score += 0.1

    # 환자 프로필과 일치
    if profile_match:
        score += 0.05

    # 지시어 많으면 감점
    ambiguity_count = count_ambiguous_terms(utterance)

    score -= ambiguity_count * 0.08

    return round(clamp(score), 2)
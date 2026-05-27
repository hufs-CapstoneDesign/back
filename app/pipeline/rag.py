from openai import AsyncOpenAI
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings
from datetime import datetime, timedelta

client = AsyncOpenAI(api_key=settings.OPENAI_KEY)

# ==================== 개선: 더 정교한 트리거 ===================

# 1. 직접 참조 키워드 (강한 트리거)
DIRECT_REFERENCE_KEYWORDS = [
    "저번에", "그거", "아까", "거기", "지난번",
    "어제", "전에", "그때", "그분", "그사람",
    "거기서", "저기", "요전에", "지지난",
    "아들", "딸", "가족", "언제", "깜빡", "잊어버렸",
    "뭐였지", "기억", "뭐라고", "했었나", "했나"
]

# 2. 짧은 발화 (문맥 의존성 높음)
SHORT_UTTERANCE_PATTERNS = [
    "그래", "맞지", "그래?", "맞나", "맞나?",
    "약은", "약은?", "밥은", "밥은?",
    "그래서", "그래서?", "그래서 뭐",
    "뭐", "뭐?", "뭐해", "뭐해?",
    "언제", "언제?", "누구", "누구?",
]

# 3. 대명사 (문맥 필수)
PRONOUN_PATTERNS = [
    "그", "그거", "그거", "저거", "이거",
    "그사람", "그분", "저사람", "저분",
    "거기", "저기", "이곳", "그곳"
]


def detect_context_dependency(utterance: str) -> float:
    """
    발화의 문맥 의존도 계산 (0.0 ~ 1.0)
    높을수록 이전 대화 문맥이 필요함
    """
    score = 0.0
    
    # 1. 직접 참조 (강함)
    if any(kw in utterance for kw in DIRECT_REFERENCE_KEYWORDS):
        score = max(score, 0.9)
    
    # 2. 짧은 발화 (중간~강함)
    if len(utterance) < 10:  # 매우 짧음
        score = max(score, 0.7)
    elif len(utterance) < 20:  # 짧음
        score = max(score, 0.5)
    
    # 3. 대명사 (중간)
    if any(p in utterance for p in PRONOUN_PATTERNS):
        score = max(score, 0.6)
    
    # 4. 질문 형태 (중간)
    if utterance.endswith("?") or utterance.endswith("나"):
        score = max(score, 0.4)
    
    return score


def should_trigger_working_memory(utterance: str) -> bool:
    """
    Working Memory를 retrieval할지 판단
    (기존: keyword 기반, 개선: context dependency 기반)
    """
    return detect_context_dependency(utterance) > 0.3


def get_retrieval_params(utterance: str) -> dict:
    """
    문맥 의존도에 따라 retrieval 강도 조정
    """
    dependency = detect_context_dependency(utterance)
    
    if dependency > 0.8:  # 매우 강한 의존성
        return {
            "wm_limit": 3,
            "wm_threshold": 0.8,  # 더 관대함
            "ltm_limit": 3,
            "ltm_threshold": 0.7,
        }
    elif dependency > 0.6:  # 중간~강함
        return {
            "wm_limit": 2,
            "wm_threshold": 0.75,
            "ltm_limit": 2,
            "ltm_threshold": 0.7,
        }
    else:  # 약함
        return {
            "wm_limit": 1,
            "wm_threshold": 0.7,
            "ltm_limit": 2,
            "ltm_threshold": 0.7,
        }


# ==================== 임베딩 캐시 (선택사항) ===================

_embedding_cache = {}  # {text: embedding}

async def get_embedding(text_input: str) -> list:
    """임베딩 조회 (캐시 활용)"""
    if text_input in _embedding_cache:
        return _embedding_cache[text_input]
    
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    embedding = response.data[0].embedding
    _embedding_cache[text_input] = embedding
    
    return embedding


# ==================== Working Memory ===================

async def save_to_working_memory(
    session_id: str,
    patient_id: str,
    speaker: str,
    raw_text: str,
) -> None:
    """발화마다 working_memory에 저장"""
    embedding = await get_embedding(raw_text)

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO working_memory
                (id, session_id, patient_id, speaker, raw_text,
                 memory_content, embedding, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid),
                 CAST(:patient_id AS uuid), :speaker, :raw_text,
                 :raw_text, CAST(:embedding AS vector), NOW())
        """), {
            "session_id": session_id,
            "patient_id": patient_id,
            "speaker": speaker,
            "raw_text": raw_text,
            "embedding": str(embedding),
        })
        await db.commit()


async def get_recent_history(
    session_id: str,
    max_tokens: int = 512,
    max_turns: int = 5,
) -> str:
    """
    최근 대화 히스토리를 바로 조회 (retrieval 아님)
    - 문맥 연속성 보장
    - 임베딩 불필요 (빠름)
    - Token 제한으로 비용 관리
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT speaker, raw_text, created_at
            FROM working_memory
            WHERE session_id = CAST(:session_id AS uuid)
            ORDER BY created_at DESC
            LIMIT :max_turns
        """), {
            "session_id": session_id,
            "max_turns": max_turns,
        })
        
        rows = result.fetchall()
        if not rows:
            return ""
        
        # 시간순으로 정렬 (역순 → 정순)
        rows = list(reversed(rows))
        
        # Token 계산하며 추가
        history_parts = []
        token_count = 0
        
        for row in rows:
            speaker_label = "환자" if row.speaker == "patient" else "AI"
            formatted = f"{speaker_label}: {row.raw_text}"
            
            # 대략적인 토큰 계산 (한글: 글자수/3, 영어: 단어수)
            estimated_tokens = len(formatted) // 3
            
            if token_count + estimated_tokens > max_tokens:
                break
            
            history_parts.append(formatted)
            token_count += estimated_tokens
        
        return "\n".join(history_parts)


async def search_working_memory(
    query_embedding: list,
    session_id: str,
    limit: int = 2,
    threshold: float = 0.7,
) -> list[str]:
    """Working Memory 검색 (선택적 활용)"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT raw_text,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM working_memory
            WHERE session_id = CAST(:session_id AS uuid)
              AND embedding IS NOT NULL
            ORDER BY distance
            LIMIT :limit
        """), {
            "vec": str(query_embedding),
            "session_id": session_id,
            "limit": limit,
        })
        rows = result.fetchall()
        return [row.raw_text for row in rows if row.distance < threshold]


# ==================== Long-term Memory ===================

async def save_to_messages(
    session_id: str,
    patient_id: str,
    sender_type: str,
    content: str,
    corrected_content: str | None = None,
) -> None:
    """messages 테이블에 대화 원본 저장"""
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO messages
                (id, session_id, patient_id, sender_type,
                 content, corrected_content, message_type, created_at)
            VALUES
                (gen_random_uuid(), CAST(:session_id AS uuid),
                 CAST(:patient_id AS uuid), :sender_type,
                 :content, :corrected_content, 'text', NOW())
        """), {
            "session_id": session_id,
            "patient_id": patient_id,
            "sender_type": sender_type,
            "content": content,
            "corrected_content": corrected_content,
        })
        await db.commit()


async def search_long_term_memory(
    query_embedding: list,
    patient_id: str,
    limit: int = 3,
    threshold: float = 0.7,
) -> list[str]:
    """Long-term Memory 검색 (항상 수행)"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT content,
                   embedding <=> CAST(:vec AS vector) AS distance
            FROM long_term_memory
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND embedding IS NOT NULL
            ORDER BY distance
            LIMIT :limit
        """), {
            "vec": str(query_embedding),
            "patient_id": patient_id,
            "limit": limit,
        })
        rows = result.fetchall()
        return [row.content for row in rows if row.distance < threshold]


# ==================== 통합 Retrieval (개선) ===================

async def retrieve_context(
    utterance: str,
    session_id: str,
    patient_id: str,
) -> dict:
    """
    [개선] 최근 히스토리 + 선택적 retrieval 통합
    
    반환값:
    {
        "recent_history": "...",  # 최근 대화 (항상 포함)
        "working_memory": [...],  # 관련 발화 (조건부)
        "long_term_memory": [...],  # 환자 정보 (항상)
    }
    """
    
    # 1. 최근 히스토리 (항상 포함, 빠름)
    recent_history = await get_recent_history(session_id)
    
    # 2. Selective Retrieval
    query_embedding = await get_embedding(utterance)
    retrieval_params = get_retrieval_params(utterance)
    
    # Working Memory: 선택적
    wm_results = []
    if should_trigger_working_memory(utterance):
        wm_results = await search_working_memory(
            query_embedding,
            session_id,
            limit=retrieval_params["wm_limit"],
            threshold=retrieval_params["wm_threshold"],
        )
    
    # Long-term Memory: 항상
    ltm_results = await search_long_term_memory(
        query_embedding,
        patient_id,
        limit=retrieval_params["ltm_limit"],
        threshold=retrieval_params["ltm_threshold"],
    )
    
    return {
        "recent_history": recent_history,
        "working_memory": wm_results,
        "long_term_memory": ltm_results,
        "context_dependency": detect_context_dependency(utterance),
    }


async def build_context_prompt(retrieval_result: dict) -> str:
    """
    Retrieval 결과를 프롬프트용 context로 변환
    """
    context_parts = []
    
    # 1. 최근 대화 (높은 우선순위)
    if retrieval_result["recent_history"]:
        context_parts.append("[최근 대화]\n" + retrieval_result["recent_history"])
    
    # 2. Working Memory (중간 우선순위)
    if retrieval_result["working_memory"]:
        wm_text = "\n".join([f"- {r}" for r in retrieval_result["working_memory"]])
        context_parts.append(f"[관련 발화]\n{wm_text}")
    
    # 3. Long-term Memory (기본 우선순위)
    if retrieval_result["long_term_memory"]:
        ltm_text = "\n".join([f"- {r}" for r in retrieval_result["long_term_memory"]])
        context_parts.append(f"[환자 정보]\n{ltm_text}")
    
    return "\n\n".join(context_parts)


# ==================== 성능 모니터링 (선택사항) ===================

class RetrievalMetrics:
    """Retrieval 성능 모니터링"""
    
    @staticmethod
    async def log_retrieval(
        utterance: str,
        result: dict,
        latency_ms: float,
    ) -> None:
        """Retrieval 성능 로깅"""
        import logging
        logger = logging.getLogger("retrieval_metrics")
        
        logger.info(
            f"Retrieval | "
            f"utterance_len={len(utterance)} | "
            f"context_dep={result['context_dependency']:.2f} | "
            f"wm_hits={len(result['working_memory'])} | "
            f"ltm_hits={len(result['long_term_memory'])} | "
            f"latency={latency_ms:.2f}ms"
        )
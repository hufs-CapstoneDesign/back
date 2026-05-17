"""
전체 통화 테스트
한 세션에서 모든 발화(통화1~6)를 순차적으로 처리
"""

import asyncio
import websockets
import httpx
from pathlib import Path
from datetime import datetime
import json

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

PATIENT_ID = "6d3ef730-2ac9-4290-8db2-31859bcc49a5"
AUDIO_DIR = Path("tests/audio")

# 전체 통화 순서 (통화1 ~ 통화6)
FULL_CONVERSATION = [
    ("통화1.mp3", "통화1: 안녕?"),
    ("통화2.mp3", "통화2: (활기차게 답하며) 아주 좋아! 밖에 날씨도 좋고. 아유, 좋네."),
    ("통화3.mp3", "통화3: 아까 아들이 전화했는데 언제 온다고 했는지 깜빡 잊어버렸네."),
    ("통화4.mp3", "통화4: 나? 김치찌개 먹었어"),
    ("통화5.mp3", "통화5: (단호하게) 운동 안해. 이따가 아들 만나기로 했어."),
    ("통화6.mp3", "통화6: 아, 아닌가?"),
]

EXPECTED_EXTRACTIONS = {
    "통화2.mp3": {
        "신체_상태": "좋음",
        "감정_상태": "활기찬, 긍정적",
        "extraction_target": "신체 상태 및 감정 상태"
    },
    "통화3.mp3": {
        "기억_회상": "아들 방문 일정 회상",
        "ai_support": "아들이 이번 주 토요일 점심에 온다고 했음",
        "extraction_target": "기억력 장애 보조"
    },
    "통화4.mp3": {
        "식사_여부": "김치찌개 섭취",
        "extraction_target": "일일 활동 추적"
    },
    "통화5.mp3": {
        "당일_일정": "아들 만나기",
        "운동": "안함",
        "extraction_target": "일정 확인"
    }
}

async def send_utterance(ws, audio_file: Path) -> bytes:
    """WebSocket으로 발화를 전송하고 응답 수집"""
    if not audio_file.exists():
        raise FileNotFoundError(f"파일 없음: {audio_file}")
    
    with open(audio_file, "rb") as f:
        audio_bytes = f.read()
    
    await ws.send(audio_bytes)
    
    # 응답 수집
    response_bytes = b""
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(msg, bytes):
                response_bytes += msg
            elif msg == "END":
                break
        except asyncio.TimeoutError:
            break
    
    return response_bytes

async def run_full_conversation():
    """전체 통화 테스트"""
    
    print("\n" + "="*70)
    print("🎤 전체 통화 테스트 (한 세션)")
    print("="*70)
    print(f"테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"환자 ID: {PATIENT_ID}")
    print(f"발화 수: {len(FULL_CONVERSATION)}")
    
    session_id = None
    utterance_results = []
    
    try:
        # 1. 세션 시작
        print(f"\n[1단계] 세션 시작...")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/calls", json={
                "patient_id": PATIENT_ID,
                "call_type": "test_full_conversation"
            })
            
            if response.status_code != 200:
                print(f"❌ 세션 시작 실패! (상태: {response.status_code})")
                return
            
            session_data = response.json()
            session_id = session_data["session_id"]
            print(f"✅ 세션 생성: {session_id}")
        
        # 2. WebSocket 연결 후 순차 발화 처리
        print(f"\n[2단계] 발화 순차 처리...")
        uri = f"{WS_URL}/ws/calls?session_id={session_id}"
        
        async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
            for idx, (file_name, description) in enumerate(FULL_CONVERSATION, 1):
                audio_file = AUDIO_DIR / file_name
                
                if not audio_file.exists():
                    print(f"\n❌ [{idx}] {description}")
                    print(f"   파일 없음: {audio_file}")
                    utterance_results.append({
                        "num": idx,
                        "file": file_name,
                        "status": "error",
                        "reason": "file_not_found"
                    })
                    continue
                
                try:
                    print(f"\n📝 [{idx}/{len(FULL_CONVERSATION)}] {description}")
                    print(f"   🎤 음성 전송 중...")
                    
                    response_bytes = await send_utterance(ws, audio_file)
                    
                    print(f"   🔊 응답 수신 ({len(response_bytes)} bytes)")
                    
                    # 응답 저장
                    output_file = AUDIO_DIR / f"response_{idx:02d}_{file_name}"
                    with open(output_file, "wb") as f:
                        f.write(response_bytes)
                    print(f"   💾 저장: {output_file}")
                    
                    # 예상 추출 정보 표시
                    if file_name in EXPECTED_EXTRACTIONS:
                        extraction = EXPECTED_EXTRACTIONS[file_name]
                        print(f"   📊 예상 추출: {extraction.get('extraction_target')}")
                        for key, val in extraction.items():
                            if key != "extraction_target":
                                print(f"      • {key}: {val}")
                    
                    utterance_results.append({
                        "num": idx,
                        "file": file_name,
                        "status": "success",
                        "response_bytes": len(response_bytes)
                    })
                    
                    # 발화 간 간격
                    await asyncio.sleep(1)
                
                except Exception as e:
                    print(f"   ❌ 에러: {e}")
                    utterance_results.append({
                        "num": idx,
                        "file": file_name,
                        "status": "error",
                        "reason": str(e)
                    })
        
        # 3. 세션 종료
        print(f"\n[3단계] 세션 종료...")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/calls/{session_id}")
            
            if response.status_code == 200:
                print(f"✅ 세션 종료 완료")
            else:
                print(f"⚠️  세션 종료 응답: {response.status_code}")
        
        # 4. 결과 정리
        print(f"\n{'='*70}")
        print(f"📊 테스트 결과 요약")
        print(f"{'='*70}")
        
        success_count = sum(1 for r in utterance_results if r["status"] == "success")
        print(f"성공: {success_count}/{len(utterance_results)}")
        
        for result in utterance_results:
            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"{status_icon} [{result['num']}] {result['file']}")
            if result["status"] == "error":
                print(f"   └─ {result.get('reason', 'Unknown error')}")
        
        # 5. DBeaver 확인 쿼리
        print(f"\n{'='*70}")
        print(f"🔍 DBeaver 확인 명령어")
        print(f"{'='*70}")
        
        print(f"\n-- 현재 세션의 모든 메시지")
        print(f"SELECT DISTINCT")
        print(f"  m.id,")
        print(f"  m.sender_type,")
        print(f"  LEFT(m.content, 50) as content_preview,")
        print(f"  m.created_at")
        print(f"FROM messages m")
        print(f"WHERE m.session_id = '{session_id}'")
        print(f"ORDER BY m.created_at ASC;")
        
        print(f"\n-- 현재 세션의 Working Memory")
        print(f"SELECT")
        print(f"  memory_content,")
        print(f"  importance_score,")
        print(f"  created_at")
        print(f"FROM working_memory")
        print(f"WHERE session_id = '{session_id}'")
        print(f"ORDER BY created_at ASC;")
        
        print(f"\n-- 환자의 모든 세션 목록")
        print(f"SELECT")
        print(f"  s.id,")
        print(f"  s.call_type,")
        print(f"  s.started_at,")
        print(f"  s.ended_at,")
        print(f"  COUNT(m.id) as msg_count")
        print(f"FROM sessions s")
        print(f"LEFT JOIN messages m ON s.id = m.session_id")
        print(f"WHERE s.patient_id = '{PATIENT_ID}'")
        print(f"GROUP BY s.id")
        print(f"ORDER BY s.started_at DESC;")
        
        print(f"\n-- Long-term Memory (RAG) 확인")
        print(f"SELECT")
        print(f"  memory_type,")
        print(f"  memory_content,")
        print(f"  confidence_score,")
        print(f"  last_mentioned_at")
        print(f"FROM long_term_memory")
        print(f"WHERE patient_id = '{PATIENT_ID}'")
        print(f"ORDER BY memory_type, confidence_score DESC;")
        
        print(f"\n{'='*70}")
        print(f"✅ 테스트 완료!")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
    
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(run_full_conversation())
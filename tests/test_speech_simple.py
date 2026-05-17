"""
간단한 발화별 테스트
각 발화마다 새로운 세션을 시작 (독립적 테스트)
"""

import asyncio
import websockets
import httpx
from pathlib import Path
import json

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

PATIENT_ID = "6d3ef730-2ac9-4290-8db2-31859bcc49a5"
AUDIO_DIR = Path("tests/audio")

# 간단한 발화 목록
UTTERANCES = [
    # Case A
    ("A-1.mp3", "A-1: 안녕?"),
    ("A-2.mp3", "A-2: 그래."),
    ("A-3.mp3", "A-3: 너는 누구니?"),
    # Case B
    ("B-1.mp3", "B-1: 지금 몇 시야? 그리고 오늘 밖에 날씨 어때?"),
    ("B-2.mp3", "B-2: 아침 약 먹을 시간 알려줘. 그리고 오늘 점심은 뭘 먹어야 할지 모르겠네."),
    ("B-3.mp3", "B-3: 오늘이 며칠이더라? 아유, 하늘이 뿌연 게 내일 비가 오려나?"),
    # Case C
    ("C-1.mp3", "C-1: 나 저번에 그거 붙였던 거.. 이름이 뭐였지?"),
    ("C-2.mp3", "C-2: 아까 아들이 전화했는데 언제 온다고 했는지 깜빡 잊어버�었네."),
    ("C-3.mp3", "C-3: 저번에 선생님이 조심하라고 했던 거, 그게 뭐였더라?"),
]

async def test_single_utterance(file_name: str, description: str) -> dict:
    """단일 발화 테스트"""
    audio_file = AUDIO_DIR / file_name
    
    if not audio_file.exists():
        print(f"❌ {description} — 파일 없음: {audio_file}")
        return {"status": "error", "reason": "file_not_found"}
    
    print(f"\n📝 {description}")
    
    try:
        # 1. 세션 시작
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/calls", json={
                "patient_id": PATIENT_ID,
                "call_type": "test"
            })
            
            if response.status_code != 200:
                print(f"❌ 세션 시작 실패")
                return {"status": "error", "reason": "session_creation_failed"}
            
            session_data = response.json()
            session_id = session_data["session_id"]
            print(f"✅ 세션 생성: {session_id[:8]}...")
        
        # 2. WebSocket으로 음성 전송
        uri = f"{WS_URL}/ws/calls?session_id={session_id}"
        
        async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
            with open(audio_file, "rb") as f:
                audio_bytes = f.read()
            
            print(f"   🎤 음성 전송 ({len(audio_bytes)} bytes)")
            await ws.send(audio_bytes)
            
            # 응답 수집
            response_bytes = b""
            print(f"   ⏳ 응답 대기 중...")
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    if isinstance(msg, bytes):
                        response_bytes += msg
                        print(f"   🔊 수신 ({len(msg)} bytes)")
                    elif msg == "END":
                        print(f"   ✅ 응답 완료!")
                        break
                except asyncio.TimeoutError:
                    print(f"   ⚠️  타임아웃")
                    break
            
            # 응답 저장
            if response_bytes:
                output_file = AUDIO_DIR / f"response_{file_name}"
                with open(output_file, "wb") as f:
                    f.write(response_bytes)
                print(f"   💾 저장: {output_file}")
        
        # 3. 세션 종료
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/calls/{session_id}")
            if response.status_code == 200:
                print(f"✅ 세션 종료")
                
                # DB 확인 정보 출력
                end_data = response.json()
                return {
                    "status": "success",
                    "session_id": session_id,
                    "file": file_name
                }
        
        return {"status": "success", "session_id": session_id}
    
    except Exception as e:
        print(f"❌ 에러: {e}")
        return {"status": "error", "reason": str(e)}

async def run_all_tests():
    """모든 발화 테스트 실행"""
    results = {
        "total": len(UTTERANCES),
        "success": 0,
        "failed": 0,
        "sessions": []
    }
    
    print("\n" + "="*70)
    print("🎯 발화별 순차 테스트 시작")
    print("="*70)
    
    for idx, (file_name, description) in enumerate(UTTERANCES, 1):
        print(f"\n[{idx}/{len(UTTERANCES)}]", end="")
        result = await test_single_utterance(file_name, description)
        
        if result["status"] == "success":
            results["success"] += 1
            results["sessions"].append({
                "utterance": description,
                "session_id": result.get("session_id")
            })
        else:
            results["failed"] += 1
        
        # 발화 간 대기
        await asyncio.sleep(1)
    
    # 최종 결과
    print("\n" + "="*70)
    print("📊 테스트 완료")
    print("="*70)
    print(f"총 테스트: {results['total']}")
    print(f"성공: {results['success']}")
    print(f"실패: {results['failed']}")
    
    if results['sessions']:
        print(f"\n📋 생성된 세션 목록:")
        for item in results['sessions']:
            print(f"  • {item['utterance']}")
            print(f"    → {item['session_id'][:8]}...")
    
    # DBeaver 쿼리
    print(f"\n{'='*70}")
    print("📊 DBeaver에서 확인할 쿼리:")
    print("="*70)
    print("\n-- 1. 모든 메시지 확인")
    print("SELECT u.name, s.id as session_id, m.sender_type, m.content, m.created_at")
    print("FROM messages m")
    print("JOIN sessions s ON m.session_id = s.id")
    print("JOIN patients p ON s.patient_id = p.id")
    print("JOIN users u ON p.user_id = u.id")
    print("WHERE u.username = 'kim_sunja_patient'")
    print("ORDER BY s.started_at DESC, m.created_at;")
    
    print("\n-- 2. 세션별 요약")
    print("SELECT s.id, s.started_at, s.ended_at, COUNT(m.id) as msg_count")
    print("FROM sessions s")
    print("LEFT JOIN messages m ON s.id = m.session_id")
    print("WHERE s.patient_id = '%s'" % PATIENT_ID)
    print("GROUP BY s.id")
    print("ORDER BY s.started_at DESC;")
    
    print("\n-- 3. Working Memory 확인")
    print("SELECT wm.memory_content, wm.importance_score, s.id as session_id")
    print("FROM working_memory wm")
    print("LEFT JOIN sessions s ON wm.session_id = s.id")
    print("WHERE wm.patient_id = '%s'" % PATIENT_ID)
    print("ORDER BY wm.created_at DESC;")
    
    print("\n-- 4. 감정 감지 결과")
    print("SELECT emotion, confidence_score, s.started_at")
    print("FROM slot_results sr")
    print("LEFT JOIN sessions s ON sr.session_id = s.id")
    print("WHERE sr.patient_id = '%s'" % PATIENT_ID)
    print("ORDER BY sr.detected_at DESC;")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
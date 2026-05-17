"""
발화별 순차 테스트 스크립트
Case A, B, C 각각 테스트 가능
"""

import asyncio
import websockets
import httpx
from pathlib import Path
from datetime import datetime

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

PATIENT_ID = "6d3ef730-2ac9-4290-8db2-31859bcc49a5"
AUDIO_DIR = Path("tests/audio")

# 테스트 케이스 정의
TEST_CASES = {
    "A": {
        "name": "기본 인사말 테스트",
        "utterances": [
            {"num": 1, "file": "A-1.mp3", "description": "발화: 안녕?"},
            {"num": 2, "file": "A-2.mp3", "description": "발화: 그래."},
            {"num": 3, "file": "A-3.mp3", "description": "발화: 너는 누구니?"},
        ]
    },
    "B": {
        "name": "시간/날씨/약 정보 테스트",
        "utterances": [
            {"num": 1, "file": "B-1.mp3", "description": "발화: 지금 몇 시야? 그리고 오늘 밖에 날씨 어때?"},
            {"num": 2, "file": "B-2.mp3", "description": "발화: 아침 약 먹을 시간 알려줘. 그리고 오늘 점심은 뭘 먹어야 할지 모르겠네."},
            {"num": 3, "file": "B-3.mp3", "description": "발화: 오늘이 며칠이더라? 아유, 하늘이 뿌연 게 내일 비가 오려나?"},
        ]
    },
    "C": {
        "name": "기억 회상 테스트",
        "utterances": [
            {"num": 1, "file": "C-1.mp3", "description": "발화: 나 저번에 그거 붙였던 거.. 이름이 뭐였지?"},
            {"num": 2, "file": "C-2.mp3", "description": "발화: 아까 아들이 전화했는데 언제 온다고 했는지 깜빡 잊어버렸네."},
            {"num": 3, "file": "C-3.mp3", "description": "발화: 저번에 선생님이 조심하라고 했던 거, 그게 뭐였더라?"},
        ]
    },
    "FULL": {
        "name": "전체 통화 테스트",
        "utterances": [
            {"num": 1, "file": "통화1.mp3", "description": "통화1: 안녕?"},
            {"num": 2, "file": "통화2.mp3", "description": "통화2: (활기차게 답하며) 아주 좋아!"},
            {"num": 3, "file": "통화3.mp3", "description": "통화3: 아까 아들이 전화했는데..."},
            {"num": 4, "file": "통화4.mp3", "description": "통화4: 나? 김치찌개 먹었어"},
            {"num": 5, "file": "통화5.mp3", "description": "통화5: (단호하게) 운동 안해."},
            {"num": 6, "file": "통화6.mp3", "description": "통화6: 아, 아닌가?"},
        ]
    }
}

async def test_single_utterance(session_id: str, audio_file: Path, utterance_info: dict):
    """단일 발화 테스트"""
    if not audio_file.exists():
        print(f"❌ 파일 없음: {audio_file}")
        return False
    
    print(f"\n📝 {utterance_info['description']}")
    uri = f"{WS_URL}/ws/calls?session_id={session_id}"
    
    try:
        async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
            with open(audio_file, "rb") as f:
                audio_bytes = f.read()
            
            print(f"   🎤 음성 파일 전송 ({len(audio_bytes)} bytes)")
            await ws.send(audio_bytes)
            
            # 응답 수집
            response_data = []
            print(f"   ⏳ AI 응답 대기 중...")
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    if isinstance(msg, bytes):
                        response_data.append(msg)
                        print(f"   🔊 음성 응답 수신 ({len(msg)} bytes)")
                    elif msg == "END":
                        print(f"   ✅ 응답 완료!")
                        break
                except asyncio.TimeoutError:
                    print(f"   ⚠️  타임아웃 — 응답 없음")
                    break
            
            # 응답 저장
            if response_data:
                output_file = AUDIO_DIR / f"response_{session_id[:8]}_{utterance_info['num']}.mp3"
                with open(output_file, "wb") as f:
                    for data in response_data:
                        f.write(data)
                print(f"   💾 응답 저장: {output_file}")
            
            return True
    
    except Exception as e:
        print(f"   ❌ 에러: {e}")
        return False

async def run_case_test(case_key: str):
    """Case별 테스트 실행"""
    case = TEST_CASES[case_key]
    
    print(f"\n{'='*70}")
    print(f"📋 Case {case_key}: {case['name']}")
    print(f"{'='*70}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. 세션 시작
        print(f"\n[세션 시작]")
        response = await client.post(f"{BASE_URL}/calls", json={
            "patient_id": PATIENT_ID,
            "call_type": "test"
        })
        
        if response.status_code != 200:
            print(f"❌ 세션 시작 실패! (상태: {response.status_code})")
            print(f"응답: {response.text}")
            return
        
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"✅ 세션 생성: {session_id}")
    
    # 2. 발화별 테스트
    for utterance in case["utterances"]:
        audio_file = AUDIO_DIR / utterance["file"]
        await test_single_utterance(session_id, audio_file, utterance)
        
        # 발화 간 대기 (서버 부하 방지)
        await asyncio.sleep(2)
    
    # 3. 세션 종료
    print(f"\n[세션 종료]")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{BASE_URL}/calls/{session_id}")
        if response.status_code == 200:
            print(f"✅ 세션 종료 완료")
        else:
            print(f"⚠️  세션 종료 응답: {response.status_code}")
    
    # 4. 확인 쿼리 출력
    print(f"\n{'='*70}")
    print(f"📊 DBeaver 확인 쿼리:")
    print(f"{'='*70}")
    print(f"-- 메시지 확인")
    print(f"SELECT id, sender_type, content, created_at FROM messages")
    print(f"WHERE session_id = '{session_id}'")
    print(f"ORDER BY created_at;")
    print(f"\n-- Working Memory 확인")
    print(f"SELECT memory_content, importance_score, created_at FROM working_memory")
    print(f"WHERE session_id = '{session_id}'")
    print(f"ORDER BY created_at;")
    print(f"\n-- 감정 감지 결과 확인")
    print(f"SELECT emotion, confidence_score, detected_at FROM slot_results")
    print(f"WHERE session_id = '{session_id}'")
    print(f"ORDER BY detected_at;")

async def main():
    """메인 메뉴"""
    print("\n🎯 발화별 순차 테스트 스크립트")
    print(f"{'='*70}")
    print("테스트 케이스:")
    for key, case in TEST_CASES.items():
        print(f"  {key}: {case['name']} ({len(case['utterances'])}개 발화)")
    print(f"\n실행 방식:")
    print(f"  python test_speech_by_case.py A      # Case A만 테스트")
    print(f"  python test_speech_by_case.py B      # Case B만 테스트")
    print(f"  python test_speech_by_case.py C      # Case C만 테스트")
    print(f"  python test_speech_by_case.py FULL   # 전체 통화 테스트")
    print(f"  python test_speech_by_case.py ALL    # 모든 케이스 순차 테스트")
    print(f"{'='*70}\n")
    
    import sys
    if len(sys.argv) < 2:
        print("❌ 사용법: python test_speech_by_case.py [A|B|C|FULL|ALL]")
        sys.exit(1)
    
    test_type = sys.argv[1].upper()
    
    if test_type == "ALL":
        for case_key in ["A", "B", "C"]:
            await run_case_test(case_key)
            await asyncio.sleep(5)  # Case 간 대기
    elif test_type in TEST_CASES:
        await run_case_test(test_type)
    else:
        print(f"❌ 잘못된 옵션: {test_type}")
        print(f"사용 가능: {', '.join(TEST_CASES.keys())}, ALL")

if __name__ == "__main__":
    asyncio.run(main())

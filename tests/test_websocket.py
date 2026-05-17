import asyncio
import websockets
import httpx

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

PATIENT_ID = "6d3ef730-2ac9-4290-8db2-31859bcc49a5"
AUDIO_FILE = "tests/audio/통화3.mp3"


async def test_full_pipeline():
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. 세션 시작
        print("=== 세션 시작 ===")
        response = await client.post(f"{BASE_URL}/calls", json={
            "patient_id": PATIENT_ID,
            "call_type": "voluntary"
        })
        print(f"상태코드: {response.status_code}")
        session_data = response.json()
        print(f"응답: {session_data}")

        if response.status_code != 200:
            print("세션 시작 실패!")
            return

        session_id = session_data["session_id"]

    # 2. WebSocket 연결 + 음성 전송
    print(f"\n=== WebSocket 연결 ===")
    uri = f"{WS_URL}/ws/calls?session_id={session_id}"

    async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
        with open(AUDIO_FILE, "rb") as f:
            audio_bytes = f.read()

        print(f"음성 파일 전송 ({len(audio_bytes)} bytes)")
        await ws.send(audio_bytes)

        # 응답 대기
        print("AI 응답 대기 중...")
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                if isinstance(msg, bytes):
                    print(f"음성 응답 수신 ({len(msg)} bytes)")
                    with open("tests/audio/response.mp3", "wb") as f:
                        f.write(msg)
                    print("응답 음성 저장 완료: tests/audio/response.mp3")
                elif msg == "END":
                    print("응답 완료!")
                    break
            except asyncio.TimeoutError:
                print("타임아웃 — 응답 없음")
                break

    # 3. 세션 종료
    print(f"\n=== 세션 종료 ===")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{BASE_URL}/calls/{session_id}")
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}")

    print("\n✅ 테스트 완료! DBeaver에서 확인:")
    print(f"SELECT * FROM messages WHERE session_id = '{session_id}';")
    print(f"SELECT * FROM working_memory WHERE session_id = '{session_id}';")
    print(f"SELECT * FROM daily_reports WHERE patient_id = '{PATIENT_ID}';")

asyncio.run(test_full_pipeline())
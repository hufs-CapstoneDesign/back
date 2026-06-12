import asyncio
import json
import httpx
import websockets
from app.config import settings

VITO_WS_URL = "wss://openapi.vito.ai/v1/transcribe:streaming"
SILENCE_THRESHOLD = 2.0
NO_FINAL_TIMEOUT = 3.0


async def get_vito_token() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openapi.vito.ai/v1/authenticate",
            data={
                "client_id": settings.VITO_CLIENT_ID,
                "client_secret": settings.VITO_CLIENT_SECRET,
            }
        )
        return response.json()["access_token"]


async def vito_streaming_stt(
    audio_queue: asyncio.Queue,
    text_queue: asyncio.Queue,
    stop_event: asyncio.Event,
    is_speaking: asyncio.Event,
):
    token = await get_vito_token()

    params = (
        "?sample_rate=16000"
        "&encoding=LINEAR16"
        "&use_itn=true"
        "&use_disfluency_filter=true"
        "&use_profanity_filter=false"
    )
    uri = f"{VITO_WS_URL}{params}"
    headers = {"Authorization": f"Bearer {token}"}

    async with websockets.connect(uri, additional_headers=headers) as ws:

        async def send_audio():
            while not stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                    if is_speaking.is_set():
                        continue
                    await ws.send(chunk)
                except asyncio.TimeoutError:
                    continue
            await ws.send("EOS")

        async def receive_text():
            last_final: str | None = None
            best_nonfinal: str | None = None
            flush_task: asyncio.Task | None = None
            nonfinal_fallback_task: asyncio.Task | None = None

            last_nonfinal_at: float = 0.0

            def cancel_task(t):
                if t and not t.done():
                    t.cancel()

            async def flush_after_silence():
                nonlocal last_final, best_nonfinal
                await asyncio.sleep(SILENCE_THRESHOLD)
                if is_speaking.is_set():
                    print("[STT] is_speaking 중 — is_speaking 해제 대기")
                    await is_speaking.wait()  # is_speaking이 clear될 때까지 대기
                    # clear 후 drain이 먼저 실행될 수 있으므로 last_final 재확인
                    if not last_final:
                        return
                if last_final:
                    text = last_final
                    last_final = None
                    best_nonfinal = None
                    print(f"[STT flush - final] {text}")
                    await text_queue.put(text)  
        
            async def nonfinal_fallback():
                """
                final이 오지 않는 엣지케이스 전용 안전망.
                조건을 엄격하게 제한:
                1. NO_FINAL_TIMEOUT 동안 새 non-final 업데이트가 없어야 함
                    (= 발화가 실제로 멈춘 상태)
                2. is_speaking 중이면 flush 안 함
                3. 이미 final을 받은 상태면 flush 안 함 (flush_task가 처리)
                """
                await asyncio.sleep(NO_FINAL_TIMEOUT)
                nonlocal last_final, best_nonfinal, last_nonfinal_at

                if is_speaking.is_set():
                    return
                if last_final is not None:
                    # final이 있으면 flush_after_silence가 처리
                    return
                if best_nonfinal is None:
                    return

                # 마지막 non-final 수신 후 실제로 NO_FINAL_TIMEOUT이 지났는지 재확인
                elapsed = asyncio.get_event_loop().time() - last_nonfinal_at
                if elapsed < NO_FINAL_TIMEOUT - 0.1:
                    # 새 non-final이 중간에 왔다면 이 task는 stale → 조용히 종료
                    return

                text = best_nonfinal
                best_nonfinal = None
                print(f"[STT flush - nonfinal fallback] {text}")
                await text_queue.put(text)

            async for raw in ws:
                print("VITO:", raw)
                msg = json.loads(raw)

                alternatives = msg.get("alternatives", [])
                if not alternatives:
                    continue

                text = alternatives[0].get("text", "").strip()
                if not text:
                    continue

                if msg.get("final"):
                    if is_speaking.is_set():
                        print(f"[STT] is_speaking 중 final 무시: {text}")
                        continue

                    last_final = text
                    best_nonfinal = None
                    cancel_task(nonfinal_fallback_task)  
                    cancel_task(flush_task)
                    flush_task = asyncio.create_task(flush_after_silence())
                
                else:
                    if is_speaking.is_set():
                        continue
                    if best_nonfinal is None or len(text) >= len(best_nonfinal):
                        best_nonfinal = text
                    last_nonfinal_at = asyncio.get_event_loop().time()
                    cancel_task(nonfinal_fallback_task)
                    nonfinal_fallback_task = asyncio.create_task(nonfinal_fallback())

            cancel_task(nonfinal_fallback_task)
            if flush_task and not flush_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(flush_task),
                        timeout=SILENCE_THRESHOLD + 0.5
                    )
                except asyncio.TimeoutError:
                    cancel_task(flush_task)
                    target = last_final or best_nonfinal
                    if target:
                        print(f"[STT flush - EOS timeout] {target}")
                        await text_queue.put(target)
                        last_final = None
                        best_nonfinal = None
            elif best_nonfinal and not last_final:
                print(f"[STT flush - EOS nonfinal] {best_nonfinal}")
                await text_queue.put(best_nonfinal)
                best_nonfinal = None

            await text_queue.put(None)
            print("[STT] EOS 센티널 전송")

        await asyncio.gather(send_audio(), receive_text())
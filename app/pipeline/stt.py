import asyncio
import json
import httpx
import websockets
from app.config import settings

VITO_WS_URL = "wss://openapi.vito.ai/v1/transcribe:streaming"
SILENCE_THRESHOLD = 3
NO_FINAL_TIMEOUT = 1.2


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
            utterance_buffer = []
            pending_nonfinal = None
            flush_task = None
            fallback_task = None

            def cancel_task(t):
                if t and not t.done():
                    t.cancel()

            async def flush_after_silence():
                """final=true 이후 SILENCE_THRESHOLD 동안 추가 final이 없으면 flush"""
                await asyncio.sleep(SILENCE_THRESHOLD)
                if utterance_buffer:
                    full_text = utterance_buffer[-1]
                    utterance_buffer.clear()
                    print(f"[STT flush - normal] {full_text}")
                    await text_queue.put(full_text)

            async def flush_after_no_final():
                await asyncio.sleep(NO_FINAL_TIMEOUT)
                nonlocal pending_nonfinal
                if pending_nonfinal:
                    text = pending_nonfinal
                    pending_nonfinal = None

                    candidates = utterance_buffer + [text]
                    full_text = max(candidates, key=len).strip()
                   
                    utterance_buffer.clear()
                    print(f"[STT flush - fallback] {full_text}")
                    await text_queue.put(full_text)

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
                    pending_nonfinal = None
                    cancel_task(fallback_task)
                    utterance_buffer.append(text)
                    cancel_task(flush_task)
                    flush_task = asyncio.create_task(flush_after_silence())
                else:
                    pending_nonfinal = text
                    cancel_task(fallback_task)
                    fallback_task = asyncio.create_task(flush_after_no_final())

            pending = [t for t in [flush_task, fallback_task] if t and not t.done()]
            if pending:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=SILENCE_THRESHOLD + 0.5
                    )
                except asyncio.TimeoutError:
                    if utterance_buffer:
                        full_text = utterance_buffer[-1]
                        utterance_buffer.clear()
                        print(f"[STT flush - timeout fallback] {full_text}")
                        await text_queue.put(full_text)

            await text_queue.put(None)
            print("[STT] EOS 센티널 전송")

        await asyncio.gather(send_audio(), receive_text())
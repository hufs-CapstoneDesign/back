import httpx
from app.config import settings

url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.VOICE_ID}/stream"

def _tts_payload(text: str) -> dict:
    return {
        "text": text,
        "model_id": "eleven_flash_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

def _tts_headers() -> dict:
    return {
        "xi-api-key": settings.ELEVENLABS_KEY,
        "Content-Type": "application/json",
    }


async def stream_tts(text: str):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST",
                url,
                headers=_tts_headers(),
                json=_tts_payload(text),
                params={"output_format": "pcm_16000"},
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise RuntimeError(f"ElevenLabs TTS 실패 (status={response.status_code}): {response.text}")
                response.raise_for_status()

                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"ElevenLabs TTS 실패 (status={e.response.status_code})")
    except httpx.TimeoutException:
        raise RuntimeError("ElevenLabs TTS timeout")
    except httpx.RequestError as e:
        raise RuntimeError(f"ElevenLabs 연결 실패: {e}")


async def generate_tts(text: str) -> bytes:
    """stream_tts를 모아서 bytes로 반환 (배치 필요 시 사용)"""
    return b"".join([chunk async for chunk in stream_tts(text)])
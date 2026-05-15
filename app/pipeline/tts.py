import httpx
from app.config import settings

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

async def stream_tts(text: str):
    """
    텍스트 → ElevenLabs TTS 스트리밍
    mp3 chunk를 async generator로 yield
    """
    url = ELEVENLABS_API_URL.format(voice_id=settings.VOICE_ID)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "xi-api-key": settings.ELEVENLABS_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_flash_v2_5",  # 한국어 지원
                    "output_format": "mp3_44100_128",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            ) as response:
                
                if response.status_code != 200:
                    error_text = await response.aread()

                    raise RuntimeError(
                        f"ElevenLabs TTS 실패 "
                        f"(status={response.status_code}): "
                        f"{error_text.decode(errors='ignore')}"
                    )


                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    except httpx.TimeoutException:
        raise RuntimeError("ElevenLabs TTS timeout")

    except httpx.RequestError as e:
        raise RuntimeError(
            f"ElevenLabs 연결 실패: {str(e)}"
        )

    except Exception as e:
        raise RuntimeError(
            f"TTS 처리 중 오류 발생: {str(e)}"
        )
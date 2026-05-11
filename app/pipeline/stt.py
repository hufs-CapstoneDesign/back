import httpx
from app.config import settings


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


async def transcribe(audio_bytes: bytes) -> str:
    """음성 바이트 → 텍스트"""
    token = await get_vito_token()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openapi.vito.ai/v1/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={
                "config": '{"language":"ko","use_itn":true}'
            }
        )
        result = response.json()
        # 전사 ID 받아서 결과 polling
        transcribe_id = result["id"]
        return await poll_transcribe_result(client, token, transcribe_id)


async def poll_transcribe_result(
    client: httpx.AsyncClient,
    token: str,
    transcribe_id: str,
) -> str:
    """전사 완료될 때까지 polling"""
    import asyncio

    for _ in range(30):  # 최대 30초 대기
        response = await client.get(
            f"https://openapi.vito.ai/v1/transcribe/{transcribe_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        result = response.json()

        if result["status"] == "completed":
            # 전체 텍스트 합치기
            utterances = result["results"]["utterances"]
            return " ".join([u["msg"] for u in utterances])

        elif result["status"] == "failed":
            raise Exception(f"STT 실패: {result}")

        await asyncio.sleep(1)

    raise Exception("STT 타임아웃")
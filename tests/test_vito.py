import asyncio
import httpx
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

async def test_vito_token():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openapi.vito.ai/v1/authenticate",
            data={
                "client_id": settings.VITO_CLIENT_ID,
                "client_secret": settings.VITO_CLIENT_SECRET,
            }
        )
        result = response.json()
        print(result)

asyncio.run(test_vito_token())
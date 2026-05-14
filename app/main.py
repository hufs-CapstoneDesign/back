from fastapi import FastAPI
import uvicorn
from app.config import settings
from app.api.auth import router as auth_router

app = FastAPI(title="CareMate API")

app.include_router(auth_router)

if __name__ == "__main__":
    uvicorn.run(
        app="app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=True,
    )
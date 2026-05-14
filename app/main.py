from fastapi import FastAPI
import uvicorn
from app.config import settings
from app.ws.websocket import router as ws_router
from app.api.session import router as session_router
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

app.include_router(ws_router)
app.include_router(session_router)
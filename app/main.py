from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.ws.websocket import router as ws_router
from app.api.session import router as session_router
from app.api.auth import router as auth_router
from app.api.reports import router as reports_router
from app.api.schedule import router as schedule_router
from app.api.conversations import router as conversations_router
from app.scheduler.scheduler import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield

app = FastAPI(title="CareMate API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중이니까 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(session_router)
app.include_router(reports_router)
app.include_router(schedule_router)
app.include_router(conversations_router)

if __name__ == "__main__":
    uvicorn.run(
        app="app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=True,
    )

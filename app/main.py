from fastapi import FastAPI
import uvicorn
from config import settings

app = FastAPI()

if __name__ == "__main__":
    uvicorn.run(
        app="main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=True,
    )
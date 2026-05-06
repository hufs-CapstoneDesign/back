from fastapi import FastAPI
import uvicorn
from config import setting

app = FastAPI()

if __name__ == "__main__":
    uvicorn.run(
        app="main:app",
        host="0.0.0.0",
        port=setting.APP_PORT,
        reload=True,
    )
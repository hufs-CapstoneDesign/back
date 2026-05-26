from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    APP_PORT: int
    WS_BASE_URL: str

    VITO_CLIENT_ID: str
    VITO_CLIENT_SECRET: str
    OPENAI_KEY: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    DATABASE_URL: str
    ELEVENLABS_KEY: str
    VOICE_ID: str
    FIREBASE_CREDENTIALS_PATH: str


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env"
        )


settings = Settings()
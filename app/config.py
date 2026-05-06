import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

class Setting(BaseSettings):
    APP_PORT: int

    VITO_CLIENT_ID: str
    VITO_CLIENT_SECRET: str


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env"
        )


setting = Setting()
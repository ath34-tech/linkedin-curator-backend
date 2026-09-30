import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'ath_radar.db'}"
    ENABLE_SCHEDULER: bool = True
    DAILY_DIGEST_TIME: str = "08:30"
    POSTING_REMINDER_TIME: str = "17:00"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Path to seed file
    ATH_MD_PATH: Path = DATA_DIR / "ath.md"

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"

settings = Settings()

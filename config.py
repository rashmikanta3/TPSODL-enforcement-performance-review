import os
from dotenv import load_dotenv

load_dotenv()

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "TPSODL Enforcement & Squad Operations Portal"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "tpsodl-secret-key-enforcement-ops-2026-super-secure")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./tpsodl.db")
    
    CIRCLES: list[str] = [
        "BERHAMPUR",
        "CITY",
        "ASKA",
        "BHANJANAGAR",
        "JEYPORE",
        "RAYAGADA"
    ]
    
    THEFT_TYPES: list[str] = [
        "Hooking",
        "Meter Tamper",
        "Bypass",
        "Misuse"
    ]
    
    OPERATION_MODES: list[str] = [
        "INDEPENDENT_WITH_TL",
        "INDEPENDENT_WITHOUT_TL_COLLECTION",
        "MERGED",
        "NON_OPERATIONAL"
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()


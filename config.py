import os
from dotenv import load_dotenv

load_dotenv()

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "TPSODL Enforcement & Squad Operations Portal"
    # Required: must be set in .env (no default, so a public fallback key is never used).
    SECRET_KEY: str
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

    # --- PVR module: Google Drive via the Apps Script Web App (apps_script/Code.gs) ---
    GOOGLE_APPS_SCRIPT_URL: str = ""
    GOOGLE_APPS_SCRIPT_SECRET: str = ""

    # --- PVR module limits / storage ---
    PVR_MAX_UPLOAD_MB: int = 25
    PVR_ZIP_MAX_DAYS: int = 62
    PVR_ZIP_MAX_FILES: int = 1000
    PVR_SPOOL_DIR: str = "/app/spool"      # local queue of PDFs waiting for Drive (Docker volume)

    # --- PVR PDF compression (runs in the background worker) ---
    PVR_COMPRESS_MODE: str = "balanced"     # off | lossless | balanced
    PVR_COMPRESS_DPI: int = 200
    PVR_JPEG_QUALITY: int = 85

    @property
    def gdrive_configured(self) -> bool:
        return bool(self.GOOGLE_APPS_SCRIPT_URL.strip() and self.GOOGLE_APPS_SCRIPT_SECRET.strip())

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()


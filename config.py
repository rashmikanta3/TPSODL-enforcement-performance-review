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

    # --- PVR module: Google Drive (Apps Script Web App / Service Account / Folder ID) ---
    GOOGLE_APPS_SCRIPT_URL: str = ""
    GOOGLE_APPS_SCRIPT_SECRET: str = ""
    GDRIVE_SERVICE_ACCOUNT_FILE: str = "tpsodl-enf.json"
    GDRIVE_ROOT_FOLDER_ID: str = "1MjeaI7UDzuAM9wxq4IMSbm-Jm0vcWCPg"
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""
    GOOGLE_DRIVE_PVR_FOLDER_ID: str = ""
    GDRIVE_FOLDER_ID: str = ""

    # Legacy OAuth fallback (optional)
    GDRIVE_CLIENT_ID: str = ""
    GDRIVE_CLIENT_SECRET: str = ""
    GDRIVE_REFRESH_TOKEN: str = ""
    GDRIVE_ROOT_FOLDER_NAME: str = "TPSODL_PVR"

    # --- PVR module limits ---
    PVR_MAX_UPLOAD_MB: int = 25
    PVR_ZIP_MAX_DAYS: int = 62
    PVR_ZIP_MAX_FILES: int = 1000

    @property
    def gdrive_configured(self) -> bool:
        load_dotenv(override=True)
        gas_url = (os.getenv("GOOGLE_APPS_SCRIPT_URL") or self.GOOGLE_APPS_SCRIPT_URL).strip()
        gas_sec = (os.getenv("GOOGLE_APPS_SCRIPT_SECRET") or self.GOOGLE_APPS_SCRIPT_SECRET).strip()
        if gas_url and gas_sec:
            return True
        sa_file = (
            os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE")
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
            or self.GDRIVE_SERVICE_ACCOUNT_FILE
            or self.GOOGLE_SERVICE_ACCOUNT_FILE
            or "tpsodl-enf.json"
        )
        folder_id = (
            os.getenv("GDRIVE_ROOT_FOLDER_ID")
            or os.getenv("GOOGLE_DRIVE_PVR_FOLDER_ID")
            or os.getenv("GDRIVE_FOLDER_ID")
            or self.GDRIVE_ROOT_FOLDER_ID
            or self.GOOGLE_DRIVE_PVR_FOLDER_ID
        )
        if os.path.exists(sa_file) and str(folder_id).strip():
            return True
        return bool(self.GDRIVE_CLIENT_ID.strip() and self.GDRIVE_CLIENT_SECRET.strip()
                    and self.GDRIVE_REFRESH_TOKEN.strip())

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()


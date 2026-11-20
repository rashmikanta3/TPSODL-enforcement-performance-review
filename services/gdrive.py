"""
Google Drive Storage Adapter.
Routes calls to services/gdrive_pvr.py (Google Apps Script Web App),
with legacy fallback support.
"""
import io
import logging
import re
from datetime import date
from typing import BinaryIO, Iterable, Optional

from services import gdrive_pvr

logger = logging.getLogger(__name__)

DriveNotConfigured = gdrive_pvr.DriveNotConfigured
DriveFileNotFound = gdrive_pvr.DriveFileNotFound

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def is_configured() -> bool:
    """True if Google Apps Script Web App or legacy credentials are configured."""
    return gdrive_pvr.is_configured()


def sanitize(name: str, max_len: int = 120) -> str:
    """Drive/ZIP safe name: drop / \\ : * ? " < > | and control chars, trim spaces."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:max_len].strip() or "Unnamed"


def pvr_folder_parts(pvr_date: date, tl_name: str) -> list[str]:
    """YYYY / MM-MonthName / DD-MM-YYYY / TL Name"""
    return [
        f"{pvr_date:%Y}",
        f"{pvr_date:%m}-{MONTHS[pvr_date.month - 1]}",
        f"{pvr_date:%d-%m-%Y}",
        sanitize(tl_name),
    ]


def pvr_file_name(pvr_date: date, circle: str, tl_code: str, tl_name: str) -> str:
    """PVR_20-11-2026_ASKA_TL045_Ramesh-Sahu.pdf"""
    dash = lambda s: re.sub(r"\s+", "-", sanitize(s))  # noqa: E731
    return f"PVR_{pvr_date:%d-%m-%Y}_{dash(circle)}_{dash(tl_code)}_{dash(tl_name)}.pdf"


def ensure_folder_path(parts: Iterable[str]) -> str:
    """
    Folder path handled automatically by Google Apps Script on upload.
    Returns a virtual folder path string.
    """
    return "/".join(parts)


def upload_pdf(
    local_path: str,
    filename: str,
    folder_id: str,
    pvr_date_str: Optional[str] = None,
    team_leader: Optional[str] = None
) -> str:
    """Uploads local PDF via Google Apps Script Web App."""
    with open(local_path, "rb") as f:
        file_bytes = f.read()

    # Extract date and TL name from folder_id or parameters if available
    d_str = pvr_date_str or date.today().strftime("%Y-%m-%d")
    tl_str = team_leader or "General"

    return gdrive_pvr.upload_pvr_to_drive(
        file_bytes=file_bytes,
        filename=filename,
        pvr_date_str=d_str,
        team_leader=tl_str
    )


def download_to_stream(file_id: str, fh: BinaryIO) -> None:
    """Writes downloaded bytes into a writable file object."""
    stream = gdrive_pvr.download_pvr_from_drive(file_id)
    fh.write(stream.getvalue())


def trash_file(file_id: str) -> None:
    """Deletes/trashes file via Google Apps Script Web App."""
    gdrive_pvr.delete_pvr_from_drive(file_id)


def move_and_rename(file_id: str, new_folder_id: str, new_name: str) -> None:
    """Placeholder for move/rename when using Google Apps Script."""
    logger.info("move_and_rename called for file %s -> %s", file_id, new_name)

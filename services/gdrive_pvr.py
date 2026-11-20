"""
Google Drive Storage Service via Google Apps Script Web App.

Relays PDF uploads, downloads, and deletions through a Google Apps Script Web App endpoint,
completely bypassing service account storage quota limits (403 storageQuotaExceeded) and OAuth token files.
"""
import base64
import io
import logging
import os
from typing import Tuple
from dotenv import load_dotenv
import requests

logger = logging.getLogger(__name__)


class DriveNotConfigured(RuntimeError):
    pass


class DriveFileNotFound(Exception):
    pass


def get_apps_script_config() -> Tuple[str, str]:
    """
    Reads GOOGLE_APPS_SCRIPT_URL and GOOGLE_APPS_SCRIPT_SECRET from environment.
    Always uses load_dotenv(override=True) to capture runtime updates.
    """
    load_dotenv(override=True)
    url = (os.getenv("GOOGLE_APPS_SCRIPT_URL") or "").strip()
    secret = (os.getenv("GOOGLE_APPS_SCRIPT_SECRET") or "").strip()
    return url, secret


def is_configured() -> bool:
    """True if Google Apps Script Web App URL and Secret are set in .env."""
    url, secret = get_apps_script_config()
    return bool(url and secret)


def upload_pvr_to_drive(
    file_bytes: bytes,
    filename: str,
    pvr_date_str: str,
    team_leader: str
) -> str:
    """
    Uploads PVR PDF bytes to Google Drive via the Google Apps Script Web App.

    Payload:
      {
        "secret": API_SECRET,
        "action": "upload",
        "pvrDate": pvr_date_str,
        "teamLeader": team_leader,
        "filename": filename,
        "fileBase64": b64_str
      }

    Returns: drive_file_id (str)
    """
    url, secret = get_apps_script_config()
    if not url or not secret:
        raise DriveNotConfigured(
            "Google Apps Script Web App URL or Secret not configured in .env "
            "(GOOGLE_APPS_SCRIPT_URL, GOOGLE_APPS_SCRIPT_SECRET)."
        )

    b64_str = base64.b64encode(file_bytes).decode("utf-8")
    payload = {
        "secret": secret,
        "action": "upload",
        "pvrDate": str(pvr_date_str),
        "teamLeader": str(team_leader).strip(),
        "filename": str(filename).strip(),
        "fileBase64": b64_str,
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            allow_redirects=True,
            timeout=60
        )
    except Exception as e:
        logger.error("Failed to connect to Google Apps Script Web App: %s", e)
        raise RuntimeError(f"Connection to Google Apps Script Web App failed: {str(e)}")

    if resp.status_code != 200:
        logger.error("Google Apps Script HTTP %d: %s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"Google Apps Script HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        resp_json = resp.json()
    except Exception:
        logger.error("Non-JSON response from Google Apps Script: %s", resp.text[:500])
        raise RuntimeError(f"Invalid response from Google Apps Script: {resp.text[:200]}")

    if resp_json.get("status") != "success":
        err_msg = resp_json.get("message") or resp_json.get("error") or "Upload via Google Apps Script failed."
        logger.error("Google Apps Script upload error: %s", err_msg)
        raise RuntimeError(err_msg)

    file_id = resp_json.get("fileId")
    if not file_id:
        raise RuntimeError("Google Apps Script returned success but 'fileId' was missing.")

    return str(file_id)


def download_pvr_from_drive(drive_file_id: str) -> io.BytesIO:
    """
    Downloads PVR PDF bytes from Google Drive via the Google Apps Script Web App.

    Query params:
      {"secret": API_SECRET, "fileId": drive_file_id}

    Returns: io.BytesIO stream containing the decoded PDF bytes.
    """
    url, secret = get_apps_script_config()
    if not url or not secret:
        raise DriveNotConfigured(
            "Google Apps Script Web App URL or Secret not configured in .env."
        )

    params = {
        "secret": secret,
        "fileId": str(drive_file_id).strip()
    }

    try:
        resp = requests.get(
            url,
            params=params,
            allow_redirects=True,
            timeout=60
        )
    except Exception as e:
        logger.error("Failed to download from Google Apps Script Web App: %s", e)
        raise RuntimeError(f"Connection to Google Apps Script Web App failed: {str(e)}")

    if resp.status_code == 404:
        raise DriveFileNotFound(f"File {drive_file_id} not found in Google Drive.")

    if resp.status_code != 200:
        logger.error("Google Apps Script HTTP %d: %s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"Google Apps Script HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        resp_json = resp.json()
    except Exception:
        raise RuntimeError(f"Invalid response from Google Apps Script: {resp.text[:200]}")

    if resp_json.get("status") != "success":
        err_msg = resp_json.get("message") or resp_json.get("error") or "Download failed."
        if "not found" in err_msg.lower():
            raise DriveFileNotFound(err_msg)
        raise RuntimeError(err_msg)

    b64_content = resp_json.get("fileBase64")
    if not b64_content:
        raise RuntimeError("Google Apps Script response did not contain 'fileBase64'.")

    file_bytes = base64.b64decode(b64_content)
    return io.BytesIO(file_bytes)


def delete_pvr_from_drive(drive_file_id: str) -> bool:
    """
    Deletes a PVR PDF file from Google Drive via the Google Apps Script Web App.

    Payload:
      {"secret": API_SECRET, "action": "delete", "fileId": drive_file_id}

    Returns: bool (True on success)
    """
    url, secret = get_apps_script_config()
    if not url or not secret:
        logger.warning("Google Apps Script not configured; skipping Drive file deletion.")
        return False

    payload = {
        "secret": secret,
        "action": "delete",
        "fileId": str(drive_file_id).strip()
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            allow_redirects=True,
            timeout=60
        )
        resp_json = resp.json()
        if resp_json.get("status") != "success":
            logger.warning(
                "Google Apps Script delete warning for file %s: %s",
                drive_file_id, resp_json.get("message")
            )
            return False
        return True
    except Exception as e:
        logger.warning("Google Apps Script delete request failed for file %s: %s", drive_file_id, e)
        return False

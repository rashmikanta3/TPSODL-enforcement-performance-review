"""
Google Drive storage for PVR PDFs.

The Apps Script Web App (apps_script/Code.gs) is used only as a small control plane:
  * action "token"  -> short-lived OAuth access token of the Drive owner
  * action "folder" -> id of TPSODL_PVR/YYYY/MM-Month/DD-MM-YYYY/<TL> (created if needed)
  * action "move"   -> fallback move/rename
Bytes go straight to the Drive REST API (resumable upload in 8 MB chunks, streamed
downloads) - no base64, no 50 MB Apps Script limit.

If the "token" action is unavailable (old script deployed), every operation falls back
to the original base64 Apps Script actions (upload / delete / doGet download).

All functions are blocking; call them from the worker thread or sync endpoints.
"""
import base64
import logging
import os
import random
import re
import threading
import time
from datetime import date
from typing import BinaryIO, Iterator, Optional, Tuple

import requests

from config import settings

logger = logging.getLogger(__name__)

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
CHUNK = 8 * 1024 * 1024            # resumable chunk (multiple of 256 KiB)
MAX_TRIES = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}
TOKEN_TTL = 45 * 60                # Apps Script tokens live ~60 min; refresh well before
FALLBACK_RECHECK = 5 * 60          # after a failed "token" call, retry direct mode after 5 min

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


class DriveNotConfigured(RuntimeError):
    pass


class DriveFileNotFound(Exception):
    pass


class DriveError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Naming helpers (folder layout is part of the contract with Code.gs)
# ---------------------------------------------------------------------------
def is_configured() -> bool:
    return settings.gdrive_configured


def sanitize(name: str, max_len: int = 120) -> str:
    """Drive/ZIP safe name: drop / \\ : * ? " < > | and control chars, trim spaces."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:max_len].strip() or "Unnamed"


def pvr_folder_parts(pvr_date: date, tl_name: str) -> list[str]:
    """YYYY / MM-MonthName / DD-MM-YYYY / TL Name   (under TPSODL_PVR in Drive)"""
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


# ---------------------------------------------------------------------------
# Apps Script calls
# ---------------------------------------------------------------------------
_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
    return s


def _gas_config() -> Tuple[str, str]:
    if not is_configured():
        raise DriveNotConfigured("GOOGLE_APPS_SCRIPT_URL / GOOGLE_APPS_SCRIPT_SECRET are not set in .env.")
    return settings.GOOGLE_APPS_SCRIPT_URL.strip(), settings.GOOGLE_APPS_SCRIPT_SECRET.strip()


def _gas_json(resp: requests.Response, what: str) -> dict:
    if resp.status_code != 200:
        raise DriveError(f"Apps Script {what}: HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError:
        raise DriveError(f"Apps Script {what}: non-JSON reply: {resp.text[:200]}")
    if data.get("status") != "success":
        msg = data.get("message") or data.get("error") or f"{what} failed"
        if "not found" in msg.lower():
            raise DriveFileNotFound(msg)
        raise DriveError(f"Apps Script {what}: {msg}")
    return data


def _gas_post(payload: dict, what: str, timeout: int = 60) -> dict:
    url, secret = _gas_config()
    try:
        resp = _session().post(url, json={"secret": secret, **payload}, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise DriveError(f"Apps Script {what}: {e}") from e
    return _gas_json(resp, what)


# ---------------------------------------------------------------------------
# Token (direct mode) with automatic fallback
# ---------------------------------------------------------------------------
_token_lock = threading.Lock()
_token = {"value": None, "expires": 0.0}
_fallback_until = 0.0


def _get_token(force: bool = False) -> str:
    with _token_lock:
        if not force and _token["value"] and time.time() < _token["expires"]:
            return _token["value"]
        data = _gas_post({"action": "token"}, "token", timeout=30)
        tok = data.get("accessToken")
        if not tok:
            raise DriveError("Apps Script token action returned no accessToken")
        ttl = min(int(data.get("expiresIn") or 3000), TOKEN_TTL)
        _token.update(value=tok, expires=time.time() + ttl)
        return tok


def direct_mode() -> bool:
    """True when the Drive REST API can be used; False -> base64 Apps Script fallback."""
    global _fallback_until
    _gas_config()
    if time.time() < _fallback_until:
        return False
    try:
        _get_token()
        return True
    except DriveNotConfigured:
        raise
    except Exception as e:
        _fallback_until = time.time() + FALLBACK_RECHECK
        logger.warning("Drive direct mode unavailable (%s); using base64 Apps Script fallback", e)
        return False


def _backoff(attempt: int):
    time.sleep(min(20.0, (2 ** attempt) + random.random()))


def _drive(method: str, url: str, **kw) -> requests.Response:
    """Drive REST call with bearer token, 401 refresh and 429/5xx backoff."""
    force = False
    last = None
    for attempt in range(MAX_TRIES):
        headers = dict(kw.pop("headers", None) or {}, Authorization=f"Bearer {_get_token(force)}")
        force = False
        try:
            r = _session().request(method, url, headers=headers, timeout=(10, 120), **kw)
        except requests.RequestException as e:
            last = e
            _backoff(attempt)
            kw["headers"] = {k: v for k, v in headers.items() if k != "Authorization"}
            continue
        if r.status_code == 401:
            force = True
        elif r.status_code in RETRY_STATUSES:
            _backoff(attempt)
        else:
            return r
        last = f"HTTP {r.status_code}: {r.text[:200]}"
        kw["headers"] = {k: v for k, v in headers.items() if k != "Authorization"}
    raise DriveError(f"Drive {method} failed after {MAX_TRIES} tries: {last}")


def _check(r: requests.Response, what: str) -> requests.Response:
    if r.status_code == 404:
        raise DriveFileNotFound(f"{what}: not found")
    if r.status_code >= 400:
        raise DriveError(f"Drive {what}: HTTP {r.status_code}: {r.text[:200]}")
    return r


# ---------------------------------------------------------------------------
# Folders (memory + pvr_drive_folders table + Apps Script "folder" action)
# ---------------------------------------------------------------------------
_folders: dict[str, str] = {}
_folder_lock = threading.Lock()


def _db_folder(path: str, folder_id: Optional[str] = None, delete: bool = False) -> Optional[str]:
    from database import SessionLocal
    from models import PVRDriveFolder
    db = SessionLocal()
    try:
        row = db.query(PVRDriveFolder).filter(PVRDriveFolder.path == path).first()
        if delete:
            if row:
                db.delete(row)
                db.commit()
            return None
        if folder_id is None:
            return row.folder_id if row else None
        if row:
            row.folder_id = folder_id
        else:
            db.add(PVRDriveFolder(path=path, folder_id=folder_id))
        db.commit()
        return folder_id
    except Exception as e:  # cache only: never fail an upload because of it
        db.rollback()
        logger.warning("pvr_drive_folders cache error for %s: %s", path, e)
        return None
    finally:
        db.close()


def folder_for(pvr_date: date, tl_name: str, refresh: bool = False) -> str:
    parts = pvr_folder_parts(pvr_date, tl_name)
    path = "/".join(parts)
    with _folder_lock:
        if refresh:
            _folders.pop(path, None)
            _db_folder(path, delete=True)
        fid = _folders.get(path) or _db_folder(path)
        if not fid:
            fid = _gas_post({"action": "folder", "pvrDate": pvr_date.isoformat(), "teamLeader": parts[-1]},
                            "folder")["folderId"]
            _db_folder(path, fid)
        _folders[path] = fid
        return fid


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def _resumable_upload(path: str, name: str, folder_id: str) -> str:
    size = os.path.getsize(path)
    init = _check(_drive(
        "POST", f"{DRIVE_UPLOAD}/files?uploadType=resumable&supportsAllDrives=true&fields=id",
        json={"name": name, "parents": [folder_id], "mimeType": "application/pdf"},
        headers={"X-Upload-Content-Type": "application/pdf", "X-Upload-Content-Length": str(size)},
    ), "upload init")
    session_url = init.headers["Location"]

    offset, failures = 0, 0
    with open(path, "rb") as f:
        while True:
            f.seek(offset)
            chunk = f.read(CHUNK)
            end = offset + len(chunk) - 1
            try:
                r = _session().put(session_url, data=chunk, timeout=(10, 300), headers={
                    "Authorization": f"Bearer {_get_token()}",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                })
                code = r.status_code
            except requests.RequestException as e:
                r, code = None, f"network: {e}"

            if code in (200, 201):
                return r.json()["id"]
            if code == 308:
                rng = r.headers.get("Range")
                offset = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
                failures = 0
                continue
            if code == 404:
                raise DriveError("Resumable upload session expired")
            # 401 / 429 / 5xx / network: ask Drive how much it has, then resume
            failures += 1
            if failures >= MAX_TRIES:
                raise DriveError(f"Resumable upload failed at byte {offset}: {code}")
            if code == 401:
                _get_token(force=True)
            else:
                _backoff(failures)
            try:
                st = _session().put(session_url, timeout=(10, 60), headers={
                    "Authorization": f"Bearer {_get_token()}", "Content-Range": f"bytes */{size}",
                    "Content-Length": "0"})
                if st.status_code in (200, 201):
                    return st.json()["id"]
                if st.status_code == 308:
                    rng = st.headers.get("Range")
                    offset = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
            except requests.RequestException:
                pass


def _gas_upload(path: str, name: str, pvr_date: date, tl_name: str) -> str:
    with open(path, "rb") as f:   # fallback only: Apps Script needs the whole file as base64
        b64 = base64.b64encode(f.read()).decode("ascii")
    data = _gas_post({"action": "upload", "pvrDate": pvr_date.isoformat(), "teamLeader": sanitize(tl_name),
                      "filename": name, "fileBase64": b64}, "upload", timeout=300)
    if not data.get("fileId"):
        raise DriveError("Apps Script upload returned no fileId")
    return str(data["fileId"])


def upload_pvr(path: str, name: str, pvr_date: date, tl_name: str) -> Tuple[str, Optional[str]]:
    """Upload a local PDF into the PVR folder. Returns (file_id, folder_id)."""
    if not direct_mode():
        return _gas_upload(path, name, pvr_date, tl_name), None
    folder_id = folder_for(pvr_date, tl_name)
    try:
        return _resumable_upload(path, name, folder_id), folder_id
    except DriveFileNotFound:
        # cached folder was deleted/trashed by hand -> resolve again once
        logger.warning("Drive folder %s missing; resolving again", folder_id)
        folder_id = folder_for(pvr_date, tl_name, refresh=True)
        return _resumable_upload(path, name, folder_id), folder_id


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def _gas_download(file_id: str) -> bytes:
    url, secret = _gas_config()
    try:
        resp = _session().get(url, params={"secret": secret, "fileId": file_id}, timeout=120)
    except requests.RequestException as e:
        raise DriveError(f"Apps Script download: {e}") from e
    if resp.status_code == 404:
        raise DriveFileNotFound(file_id)
    data = _gas_json(resp, "download")
    if not data.get("fileBase64"):
        raise DriveError("Apps Script download returned no data")
    return base64.b64decode(data["fileBase64"])


def open_stream(file_id: str, chunk: int = 1024 * 1024) -> Iterator[bytes]:
    """
    Start a download and return an iterator over its bytes. Errors (404 etc.) are raised
    here, before the first byte, so callers can still send a proper HTTP error.
    """
    if not direct_mode():
        data = _gas_download(file_id)
        return iter([data])
    r = _check(_drive("GET", f"{DRIVE_API}/files/{file_id}?alt=media&supportsAllDrives=true", stream=True),
               f"download {file_id}")

    def gen():
        try:
            yield from r.iter_content(chunk)
        finally:
            r.close()
    return gen()


def download_to_file(file_id: str, fh: BinaryIO) -> int:
    n = 0
    for part in open_stream(file_id):
        fh.write(part)
        n += len(part)
    return n


# ---------------------------------------------------------------------------
# Trash / move
# ---------------------------------------------------------------------------
def trash(file_id: Optional[str]) -> None:
    """Move to Drive trash (recoverable for 30 days). Missing files are ignored."""
    if not file_id:
        return
    try:
        if direct_mode():
            _check(_drive("PATCH", f"{DRIVE_API}/files/{file_id}?supportsAllDrives=true&fields=id",
                          json={"trashed": True}), f"trash {file_id}")
        else:
            _gas_post({"action": "delete", "fileId": file_id}, "delete")
    except DriveFileNotFound:
        logger.warning("Drive file %s already gone when trashing", file_id)


def move_pvr(file_id: str, pvr_date: date, tl_name: str, new_name: str) -> Optional[str]:
    """Move a PVR file into the folder for (date, TL) and rename it. Returns the folder id."""
    if not direct_mode():
        data = _gas_post({"action": "move", "fileId": file_id, "pvrDate": pvr_date.isoformat(),
                          "teamLeader": sanitize(tl_name), "newName": new_name}, "move")
        return data.get("folderId")
    folder_id = folder_for(pvr_date, tl_name)
    meta = _check(_drive("GET", f"{DRIVE_API}/files/{file_id}?fields=parents&supportsAllDrives=true"),
                  f"get {file_id}").json()
    parents = meta.get("parents", [])
    params = {"supportsAllDrives": "true", "fields": "id"}
    if folder_id not in parents:
        params["addParents"] = folder_id
    old = ",".join(p for p in parents if p != folder_id)
    if old:
        params["removeParents"] = old
    _check(_drive("PATCH", f"{DRIVE_API}/files/{file_id}", params=params, json={"name": new_name}),
           f"move {file_id}")
    return folder_id

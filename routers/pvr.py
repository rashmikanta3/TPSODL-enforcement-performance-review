"""
PVR (Physical Verification Report) module: upload / view / download.

PDFs live in Google Drive (services/gdrive.py); metadata in pvr_uploads.
Endpoints are plain `def` on purpose: FastAPI runs them in the threadpool, so the
blocking Drive + DB calls never block the event loop.

Auth: every endpoint requires a real JWT session (access_token cookie or Bearer);
the spoofable x-user-* headers are NOT accepted here.
"""
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status, Response
from fastapi.responses import FileResponse
from google.auth.exceptions import RefreshError
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from auth import get_current_user_optional, verify_team_permission, verify_write_permission
from config import settings
from database import get_db
from models import (DailyTeamOperation, PVRAuditLog, PVRUpload, Team, TeamLead, User,
                    get_assigned_circles, is_circle_authorized)
from services import gdrive, gdrive_pvr

logger = logging.getLogger(__name__)
router = APIRouter()

IST = pytz.timezone("Asia/Kolkata")
CITY_SYNONYMS = {"CITY", "BERHAMPUR CITY"}
NOT_CONFIGURED_MSG = (
    "Google Apps Script Web App not configured. Please ensure GOOGLE_APPS_SCRIPT_URL "
    "and GOOGLE_APPS_SCRIPT_SECRET are set in .env."
)


# =========================================================================
# Helpers: auth, visibility, validation
# =========================================================================
def require_user(current_user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Your session has expired. Please sign in again.")
    return current_user


def require_admin(current_user: User = Depends(require_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only ADMIN users can edit, re-upload or delete PVRs.")
    return current_user


def require_drive():
    if not (gdrive_pvr.is_configured() or gdrive.is_configured()):
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MSG)


def canon_circle(circle: Optional[str]) -> str:
    """Canonical circle spelling = settings.CIRCLES (DB uses 'CITY')."""
    c = (circle or "").strip().upper()
    return "CITY" if c in CITY_SYNONYMS else c


def circle_variants(circle: str) -> List[str]:
    c = canon_circle(circle)
    return sorted(CITY_SYNONYMS) if c == "CITY" else [c]


def authorized_circles(user: User) -> List[str]:
    if user.role == "ADMIN":
        return list(settings.CIRCLES)
    mine = {canon_circle(c) for c in get_assigned_circles(user)}
    return [c for c in settings.CIRCLES if c in mine]


def apply_visibility(q, user: User):
    """ADMIN: all. SUB_ADMIN: authorized circles. USER: own team only."""
    if user.role == "ADMIN":
        return q
    if user.role == "SUB_ADMIN":
        allowed = []
        for c in authorized_circles(user):
            allowed += circle_variants(c)
        return q.filter(PVRUpload.circle.in_(allowed or ["__none__"]))
    if user.role == "USER" and user.team_id:
        return q.filter(PVRUpload.team_id == user.team_id)
    return q.filter(PVRUpload.id == -1)  # nothing


def can_see(user: User, pvr: PVRUpload) -> bool:
    if user.role == "ADMIN":
        return True
    if user.role == "SUB_ADMIN":
        return is_circle_authorized(user, pvr.circle)
    return user.role == "USER" and bool(user.team_id) and pvr.team_id == user.team_id


def get_visible_pvr(db: Session, user: User, pvr_id: int) -> PVRUpload:
    pvr = db.get(PVRUpload, pvr_id)
    # 404 (not 403) so ids of other teams' PVRs cannot be probed
    if not pvr or not can_see(user, pvr):
        raise HTTPException(status_code=404, detail="PVR not found.")
    return pvr


def today_ist() -> date:
    return datetime.now(IST).date()


def check_not_future(d: date):
    if d > today_ist():
        raise HTTPException(status_code=400, detail="PVR date cannot be in the future.")


def load_team_and_tl(db: Session, circle: str, team_id: int, team_lead_id: int):
    variants = circle_variants(circle)
    team = db.query(Team).filter(Team.id == team_id, Team.is_active == True).first()  # noqa: E712
    if not team or canon_circle(team.circle) not in {canon_circle(v) for v in variants}:
        raise HTTPException(status_code=400, detail="Selected team is not an active team of this circle.")
    tl = db.query(TeamLead).filter(TeamLead.id == team_lead_id, TeamLead.is_active == True).first()  # noqa: E712
    if not tl or canon_circle(tl.circle) != canon_circle(circle):
        raise HTTPException(status_code=400, detail="Selected team leader is not an active TL of this circle.")
    return team, tl


def user_fk(user: User) -> Optional[int]:
    return user.id if getattr(user, "id", None) else None


def audit(db: Session, pvr_id: Optional[int], action: str, user: User, **details):
    db.add(PVRAuditLog(pvr_id=pvr_id, action=action, user_id=user_fk(user), username=user.username,
                       details=json.dumps(details, default=str)))


def save_upload_to_temp(file: UploadFile) -> tuple[str, int]:
    """Copy the upload to a temp file (size-capped), validate %PDF magic. Returns (path, size)."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    max_bytes = settings.PVR_MAX_UPLOAD_MB * 1024 * 1024
    fd, path = tempfile.mkstemp(prefix="pvr_", suffix=".pdf")
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            first = True
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                if first:
                    if not chunk.lstrip(b"\r\n\t \x00\xef\xbb\xbf")[:4] == b"%PDF":
                        raise HTTPException(status_code=400,
                                            detail="This file is not a real PDF (it may just be renamed to .pdf).")
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=400,
                                        detail=f"File is larger than the {settings.PVR_MAX_UPLOAD_MB} MB limit.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        return path, size
    except Exception:
        remove_quietly(path)
        raise


def count_pages(path: str) -> Optional[int]:
    try:
        from pypdf import PdfReader
        return len(PdfReader(path, strict=False).pages)
    except Exception as e:
        logger.warning("Could not count PDF pages: %s", e)
        return None


def remove_quietly(path: Optional[str]):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


def drive_error(e: Exception) -> HTTPException:
    if isinstance(e, (gdrive.DriveNotConfigured, gdrive_pvr.DriveNotConfigured)):
        return HTTPException(status_code=503, detail=NOT_CONFIGURED_MSG)
    if isinstance(e, (gdrive.DriveFileNotFound, gdrive_pvr.DriveFileNotFound)):
        return HTTPException(status_code=404, detail="The PDF is missing in Google Drive.")
    logger.error("Google Drive / Apps Script error: %s", e, exc_info=True)
    return HTTPException(status_code=502, detail=f"Google Drive service error: {str(e)}")


def serialize(p: PVRUpload, user: User) -> dict:
    return {
        "id": p.id,
        "pvr_date": p.pvr_date.isoformat(),
        "circle": p.circle,
        "team_id": p.team_id,
        "team_name": p.team_name,
        "team_lead_id": p.team_lead_id,
        "tl_code": p.team_lead.tl_code if p.team_lead else None,
        "tl_name": p.tl_name,
        "file_name": p.file_name,
        "file_size": p.file_size,
        "page_count": p.page_count,
        "uploaded_by": p.uploader.username if p.uploader else None,
        "uploaded_at": p.uploaded_at.isoformat() + "Z" if p.uploaded_at else None,
        "updated_by": p.updater.username if p.updater else None,
        "updated_at": p.updated_at.isoformat() + "Z" if p.updated_at else None,
        "can_view": can_see(user, p),
    }


def place_in_drive(pvr_date: date, circle: str, tl: TeamLead):
    folder_id = gdrive.ensure_folder_path(gdrive.pvr_folder_parts(pvr_date, tl.name))
    return folder_id, gdrive.pvr_file_name(pvr_date, circle, tl.tl_code, tl.name)


def find_duplicate(db: Session, pvr_date: date, team_lead_id: int, exclude_id: Optional[int] = None):
    q = db.query(PVRUpload).filter(PVRUpload.pvr_date == pvr_date, PVRUpload.team_lead_id == team_lead_id)
    if exclude_id:
        q = q.filter(PVRUpload.id != exclude_id)
    return q.first()


def duplicate_detail(dup: PVRUpload) -> str:
    who = dup.uploader.username if dup.uploader else "another user"
    when = dup.uploaded_at.replace(tzinfo=pytz.utc).astimezone(IST).strftime("%d-%m-%Y %I:%M %p") \
        if dup.uploaded_at else "-"
    return f"PVR already uploaded by {who} on {when} for this team leader and date."


# =========================================================================
# Status + options
# =========================================================================
@router.get("/status")
def pvr_status(user: User = Depends(require_user)):
    return {
        "drive_configured": gdrive.is_configured(),
        "message": None if gdrive.is_configured() else NOT_CONFIGURED_MSG,
        "max_upload_mb": settings.PVR_MAX_UPLOAD_MB,
        "zip_max_days": settings.PVR_ZIP_MAX_DAYS,
        "zip_max_files": settings.PVR_ZIP_MAX_FILES,
        "today": today_ist().isoformat(),
        "user": {"username": user.username, "role": user.role, "team_id": user.team_id,
                 "can_edit": user.can_edit, "circles": authorized_circles(user)},
    }


@router.get("/options")
def pvr_options(
    circle: Optional[str] = Query(None),
    date_: Optional[date] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Authorized circles; with ?circle= also active teams, TLs and the suggested TL per team."""
    circles = authorized_circles(user)
    out = {"circles": circles, "teams": [], "team_leads": [], "suggested_tl": {},
           "locked_team_id": None, "locked_circle": None}
    if user.role == "USER":
        own = db.get(Team, user.team_id) if user.team_id else None
        if own:
            out["locked_team_id"], out["locked_circle"] = own.id, canon_circle(own.circle)
            if out["locked_circle"] not in circles:
                circles.append(out["locked_circle"])
    if not circle:
        return out

    c = canon_circle(circle)
    if c not in circles:
        raise HTTPException(status_code=403, detail=f"You are not authorized for circle {c}.")
    variants = circle_variants(c)

    teams_q = db.query(Team).filter(Team.is_active == True, Team.circle.in_(variants))  # noqa: E712
    if user.role == "USER":
        teams_q = teams_q.filter(Team.id == (user.team_id or -1))
    teams = teams_q.order_by(Team.name).all()
    tls = db.query(TeamLead).filter(TeamLead.is_active == True, TeamLead.circle.in_(variants)) \
        .order_by(TeamLead.name).all()  # noqa: E712
    active_tl_ids = {t.id for t in tls}

    daily = {}
    if date_ and teams:
        for op in db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == date_,
            DailyTeamOperation.team_id.in_([t.id for t in teams]),
        ):
            if op.daily_tl_id:
                daily[op.team_id] = op.daily_tl_id

    suggested = {}
    for t in teams:
        tl_id = daily.get(t.id) or t.default_tl_id
        if tl_id in active_tl_ids:
            suggested[str(t.id)] = tl_id

    out.update(
        teams=[{"id": t.id, "name": t.name} for t in teams],
        team_leads=[{"id": t.id, "tl_code": t.tl_code, "name": t.name} for t in tls],
        suggested_tl=suggested,
    )
    return out


@router.get("/check")
def pvr_check(
    date_: date = Query(..., alias="date"),
    team_lead_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    dup = find_duplicate(db, date_, team_lead_id)
    if not dup:
        return {"exists": False}
    return {"exists": True, "message": duplicate_detail(dup),
            "pvr": serialize(dup, user) if can_see(user, dup) else None}


# =========================================================================
# Upload
# =========================================================================
@router.post("/upload")
def pvr_upload(
    pvr_date: date = Form(..., alias="date"),
    circle: str = Form(...),
    team_id: int = Form(...),
    team_lead_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_drive()
    c = canon_circle(circle)
    verify_write_permission(user, c)
    if user.role == "USER":
        verify_team_permission(user, team_id)
    check_not_future(pvr_date)
    team, tl = load_team_and_tl(db, c, team_id, team_lead_id)

    dup = find_duplicate(db, pvr_date, tl.id)
    if dup:
        raise HTTPException(status_code=409, detail=duplicate_detail(dup))

    tmp_path = None
    file_id = None
    try:
        tmp_path, size = save_upload_to_temp(file)
        pages = count_pages(tmp_path)
        with open(tmp_path, "rb") as f:
            file_bytes = f.read()

        pvr_date_str = pvr_date.strftime("%Y-%m-%d")
        fname = gdrive.pvr_file_name(pvr_date, c, tl.tl_code, tl.name)
        folder_id = "/".join(gdrive.pvr_folder_parts(pvr_date, tl.name))

        try:
            file_id = gdrive_pvr.upload_pvr_to_drive(
                file_bytes=file_bytes,
                filename=fname,
                pvr_date_str=pvr_date_str,
                team_leader=tl.name
            )
        except Exception as e:
            raise drive_error(e)

        pvr = PVRUpload(
            pvr_date=pvr_date, circle=c, team_id=team.id, team_lead_id=tl.id,
            team_name=team.name, tl_name=tl.name, drive_file_id=file_id, drive_folder_id=folder_id,
            file_name=fname, file_size=size, page_count=pages, uploaded_by=user_fk(user),
        )
        db.add(pvr)
        try:
            db.flush()
            audit(db, pvr.id, "UPLOAD", user, drive_file_id=file_id, file_name=fname, size=size,
                  original_name=file.filename)
            db.commit()
        except IntegrityError:
            db.rollback()
            gdrive_pvr.delete_pvr_from_drive(file_id)          # no orphans from a lost race
            dup = find_duplicate(db, pvr_date, tl.id)
            raise HTTPException(status_code=409, detail=duplicate_detail(dup) if dup else
                                "A PVR for this team leader and date was just uploaded by someone else.")
        except Exception:
            db.rollback()
            gdrive_pvr.delete_pvr_from_drive(file_id)
            raise
        db.refresh(pvr)
        return {"success": True, "pvr": serialize(pvr, user)}
    finally:
        remove_quietly(tmp_path)


# =========================================================================
# List (with pending TLs)
# =========================================================================
@router.get("/list")
def pvr_list(
    date_: date = Query(..., alias="date"),
    circle: Optional[str] = Query(None),
    team_lead_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    q = apply_visibility(db.query(PVRUpload).filter(PVRUpload.pvr_date == date_), user)
    circles = authorized_circles(user)
    if circle and circle.upper() != "ALL":
        c = canon_circle(circle)
        if c not in circles:
            raise HTTPException(status_code=403, detail=f"You are not authorized for circle {c}.")
        circles = [c]
        q = q.filter(PVRUpload.circle.in_(circle_variants(c)))
    if team_lead_id:
        q = q.filter(PVRUpload.team_lead_id == team_lead_id)
    rows = q.order_by(PVRUpload.circle, PVRUpload.tl_name).all()

    # Pending = active TLs (in scope) without a PVR for this date
    pending = []
    if user.role in ("ADMIN", "SUB_ADMIN"):
        variants = [v for c in circles for v in circle_variants(c)]
        tl_q = db.query(TeamLead).filter(TeamLead.is_active == True, TeamLead.circle.in_(variants))  # noqa: E712
        if team_lead_id:
            tl_q = tl_q.filter(TeamLead.id == team_lead_id)
        done = {tl_id for (tl_id,) in db.query(PVRUpload.team_lead_id).filter(PVRUpload.pvr_date == date_)}
        pending = [{"id": t.id, "tl_code": t.tl_code, "name": t.name, "circle": canon_circle(t.circle)}
                   for t in tl_q.order_by(TeamLead.circle, TeamLead.name) if t.id not in done]

    return {"rows": [serialize(r, user) for r in rows], "pending": pending}


# =========================================================================
# Single file (inline view / attachment download)
# =========================================================================
@router.get("/{pvr_id}/file")
def pvr_file(
    pvr_id: int,
    inline: int = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    pvr = get_visible_pvr(db, user, pvr_id)
    require_drive()
    try:
        stream = gdrive_pvr.download_pvr_from_drive(pvr.drive_file_id)
    except gdrive_pvr.DriveFileNotFound:
        raise HTTPException(status_code=404, detail="The PDF is missing in Google Drive (it may have been deleted).")
    except Exception as e:
        raise drive_error(e)

    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{pvr.file_name}"',
        "Content-Type": "application/pdf"
    }
    return Response(content=stream.getvalue(), media_type="application/pdf", headers=headers)


@router.get("/file/{drive_file_id}")
def pvr_file_by_drive_id(
    drive_file_id: str,
    download: bool = Query(False),
    inline: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Streams PDF directly by Google Drive fileId via Google Apps Script Web App.
    Supports inline browser preview and direct download (?download=true).
    """
    require_drive()
    pvr = db.query(PVRUpload).filter(PVRUpload.drive_file_id == drive_file_id).first()
    filename = pvr.file_name if pvr else f"PVR_{drive_file_id}.pdf"

    try:
        stream = gdrive_pvr.download_pvr_from_drive(drive_file_id)
    except gdrive_pvr.DriveFileNotFound:
        raise HTTPException(status_code=404, detail="The PDF is missing in Google Drive.")
    except Exception as e:
        raise drive_error(e)

    is_attachment = download or (inline == 0)
    disposition = "attachment" if is_attachment else "inline"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Content-Type": "application/pdf"
    }
    return Response(content=stream.getvalue(), media_type="application/pdf", headers=headers)


# =========================================================================
# Summary + bulk ZIP
# =========================================================================
def parse_csv(value: Optional[str]) -> List[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip() and p.strip().upper() != "ALL"]


def bulk_query(db: Session, user: User, from_date: date, to_date: date,
               circles: Optional[str], team_lead_ids: Optional[str]):
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="'To date' cannot be before 'From date'.")
    days = (to_date - from_date).days + 1
    if days > settings.PVR_ZIP_MAX_DAYS:
        raise HTTPException(status_code=400, detail=f"Date range is {days} days; the maximum is "
                                                    f"{settings.PVR_ZIP_MAX_DAYS} days per request.")
    q = apply_visibility(db.query(PVRUpload).filter(PVRUpload.pvr_date.between(from_date, to_date)), user)

    circle_list = [canon_circle(c) for c in parse_csv(circles)]
    if circle_list:
        allowed = set(authorized_circles(user))
        bad = [c for c in circle_list if c not in allowed]
        if bad:
            raise HTTPException(status_code=403, detail=f"You are not authorized for circle(s): {', '.join(bad)}")
        q = q.filter(PVRUpload.circle.in_([v for c in circle_list for v in circle_variants(c)]))

    try:
        tl_ids = [int(x) for x in parse_csv(team_lead_ids)]
    except ValueError:
        raise HTTPException(status_code=400, detail="team_lead_ids must be a comma-separated list of numbers.")
    if tl_ids:
        q = q.filter(PVRUpload.team_lead_id.in_(tl_ids))
    return q.order_by(PVRUpload.pvr_date, PVRUpload.circle, PVRUpload.tl_name)


@router.get("/summary")
def pvr_summary(
    from_date: date = Query(...), to_date: date = Query(...),
    circles: Optional[str] = Query(None), team_lead_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    rows = bulk_query(db, user, from_date, to_date, circles, team_lead_ids).all()
    return {
        "count": len(rows),
        "total_bytes": sum(r.file_size or 0 for r in rows),
        "max_files": settings.PVR_ZIP_MAX_FILES,
        "over_limit": len(rows) > settings.PVR_ZIP_MAX_FILES,
        "rows": [serialize(r, user) for r in rows[:500]],
    }


@router.get("/bulk-download")
def pvr_bulk_download(
    from_date: date = Query(...), to_date: date = Query(...),
    circles: Optional[str] = Query(None), team_lead_ids: Optional[str] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    require_drive()
    q = bulk_query(db, user, from_date, to_date, circles, team_lead_ids)
    total = q.count()
    if total == 0:
        raise HTTPException(status_code=404, detail="No PVR found for the selected filters.")
    if total > settings.PVR_ZIP_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"{total} PVRs match; the maximum is "
                                                    f"{settings.PVR_ZIP_MAX_FILES} files per ZIP. Narrow the filters.")
    rows = q.all()

    fd, zip_path = tempfile.mkstemp(prefix="pvr_zip_", suffix=".zip")
    missing, used = [], set()
    try:
        with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for r in rows:
                folder = "/".join(gdrive.pvr_folder_parts(r.pvr_date, r.tl_name or "Unknown TL"))
                arc = f"{folder}/{gdrive.sanitize(r.file_name, 200)}"
                base, n = arc[:-4], 2
                while arc in used:
                    arc, n = f"{base}_{n}.pdf", n + 1
                # Download fully first (RAM up to 8 MB, then disk) so a missing/failed file
                # never leaves an empty or partial entry inside the ZIP.
                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buf:
                    try:
                        gdrive.download_to_stream(r.drive_file_id, buf)
                    except gdrive.DriveFileNotFound:
                        missing.append(f"{arc}  (Drive file id {r.drive_file_id})")
                        continue
                    buf.seek(0)
                    with zf.open(arc, "w", force_zip64=True) as entry:
                        shutil.copyfileobj(buf, entry, 1024 * 1024)
                used.add(arc)
            if missing:
                zf.writestr("missing_files.txt",
                            "These PVRs exist in the portal but their PDF was not found in Google Drive:\r\n\r\n"
                            + "\r\n".join(missing) + "\r\n")
    except HTTPException:
        remove_quietly(zip_path)
        raise
    except Exception as e:
        remove_quietly(zip_path)
        raise drive_error(e)

    return FileResponse(
        zip_path, media_type="application/zip",
        filename=f"PVR_{from_date:%d-%m-%Y}_to_{to_date:%d-%m-%Y}.zip",
        headers={"X-PVR-Files": str(len(used)), "X-PVR-Missing": str(len(missing))},
        background=BackgroundTask(remove_quietly, zip_path),
    )


# =========================================================================
# ADMIN: edit / re-upload / delete
# =========================================================================
class PVREditRequest(BaseModel):
    pvr_date: date
    circle: str
    team_id: int
    team_lead_id: int


@router.put("/{pvr_id}")
def pvr_edit(pvr_id: int, req: PVREditRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    require_drive()
    pvr = db.get(PVRUpload, pvr_id)
    if not pvr:
        raise HTTPException(status_code=404, detail="PVR not found.")
    check_not_future(req.pvr_date)
    c = canon_circle(req.circle)
    team, tl = load_team_and_tl(db, c, req.team_id, req.team_lead_id)

    dup = find_duplicate(db, req.pvr_date, tl.id, exclude_id=pvr.id)
    if dup:
        raise HTTPException(status_code=409, detail=duplicate_detail(dup))

    before = {"pvr_date": pvr.pvr_date, "circle": pvr.circle, "team_id": pvr.team_id,
              "team_lead_id": pvr.team_lead_id, "file_name": pvr.file_name, "folder_id": pvr.drive_folder_id}
    old_folder = pvr.drive_folder_id
    old_name = pvr.file_name

    try:
        folder_id, fname = place_in_drive(req.pvr_date, c, tl)
    except Exception as e:
        raise drive_error(e)

    pvr.pvr_date, pvr.circle, pvr.team_id, pvr.team_lead_id = req.pvr_date, c, team.id, tl.id
    pvr.team_name, pvr.tl_name, pvr.file_name, pvr.drive_folder_id = team.name, tl.name, fname, folder_id
    pvr.updated_by, pvr.updated_at = user_fk(admin), datetime.utcnow()
    try:
        db.flush()                                   # unique check before touching Drive
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Another PVR already exists for that team leader and date.")

    try:
        gdrive.move_and_rename(pvr.drive_file_id, folder_id, fname)
    except Exception as e:
        db.rollback()
        raise drive_error(e)

    audit(db, pvr.id, "EDIT", admin, before=before,
          after={"pvr_date": req.pvr_date, "circle": c, "team_id": team.id, "team_lead_id": tl.id,
                 "file_name": fname, "folder_id": folder_id})
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:   # put the file back where the DB still says it is
            if old_folder:
                gdrive.move_and_rename(pvr.drive_file_id, old_folder, old_name)
        except Exception:
            logger.error("Could not revert Drive move for PVR %s", pvr_id)
        raise HTTPException(status_code=500, detail="Could not save the change. Please try again.")
    db.refresh(pvr)
    return {"success": True, "pvr": serialize(pvr, admin)}


@router.post("/{pvr_id}/reupload")
def pvr_reupload(pvr_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    require_drive()
    pvr = db.get(PVRUpload, pvr_id)
    if not pvr:
        raise HTTPException(status_code=404, detail="PVR not found.")
    tl = db.get(TeamLead, pvr.team_lead_id)

    tmp_path = None
    try:
        tmp_path, size = save_upload_to_temp(file)
        pages = count_pages(tmp_path)
        with open(tmp_path, "rb") as f:
            file_bytes = f.read()

        pvr_date_str = pvr.pvr_date.strftime("%Y-%m-%d")
        fname = gdrive.pvr_file_name(pvr.pvr_date, pvr.circle, tl.tl_code, tl.name)
        folder_id = "/".join(gdrive.pvr_folder_parts(pvr.pvr_date, tl.name))

        try:
            new_id = gdrive_pvr.upload_pvr_to_drive(
                file_bytes=file_bytes,
                filename=fname,
                pvr_date_str=pvr_date_str,
                team_leader=tl.name
            )
        except Exception as e:
            raise drive_error(e)

        old_id = pvr.drive_file_id
        pvr.drive_file_id, pvr.drive_folder_id, pvr.file_name = new_id, folder_id, fname
        pvr.file_size, pvr.page_count = size, pages
        pvr.updated_by, pvr.updated_at = user_fk(admin), datetime.utcnow()
        audit(db, pvr.id, "REUPLOAD", admin, old_drive_file_id=old_id, new_drive_file_id=new_id,
              size=size, original_name=file.filename)
        try:
            db.commit()
        except Exception:
            db.rollback()
            gdrive_pvr.delete_pvr_from_drive(new_id)
            raise HTTPException(status_code=500, detail="Could not save the new file. The old PDF is unchanged.")

        try:
            gdrive_pvr.delete_pvr_from_drive(old_id)
        except Exception:
            logger.warning("Re-upload saved but old Drive file %s could not be deleted", old_id)
        db.refresh(pvr)
        return {"success": True, "pvr": serialize(pvr, admin)}
    finally:
        remove_quietly(tmp_path)


@router.delete("/{pvr_id}")
def pvr_delete(pvr_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    require_drive()
    pvr = db.get(PVRUpload, pvr_id)
    if not pvr:
        raise HTTPException(status_code=404, detail="PVR not found.")
    try:
        gdrive_pvr.delete_pvr_from_drive(pvr.drive_file_id)
    except Exception as e:
        logger.warning("Could not delete file %s via Apps Script: %s", pvr.drive_file_id, e)
    audit(db, pvr.id, "DELETE", admin, drive_file_id=pvr.drive_file_id, pvr_date=pvr.pvr_date,
          circle=pvr.circle, team_name=pvr.team_name, tl_name=pvr.tl_name, file_name=pvr.file_name)
    db.delete(pvr)
    db.commit()
    return {"success": True, "message": "PVR deleted. The PDF was removed from Google Drive."}

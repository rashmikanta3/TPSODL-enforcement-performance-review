"""
PVR (Physical Verification Report) module: upload / view / download.

Upload flow: the request only validates, streams the PDF into the spool directory and
inserts the row as PENDING, then returns. services/pvr_worker.py compresses it and
stores it in Google Drive (services/drive_store.py) in the background. Until then,
view/download serve the spool copy.

Endpoints are plain `def`: FastAPI runs them in the threadpool, so blocking Drive and
DB calls never block the event loop.

Auth: every endpoint requires a real JWT session (access_token cookie or Bearer);
the spoofable x-user-* headers are NOT accepted here.
"""
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from auth import get_current_user_optional, verify_team_permission, verify_write_permission
from config import settings
from database import get_db
from models import (DailyTeamOperation, PVRAuditLog, PVRUpload, Team, TeamLead, User,
                    get_assigned_circles, is_circle_authorized)
from services import drive_store, pvr_worker
from services.pvr_worker import FAILED, PENDING, UPLOADED, pvr_lock, remove_quietly, spool_path

logger = logging.getLogger(__name__)
router = APIRouter()

IST = pytz.timezone("Asia/Kolkata")
CITY_SYNONYMS = {"CITY", "BERHAMPUR CITY"}
NOT_CONFIGURED_MSG = ("Google Drive not configured. Set GOOGLE_APPS_SCRIPT_URL and "
                      "GOOGLE_APPS_SCRIPT_SECRET in .env.")
ZIP_WORKERS = 4


class RequestStartMiddleware:
    """Pure ASGI middleware: stamps the request start so upload logs can show receive time."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["t0"] = time.perf_counter()
        await self.app(scope, receive, send)


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
    if not drive_store.is_configured():
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


def save_upload_to_spool(file: UploadFile) -> tuple[str, int]:
    """Stream the upload into the spool dir (size-capped), validate %PDF magic. Returns (path, size)."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    max_bytes = settings.PVR_MAX_UPLOAD_MB * 1024 * 1024
    path = pvr_worker.new_incoming_path()
    size = 0
    try:
        with open(path, "wb") as out:
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


def drive_error(e: Exception) -> HTTPException:
    if isinstance(e, drive_store.DriveNotConfigured):
        return HTTPException(status_code=503, detail=NOT_CONFIGURED_MSG)
    if isinstance(e, drive_store.DriveFileNotFound):
        return HTTPException(status_code=404, detail="The PDF is missing in Google Drive.")
    logger.error("Google Drive error: %s", e)
    return HTTPException(status_code=502, detail=f"Google Drive error: {e}")


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
        "original_size": p.original_size,
        "page_count": p.page_count,
        "storage_status": p.storage_status,
        "storage_error": p.storage_error if user.role == "ADMIN" else None,
        "uploaded_by": p.uploader.username if p.uploader else None,
        "uploaded_at": p.uploaded_at.isoformat() + "Z" if p.uploaded_at else None,
        "updated_by": p.updater.username if p.updater else None,
        "updated_at": p.updated_at.isoformat() + "Z" if p.updated_at else None,
        "can_view": can_see(user, p),
    }


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


def local_copy(pvr: PVRUpload) -> Optional[str]:
    """Spool file to serve while the PVR is not (yet) in Drive."""
    if pvr.storage_status != UPLOADED or not pvr.drive_file_id:
        path = spool_path(pvr.id)
        if os.path.exists(path):
            return path
    return None


# =========================================================================
# Status + options
# =========================================================================
@router.get("/status")
def pvr_status(user: User = Depends(require_user)):
    return {
        "drive_configured": drive_store.is_configured(),
        "message": None if drive_store.is_configured() else NOT_CONFIGURED_MSG,
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
# Upload (returns as soon as the file is in the spool)
# =========================================================================
@router.post("/upload")
def pvr_upload(
    request: Request,
    pvr_date: date = Form(..., alias="date"),
    circle: str = Form(...),
    team_id: int = Form(...),
    team_lead_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    t_start = time.perf_counter()
    t_receive = t_start - request.state.t0 if hasattr(request.state, "t0") else -1
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
    t_validate = time.perf_counter() - t_start

    t1 = time.perf_counter()
    incoming, size = save_upload_to_spool(file)
    t_spool = time.perf_counter() - t1

    t2 = time.perf_counter()
    try:
        fname = drive_store.pvr_file_name(pvr_date, c, tl.tl_code, tl.name)
        pvr = PVRUpload(
            pvr_date=pvr_date, circle=c, team_id=team.id, team_lead_id=tl.id,
            team_name=team.name, tl_name=tl.name, file_name=fname, file_size=size, original_size=size,
            storage_status=PENDING, attempts=0, uploaded_by=user_fk(user),
        )
        db.add(pvr)
        try:
            db.flush()                         # unique (date, TL) is the final race guard
        except IntegrityError:
            db.rollback()
            dup = find_duplicate(db, pvr_date, tl.id)
            raise HTTPException(status_code=409, detail=duplicate_detail(dup) if dup else
                                "A PVR for this team leader and date was just uploaded by someone else.")
        os.replace(incoming, spool_path(pvr.id))
        incoming = None
        audit(db, pvr.id, "UPLOAD", user, file_name=fname, size=size, original_name=file.filename)
        try:
            db.commit()
        except Exception:
            db.rollback()
            remove_quietly(spool_path(pvr.id))
            raise
    finally:
        remove_quietly(incoming)
    t_db = time.perf_counter() - t2

    pvr_worker.enqueue(pvr.id)
    db.refresh(pvr)
    logger.info("PVR %s upload request: receive=%.2fs validate=%.3fs spool=%.3fs db=%.3fs size=%d "
                "(Drive upload continues in background)", pvr.id, t_receive, t_validate, t_spool, t_db, size)
    return {"success": True, "pvr": serialize(pvr, user)}


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

    # Submission tracker (who was expected to upload) - Admin / Sub-Admin only
    tracker = build_tracker(db, date_, circles, team_lead_id) if user.role in ("ADMIN", "SUB_ADMIN") else None
    return {"rows": [serialize(r, user) for r in rows], "tracker": tracker}


NOT_REQUIRED_REASONS = {
    "NON_OPERATIONAL": "Team inactive / TL absent",
    "INDEPENDENT_WITHOUT_TL_COLLECTION": "Working without TL",
    "OFFICE_DUTY_NO_VEHICLE": "Office duty",
}


def build_tracker(db: Session, day: date, circles: List[str], team_lead_id: Optional[int]) -> dict:
    """
    Who had to upload a PVR on `day`, using the same DailyTeamOperation rules as Attendance:
    expected = active team, mode INDEPENDENT_WITH_TL, with an active daily TL.
    5 queries total (teams, operations, team leads, partner teams, uploaded TL ids).
    """
    variants = [v for c in circles for v in circle_variants(c)]
    teams = {t.id: t for t in db.query(Team).filter(Team.is_active == True,  # noqa: E712
                                                    Team.circle.in_(variants or ["__none__"]))}
    ops = {}
    if teams:
        for op in (db.query(DailyTeamOperation)
                   .filter(DailyTeamOperation.operation_date == day,
                           DailyTeamOperation.team_id.in_(list(teams)))
                   .order_by(DailyTeamOperation.id)):
            ops[op.team_id] = op                      # latest row per team wins

    tl_ids = {op.daily_tl_id for op in ops.values() if op.daily_tl_id}
    tl_ids |= {t.default_tl_id for t in teams.values() if t.default_tl_id}
    tls = {t.id: t for t in db.query(TeamLead).filter(TeamLead.id.in_(tl_ids))} if tl_ids else {}
    partner_ids = {op.merged_with_team_id for op in ops.values() if op.merged_with_team_id} - set(teams)
    partner_names = {t.id: t.name for t in teams.values()}
    if partner_ids:
        partner_names.update({t.id: t.name for t in db.query(Team).filter(Team.id.in_(partner_ids))})
    uploaded_ids = {i for (i,) in db.query(PVRUpload.team_lead_id).filter(PVRUpload.pvr_date == day)}

    expected: dict[int, dict] = {}                    # tl_id -> info (a TL leading 2 teams counts once)
    not_required, not_entered = [], []
    for team in sorted(teams.values(), key=lambda t: t.name):
        op = ops.get(team.id)
        circle = canon_circle(team.circle)
        if op is None:
            dtl = tls.get(team.default_tl_id)
            if team_lead_id and team.default_tl_id != team_lead_id:
                continue
            not_entered.append({"team": team.name, "default_tl": dtl.name if dtl else None, "circle": circle})
            continue

        tl = tls.get(op.daily_tl_id)
        if team_lead_id and op.daily_tl_id != team_lead_id:
            continue
        mode = op.operation_mode
        if not op.is_team_active or mode == "NON_OPERATIONAL":
            reason = NOT_REQUIRED_REASONS["NON_OPERATIONAL"]
        elif mode == "MERGED":
            reason = f"Merged with {partner_names.get(op.merged_with_team_id, 'another team')}"
        elif mode in NOT_REQUIRED_REASONS:
            reason = NOT_REQUIRED_REASONS[mode]
        elif mode == "INDEPENDENT_WITH_TL" and tl and tl.is_active:
            info = expected.setdefault(tl.id, {"tl_id": tl.id, "tl_code": tl.tl_code, "name": tl.name,
                                               "contact_no": tl.contact_no or None,
                                               "circle": canon_circle(tl.circle) or circle, "teams": []})
            info["teams"].append(team.name)
            continue
        elif mode == "INDEPENDENT_WITH_TL":
            reason = "No active TL recorded"
        else:
            reason = (mode or "Unknown").replace("_", " ").title()
        not_required.append({"tl_name": (tl.name if tl else op.tl_name) or None, "team": team.name,
                             "circle": circle, "reason": reason})

    by_circle = []
    order = {c: i for i, c in enumerate(settings.CIRCLES)}
    for c in sorted({e["circle"] for e in expected.values()}, key=lambda x: (order.get(x, 99), x)):
        members = [e for e in expected.values() if e["circle"] == c]
        pending = sorted((e for e in members if e["tl_id"] not in uploaded_ids), key=lambda e: e["name"].upper())
        by_circle.append({
            "circle": c, "expected": len(members), "uploaded": len(members) - len(pending),
            "pending": [{k: e[k] for k in ("tl_id", "tl_code", "name", "teams", "contact_no")} for e in pending],
        })

    n_expected = len(expected)
    n_uploaded = sum(1 for i in expected if i in uploaded_ids)
    return {
        "date": day.isoformat(),
        "expected": n_expected,
        "uploaded": n_uploaded,
        "pending_count": n_expected - n_uploaded,
        "percent": round(100 * n_uploaded / n_expected) if n_expected else None,
        "has_operations": bool(ops),
        "by_circle": by_circle,
        "not_required": sorted(not_required, key=lambda r: (r["circle"], r["team"])),
        "not_entered": sorted(not_entered, key=lambda r: (r["circle"], r["team"])),
    }


# =========================================================================
# Single file (inline view / attachment download)
# =========================================================================
def _disposition(kind: str, filename: str) -> str:
    safe = filename.replace('"', "")
    return f'{kind}; filename="{safe}"'


@router.get("/{pvr_id}/file")
def pvr_file(
    pvr_id: int,
    inline: int = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    pvr = get_visible_pvr(db, user, pvr_id)
    headers = {"Content-Disposition": _disposition("inline" if inline else "attachment", pvr.file_name)}

    local = local_copy(pvr)
    if local:
        try:
            fh = open(local, "rb")              # open now: the worker may delete the spool file next
        except OSError:
            db.refresh(pvr)
            local = None
        else:
            def from_spool():
                with fh:
                    while chunk := fh.read(1024 * 1024):
                        yield chunk
            headers["Content-Length"] = str(os.fstat(fh.fileno()).st_size)
            return StreamingResponse(from_spool(), media_type="application/pdf", headers=headers)

    if not pvr.drive_file_id:
        raise HTTPException(status_code=404, detail="The PDF for this PVR is not available.")
    require_drive()
    try:
        stream = drive_store.open_stream(pvr.drive_file_id)
    except Exception as e:
        raise drive_error(e)
    return StreamingResponse(stream, media_type="application/pdf", headers=headers)


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


def _fetch_to_temp(row: PVRUpload, tmp_dir: str) -> tuple[Optional[str], Optional[str]]:
    """Download one PVR (spool copy or Drive) into a temp file. Returns (path, missing_reason)."""
    local = local_copy(row)
    fd, path = tempfile.mkstemp(prefix="z_", suffix=".pdf", dir=tmp_dir)
    try:
        with os.fdopen(fd, "wb") as out:
            if local:
                with open(local, "rb") as src:
                    shutil.copyfileobj(src, out, 1024 * 1024)
            elif row.drive_file_id:
                drive_store.download_to_file(row.drive_file_id, out)
            else:
                raise drive_store.DriveFileNotFound("no stored file")
        return path, None
    except (drive_store.DriveFileNotFound, FileNotFoundError) as e:
        remove_quietly(path)
        return None, f"Drive file id {row.drive_file_id or '-'} ({e})"
    except Exception:
        remove_quietly(path)
        raise


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
    for r in rows:   # load lazy attributes before handing rows to threads
        _ = (r.drive_file_id, r.storage_status, r.file_name, r.tl_name, r.pvr_date)

    t0 = time.perf_counter()
    tmp_dir = tempfile.mkdtemp(prefix="pvr_zipparts_")
    fd, zip_path = tempfile.mkstemp(prefix="pvr_zip_", suffix=".zip")
    missing, used = [], set()
    try:
        with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_STORED, allowZip64=True) as zf, \
                ThreadPoolExecutor(max_workers=ZIP_WORKERS, thread_name_prefix="pvr-zip") as pool:
            window: deque = deque()
            it = iter(rows)

            def fill():
                while len(window) < ZIP_WORKERS * 2:
                    r = next(it, None)
                    if r is None:
                        return
                    window.append((r, pool.submit(_fetch_to_temp, r, tmp_dir)))

            fill()
            while window:                      # write in the original order
                r, fut = window.popleft()
                fill()
                folder = "/".join(drive_store.pvr_folder_parts(r.pvr_date, r.tl_name or "Unknown TL"))
                arc = f"{folder}/{drive_store.sanitize(r.file_name, 200)}"
                base, n = arc[:-4], 2
                while arc in used:
                    arc, n = f"{base}_{n}.pdf", n + 1
                path, reason = fut.result()
                if not path:
                    missing.append(f"{arc}  ({reason})")
                    continue
                zf.write(path, arc)
                remove_quietly(path)
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
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("PVR ZIP: %d files, %d missing, %.2fs", len(used), len(missing), time.perf_counter() - t0)
    return FileResponse(
        zip_path, media_type="application/zip",
        filename=f"PVR_{from_date:%d-%m-%Y}_to_{to_date:%d-%m-%Y}.zip",
        headers={"X-PVR-Files": str(len(used)), "X-PVR-Missing": str(len(missing))},
        background=BackgroundTask(remove_quietly, zip_path),
    )


# =========================================================================
# ADMIN: edit / re-upload / delete / retry
# =========================================================================
class PVREditRequest(BaseModel):
    pvr_date: date
    circle: str
    team_id: int
    team_lead_id: int


@router.put("/{pvr_id}")
def pvr_edit(pvr_id: int, req: PVREditRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    require_drive()
    check_not_future(req.pvr_date)
    c = canon_circle(req.circle)
    team, tl = load_team_and_tl(db, c, req.team_id, req.team_lead_id)

    with pvr_lock(pvr_id):
        pvr = db.get(PVRUpload, pvr_id)
        if not pvr:
            raise HTTPException(status_code=404, detail="PVR not found.")
        db.refresh(pvr)
        dup = find_duplicate(db, req.pvr_date, tl.id, exclude_id=pvr.id)
        if dup:
            raise HTTPException(status_code=409, detail=duplicate_detail(dup))

        before = {"pvr_date": pvr.pvr_date, "circle": pvr.circle, "team_id": pvr.team_id,
                  "team_lead_id": pvr.team_lead_id, "file_name": pvr.file_name, "folder_id": pvr.drive_folder_id}
        old_date, old_tl, old_name = pvr.pvr_date, pvr.tl_name, pvr.file_name
        fname = drive_store.pvr_file_name(req.pvr_date, c, tl.tl_code, tl.name)
        if pvr.drive_file_id and drive_store.direct_mode():
            try:   # resolve/cache the target folder before this transaction starts writing
                drive_store.folder_for(req.pvr_date, tl.name)
            except Exception as e:
                raise drive_error(e)

        pvr.pvr_date, pvr.circle, pvr.team_id, pvr.team_lead_id = req.pvr_date, c, team.id, tl.id
        pvr.team_name, pvr.tl_name, pvr.file_name = team.name, tl.name, fname
        pvr.updated_by, pvr.updated_at = user_fk(admin), datetime.utcnow()
        try:
            db.flush()                                   # unique check before touching Drive
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Another PVR already exists for that team leader and date.")

        moved = False
        if pvr.drive_file_id:
            # Not yet uploaded (PENDING with no Drive file) -> the worker will use the new folder/name
            try:
                folder_id = drive_store.move_pvr(pvr.drive_file_id, req.pvr_date, tl.name, fname)
                pvr.drive_folder_id = folder_id or pvr.drive_folder_id
                moved = True
            except Exception as e:
                db.rollback()
                raise drive_error(e)

        audit(db, pvr.id, "EDIT", admin, before=before,
              after={"pvr_date": req.pvr_date, "circle": c, "team_id": team.id, "team_lead_id": tl.id,
                     "file_name": fname, "folder_id": pvr.drive_folder_id, "moved_in_drive": moved})
        try:
            db.commit()
        except Exception:
            db.rollback()
            if moved:
                try:   # put the file back where the DB still says it is
                    drive_store.move_pvr(pvr.drive_file_id, old_date, old_tl, old_name)
                except Exception:
                    logger.error("Could not revert Drive move for PVR %s", pvr_id)
            raise HTTPException(status_code=500, detail="Could not save the change. Please try again.")
    db.refresh(pvr)
    return {"success": True, "pvr": serialize(pvr, admin)}


@router.post("/{pvr_id}/reupload")
def pvr_reupload(pvr_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    require_drive()
    if not db.get(PVRUpload, pvr_id):
        raise HTTPException(status_code=404, detail="PVR not found.")
    incoming, size = save_upload_to_spool(file)
    try:
        with pvr_lock(pvr_id):
            pvr = db.get(PVRUpload, pvr_id)
            if not pvr:
                raise HTTPException(status_code=404, detail="PVR not found.")
            db.refresh(pvr)
            # The current Drive file stays in drive_file_id until the new one is UPLOADED;
            # the worker trashes it then.
            os.replace(incoming, spool_path(pvr.id))
            incoming = None
            pvr.storage_status, pvr.storage_error, pvr.attempts = PENDING, None, 0
            pvr.file_size, pvr.original_size, pvr.page_count = size, size, None
            pvr.updated_by, pvr.updated_at = user_fk(admin), datetime.utcnow()
            audit(db, pvr.id, "REUPLOAD", admin, current_drive_file_id=pvr.drive_file_id, size=size,
                  original_name=file.filename)
            db.commit()
    finally:
        remove_quietly(incoming)
    pvr_worker.enqueue(pvr_id)
    db.refresh(pvr)
    return {"success": True, "pvr": serialize(pvr, admin)}


@router.post("/{pvr_id}/retry")
def pvr_retry(pvr_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    require_drive()
    with pvr_lock(pvr_id):
        pvr = db.get(PVRUpload, pvr_id)
        if not pvr:
            raise HTTPException(status_code=404, detail="PVR not found.")
        if pvr.storage_status != FAILED:
            raise HTTPException(status_code=400, detail="Only FAILED uploads can be retried.")
        if not os.path.exists(spool_path(pvr.id)):
            raise HTTPException(status_code=409, detail="The local copy of this PDF is gone. Please re-upload it.")
        pvr.storage_status, pvr.storage_error, pvr.attempts = PENDING, None, 0
        db.commit()
    pvr_worker.enqueue(pvr_id)
    db.refresh(pvr)
    return {"success": True, "pvr": serialize(pvr, admin)}


@router.delete("/{pvr_id}")
def pvr_delete(pvr_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    with pvr_lock(pvr_id):                 # waits for a running upload of this PVR to finish
        pvr = db.get(PVRUpload, pvr_id)
        if not pvr:
            raise HTTPException(status_code=404, detail="PVR not found.")
        db.refresh(pvr)
        if pvr.drive_file_id:
            require_drive()
            try:
                drive_store.trash(pvr.drive_file_id)
            except Exception as e:
                raise drive_error(e)
        audit(db, pvr.id, "DELETE", admin, drive_file_id=pvr.drive_file_id, pvr_date=pvr.pvr_date,
              circle=pvr.circle, team_name=pvr.team_name, tl_name=pvr.tl_name, file_name=pvr.file_name,
              storage_status=pvr.storage_status)
        db.delete(pvr)
        db.commit()
        remove_quietly(spool_path(pvr_id))   # cancels a PENDING job (the worker skips missing rows)
    return {"success": True, "message": "PVR deleted. The PDF was moved to Google Drive trash (recoverable for 30 days)."}

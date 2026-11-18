"""
PVR (Patrolling Verification Report) Upload & AI Quality Check Router.

Endpoints:
  GET  /team-lead      – lookup TL by code
  POST /upload         – upload PDF, trigger background AI evaluation
  GET  /list           – list PVR reports (paginated, circle-scoped)
  GET  /{id}           – get single PVR detail
  GET  /{id}/file      – stream/download PVR PDF
  POST /{id}/re-evaluate – re-trigger AI evaluation
"""
import logging
import threading
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from database import get_db, SessionLocal
from models import TeamLead, get_assigned_circles, is_circle_authorized
from auth import get_current_actor, verify_write_permission

# Lazy import of PVRReport to avoid circular import at module level
import models as _models

logger = logging.getLogger(__name__)

router = APIRouter()

# Semaphore: limit concurrent AI evaluations to 2 threads
_ai_semaphore = threading.Semaphore(2)

PVR_MAX_BYTES = (settings.PVR_MAX_UPLOAD_MB or 15) * 1024 * 1024


def _get_pvr_model():
    """Return the PVRReport model class (lazy to handle import order)."""
    return _models.PVRReport


# ─── Helpers ───────────────────────────────────────────────────────────
def _circle_filter(query, col, circles: list[str]):
    """Apply circle filter handling CITY / BERHAMPUR CITY synonyms."""
    expanded = set()
    for c in circles:
        c_up = c.strip().upper()
        expanded.add(c_up)
        if c_up in ("CITY", "BERHAMPUR CITY"):
            expanded.add("CITY")
            expanded.add("BERHAMPUR CITY")
    return query.filter(col.in_(list(expanded)))


# ─── 1. TL Lookup ─────────────────────────────────────────────────────
@router.get("/team-lead")
def lookup_team_lead(
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    if not current_user:
        raise HTTPException(401, "Authentication required")
    tl = db.query(TeamLead).filter(
        TeamLead.tl_code == code.strip().upper(),
        TeamLead.is_active == True,
    ).first()
    if not tl:
        raise HTTPException(404, f"No active Team Leader found with code: {code}")
    return {
        "id": tl.id,
        "tl_code": tl.tl_code,
        "name": tl.name,
        "designation": tl.designation,
        "circle": tl.circle,
    }


# ─── 2. Upload PVR ────────────────────────────────────────────────────
@router.post("/upload")
async def upload_pvr(
    background_tasks: BackgroundTasks,
    tl_code: str = Form(...),
    report_date: str = Form(...),
    circle: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    # Auth
    verify_write_permission(current_user, circle)

    # Validate TL exists
    tl = db.query(TeamLead).filter(
        TeamLead.tl_code == tl_code.strip().upper(),
        TeamLead.is_active == True,
    ).first()
    if not tl:
        raise HTTPException(400, f"Team Leader not found: {tl_code}")

    # Circle authorisation (both the submitted circle and the TL's own circle)
    if not is_circle_authorized(current_user, circle):
        raise HTTPException(403, f"Not authorized for circle: {circle}")
    if not is_circle_authorized(current_user, tl.circle):
        raise HTTPException(403, f"Team Leader {tl.tl_code} belongs to circle {tl.circle}, which you are not authorized for")

    # Read and validate PDF (read at most limit+1 bytes so oversized uploads are not buffered whole)
    pdf_bytes = await file.read(PVR_MAX_BYTES + 1)
    if not pdf_bytes:
        raise HTTPException(400, "Uploaded file is empty")
    if len(pdf_bytes) > PVR_MAX_BYTES:
        raise HTTPException(
            400,
            f"File exceeds max size ({settings.PVR_MAX_UPLOAD_MB or 15} MB)"
        )
    if not pdf_bytes[:5].startswith(b"%PDF"):
        raise HTTPException(400, "File does not appear to be a valid PDF")

    # Parse report_date
    try:
        r_date = date.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(400, "Invalid report_date format. Use YYYY-MM-DD.")

    PVRReport = _get_pvr_model()

    # Build R2 key
    from r2_storage import build_pvr_key, upload_pdf, R2NotConfigured
    r2_key = build_pvr_key(tl.name, tl.tl_code, str(r_date))

    # Upload to R2
    try:
        upload_pdf(r2_key, pdf_bytes)
    except R2NotConfigured as exc:
        raise HTTPException(503, f"Cloud storage not configured: {exc}")
    except Exception as exc:
        logger.error("R2 upload failed: %s", exc)
        raise HTTPException(502, "Failed to upload PDF to cloud storage")

    # Upsert record (unique on tl_code + report_date)
    existing = db.query(PVRReport).filter(
        PVRReport.tl_code == tl.tl_code,
        PVRReport.report_date == r_date,
    ).first()

    now_utc = datetime.now(timezone.utc)

    if existing:
        existing.tl_name = tl.name
        existing.circle = circle.strip().upper()
        existing.r2_key = r2_key
        existing.file_size_bytes = len(pdf_bytes)
        existing.uploaded_by = current_user.username
        existing.uploaded_at = now_utc
        existing.ai_status = "PENDING"
        existing.ai_score = None
        existing.ai_verdict = None
        existing.ai_summary = None
        existing.ai_findings_json = None
        existing.ai_evaluated_at = None
        record = existing
    else:
        record = PVRReport(
            tl_code=tl.tl_code,
            tl_name=tl.name,
            circle=circle.strip().upper(),
            report_date=r_date,
            r2_key=r2_key,
            file_size_bytes=len(pdf_bytes),
            uploaded_by=current_user.username,
            uploaded_at=now_utc,
            ai_status="PENDING",
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    record_id = record.id

    # Schedule background AI evaluation
    background_tasks.add_task(run_pvr_evaluation, record_id, pdf_bytes)

    return {
        "id": record_id,
        "message": "PVR uploaded successfully. AI evaluation started.",
        "ai_status": "PENDING",
    }


# ─── 3. List PVRs ─────────────────────────────────────────────────────
@router.get("/list")
def list_pvrs(
    circle: Optional[str] = Query(None),
    tl_code: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    if not current_user:
        raise HTTPException(401, "Authentication required")

    PVRReport = _get_pvr_model()
    q = db.query(PVRReport)

    # Circle scoping
    if current_user.role == "ADMIN":
        if circle:
            q = _circle_filter(q, PVRReport.circle, [circle])
    else:
        allowed = get_assigned_circles(current_user)
        if not allowed:
            return {"items": [], "total": 0, "page": page, "limit": limit}
        if circle and is_circle_authorized(current_user, circle):
            q = _circle_filter(q, PVRReport.circle, [circle])
        else:
            q = _circle_filter(q, PVRReport.circle, allowed)

    if tl_code:
        q = q.filter(PVRReport.tl_code == tl_code.strip().upper())

    if from_date:
        try:
            q = q.filter(PVRReport.report_date >= date.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            q = q.filter(PVRReport.report_date <= date.fromisoformat(to_date))
        except ValueError:
            pass

    total = q.count()
    offset = (page - 1) * limit
    rows = q.order_by(desc(PVRReport.report_date), desc(PVRReport.id)).offset(offset).limit(limit).all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "tl_code": r.tl_code,
            "tl_name": r.tl_name,
            "circle": r.circle,
            "report_date": str(r.report_date),
            "ai_status": r.ai_status,
            "ai_score": r.ai_score,
            "ai_verdict": r.ai_verdict,
            "ai_summary": r.ai_summary,
            "uploaded_by": r.uploaded_by,
            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
        })

    return {"items": items, "total": total, "page": page, "limit": limit}


# ─── 4. Get PVR Detail ────────────────────────────────────────────────
@router.get("/{pvr_id}")
def get_pvr(
    pvr_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    if not current_user:
        raise HTTPException(401, "Authentication required")

    PVRReport = _get_pvr_model()
    record = db.query(PVRReport).filter(PVRReport.id == pvr_id).first()
    if not record:
        raise HTTPException(404, "PVR report not found")

    if current_user.role != "ADMIN" and not is_circle_authorized(current_user, record.circle):
        raise HTTPException(403, "Not authorized for this circle")

    findings = None
    if record.ai_findings_json:
        try:
            findings = __import__("json").loads(record.ai_findings_json)
        except Exception:
            findings = record.ai_findings_json

    return {
        "id": record.id,
        "tl_code": record.tl_code,
        "tl_name": record.tl_name,
        "circle": record.circle,
        "report_date": str(record.report_date),
        "r2_key": record.r2_key,
        "file_size_bytes": record.file_size_bytes,
        "uploaded_by": record.uploaded_by,
        "uploaded_at": record.uploaded_at.isoformat() if record.uploaded_at else None,
        "ai_status": record.ai_status,
        "ai_score": record.ai_score,
        "ai_verdict": record.ai_verdict,
        "ai_summary": record.ai_summary,
        "ai_findings": findings,
        "ai_evaluated_at": record.ai_evaluated_at.isoformat() if record.ai_evaluated_at else None,
    }


# ─── 5. Download PVR File ─────────────────────────────────────────────
@router.get("/{pvr_id}/file")
def download_pvr_file(
    pvr_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    if not current_user:
        raise HTTPException(401, "Authentication required")

    PVRReport = _get_pvr_model()
    record = db.query(PVRReport).filter(PVRReport.id == pvr_id).first()
    if not record:
        raise HTTPException(404, "PVR report not found")

    if current_user.role != "ADMIN" and not is_circle_authorized(current_user, record.circle):
        raise HTTPException(403, "Not authorized for this circle")

    from r2_storage import download_pdf, R2NotConfigured
    try:
        pdf_bytes = download_pdf(record.r2_key)
    except R2NotConfigured as exc:
        raise HTTPException(503, f"Cloud storage not configured: {exc}")
    except Exception as exc:
        logger.error("R2 download failed: %s", exc)
        raise HTTPException(502, "Failed to retrieve PDF from cloud storage")

    import io
    filename = f"PVR_{record.tl_code}_{record.report_date}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ─── 6. Re-evaluate PVR ───────────────────────────────────────────────
@router.post("/{pvr_id}/re-evaluate")
def re_evaluate_pvr(
    pvr_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_actor),
):
    verify_write_permission(current_user)

    PVRReport = _get_pvr_model()
    record = db.query(PVRReport).filter(PVRReport.id == pvr_id).first()
    if not record:
        raise HTTPException(404, "PVR report not found")

    if current_user.role != "ADMIN" and not is_circle_authorized(current_user, record.circle):
        raise HTTPException(403, "Not authorized for this circle")

    if record.ai_status == "PROCESSING":
        raise HTTPException(409, "AI evaluation is already in progress")

    # Download PDF from R2 for re-evaluation
    from r2_storage import download_pdf, R2NotConfigured
    try:
        pdf_bytes = download_pdf(record.r2_key)
    except R2NotConfigured as exc:
        raise HTTPException(503, f"Cloud storage not configured: {exc}")
    except Exception as exc:
        logger.error("R2 download failed for re-eval: %s", exc)
        raise HTTPException(502, "Failed to retrieve PDF from cloud storage")

    record.ai_status = "PENDING"
    record.ai_score = None
    record.ai_verdict = None
    record.ai_summary = None
    record.ai_findings_json = None
    record.ai_evaluated_at = None
    db.commit()

    background_tasks.add_task(run_pvr_evaluation, pvr_id, pdf_bytes)

    return {"id": pvr_id, "message": "Re-evaluation started.", "ai_status": "PENDING"}


# ─── Background AI Evaluation ─────────────────────────────────────────
def run_pvr_evaluation(record_id: int, pdf_bytes: bytes):
    """
    Background task: evaluate PVR with Gemini AI.
    Uses its own DB session. Semaphore limits concurrency to 2.
    """
    import json as _json
    from pvr_ai import evaluate_pvr, GeminiError

    PVRReport = _get_pvr_model()

    db = SessionLocal()
    try:
        record = db.query(PVRReport).filter(PVRReport.id == record_id).first()
        if not record:
            logger.error("PVR record %d not found for AI evaluation", record_id)
            return

        record.ai_status = "PROCESSING"
        db.commit()

        acquired = _ai_semaphore.acquire(timeout=120)
        if not acquired:
            record.ai_status = "FAILED"
            record.ai_summary = "AI evaluation timed out waiting for available slot."
            db.commit()
            return

        try:
            result = evaluate_pvr(pdf_bytes)

            record.ai_score = result.get("score")
            record.ai_verdict = result.get("verdict", "UNKNOWN")
            record.ai_summary = result.get("summary", "")
            record.ai_findings_json = _json.dumps(result)
            record.ai_status = "DONE"
            record.ai_evaluated_at = datetime.now(timezone.utc)

        except GeminiError as exc:
            logger.error("AI evaluation failed for PVR %d: %s", record_id, exc)
            record.ai_status = "FAILED"
            record.ai_summary = f"AI evaluation error: {str(exc)[:500]}"

        except Exception as exc:
            logger.error("Unexpected error in AI evaluation for PVR %d: %s", record_id, exc)
            record.ai_status = "FAILED"
            record.ai_summary = f"Unexpected error: {str(exc)[:500]}"

        finally:
            _ai_semaphore.release()

        db.commit()

    except Exception as exc:
        logger.error("DB error in PVR evaluation for %d: %s", record_id, exc)
    finally:
        db.close()

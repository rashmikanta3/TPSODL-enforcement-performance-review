"""
Background pipeline for PVR uploads.

The upload request only streams the PDF into PVR_SPOOL_DIR (a Docker volume) and inserts
the pvr_uploads row with storage_status=PENDING. This single worker thread then
compresses the PDF, uploads it to Google Drive, marks the row UPLOADED and deletes the
spool file. Until then, view/download are served from the spool file.

* Restart-safe: on startup every PENDING row whose spool file exists is queued again.
* 3 attempts with backoff, then FAILED (spool file kept; ADMIN can Retry).
* pvr_lock(id) serializes the worker with ADMIN edit / re-upload / delete of that PVR.
Requires a single app process (uvicorn --workers 1).
"""
import logging
import os
import queue
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import inspect, text

from config import settings
from database import SessionLocal, engine
from services import drive_store, pdf_compress

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_DELAYS = [10, 60]            # seconds before attempt 2 and 3

PENDING, UPLOADED, FAILED = "PENDING", "UPLOADED", "FAILED"


# ---------------------------------------------------------------------------
# Spool files
# ---------------------------------------------------------------------------
def spool_dir() -> str:
    d = os.path.abspath(settings.PVR_SPOOL_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def spool_path(pvr_id: int) -> str:
    return os.path.join(spool_dir(), f"{pvr_id}.pdf")


def new_incoming_path() -> str:
    return os.path.join(spool_dir(), f"incoming_{uuid.uuid4().hex}.part")


def remove_quietly(path: Optional[str]):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


def _signature(path: str):
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


# ---------------------------------------------------------------------------
# Per-PVR locks
# ---------------------------------------------------------------------------
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def pvr_lock(pvr_id: int):
    with _locks_guard:
        lock = _locks.setdefault(pvr_id, threading.Lock())
    with lock:
        yield


# ---------------------------------------------------------------------------
# Schema: columns added after pvr_uploads was first created (create_all won't add them)
# ---------------------------------------------------------------------------
NEW_COLUMNS = {
    # existing rows were uploaded synchronously -> UPLOADED
    "storage_status": "VARCHAR(10) NOT NULL DEFAULT 'UPLOADED'",
    "storage_error": "TEXT",
    "original_size": "INTEGER",
    "attempts": "INTEGER NOT NULL DEFAULT 0",
}


def ensure_schema():
    insp = inspect(engine)
    if not insp.has_table("pvr_uploads"):
        return
    cols = {c["name"]: c for c in insp.get_columns("pvr_uploads")}
    is_pg = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        for name, ddl in NEW_COLUMNS.items():
            if is_pg:
                conn.execute(text(f"ALTER TABLE pvr_uploads ADD COLUMN IF NOT EXISTS {name} {ddl}"))
            elif name not in cols:
                conn.execute(text(f"ALTER TABLE pvr_uploads ADD COLUMN {name} {ddl}"))
        if is_pg:
            conn.execute(text("ALTER TABLE pvr_uploads ALTER COLUMN drive_file_id DROP NOT NULL"))
        elif not cols["drive_file_id"]["nullable"]:
            _sqlite_rebuild_nullable(conn)


def _sqlite_rebuild_nullable(conn):
    """SQLite cannot DROP NOT NULL: rebuild pvr_uploads with the current model (keeps all rows)."""
    from models import PVRUpload
    logger.info("Rebuilding SQLite pvr_uploads so drive_file_id can be NULL")
    old_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(pvr_uploads)"))]
    for (idx,) in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pvr_uploads' "
            "AND name NOT LIKE 'sqlite_autoindex%'")).fetchall():
        conn.execute(text(f'DROP INDEX "{idx}"'))
    conn.execute(text("ALTER TABLE pvr_uploads RENAME TO pvr_uploads_old"))
    PVRUpload.__table__.create(conn)
    keep = ", ".join(c for c in old_cols if c in PVRUpload.__table__.c)
    conn.execute(text(f"INSERT INTO pvr_uploads ({keep}) SELECT {keep} FROM pvr_uploads_old"))
    conn.execute(text("DROP TABLE pvr_uploads_old"))


# ---------------------------------------------------------------------------
# Queue + worker thread
# ---------------------------------------------------------------------------
_queue: "queue.Queue[int]" = queue.Queue()
_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def enqueue(pvr_id: int, delay: float = 0):
    if delay > 0:
        t = threading.Timer(delay, _queue.put, args=[pvr_id])
        t.daemon = True
        t.start()
    else:
        _queue.put(pvr_id)


def _loop():
    logger.info("PVR storage worker started (spool: %s)", spool_dir())
    while not _stop.is_set():
        try:
            pvr_id = _queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            process(pvr_id)
        except Exception:
            logger.exception("PVR worker crashed on id %s (continuing)", pvr_id)
        finally:
            _queue.task_done()


def start():
    global _thread
    ensure_schema()
    _requeue_on_startup()
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="pvr-storage-worker", daemon=True)
        _thread.start()


def stop(timeout: float = 5):
    _stop.set()
    if _thread:
        _thread.join(timeout)


def wait_idle(timeout: float = 60) -> bool:
    """Test helper: wait until the queue is drained."""
    end = time.time() + timeout
    while time.time() < end:
        if _queue.unfinished_tasks == 0:
            return True
        time.sleep(0.05)
    return False


def _requeue_on_startup():
    from models import PVRUpload
    db = SessionLocal()
    try:
        queued = 0
        for row in db.query(PVRUpload).filter(PVRUpload.storage_status == PENDING).order_by(PVRUpload.id):
            if os.path.exists(spool_path(row.id)):
                enqueue(row.id)
                queued += 1
            else:
                row.storage_status, row.storage_error = FAILED, "Spool file missing after restart; re-upload needed."
        db.commit()
        if queued:
            logger.info("PVR worker: re-queued %d pending upload(s)", queued)

        # drop spool files nobody needs any more
        keep = {r.id for r in db.query(PVRUpload.id).filter(PVRUpload.storage_status != UPLOADED)}
        cutoff = time.time() - 3600
        for name in os.listdir(spool_dir()):
            path = os.path.join(spool_dir(), name)
            if name.endswith(".pdf") and name[:-4].isdigit() and int(name[:-4]) not in keep:
                remove_quietly(path)
            elif name.startswith(("incoming_", "pvrc_")) and os.path.getmtime(path) < cutoff:
                remove_quietly(path)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# One job
# ---------------------------------------------------------------------------
def _fail_or_retry(db, row, err: str):
    row.attempts = (row.attempts or 0) + 1
    row.storage_error = err[:2000]
    if row.attempts >= MAX_ATTEMPTS:
        row.storage_status = FAILED
        logger.error("PVR %s: Drive upload FAILED after %d attempts: %s", row.id, row.attempts, err)
    db.commit()
    if row.storage_status == PENDING:
        delay = RETRY_DELAYS[min(row.attempts - 1, len(RETRY_DELAYS) - 1)]
        logger.warning("PVR %s: attempt %d failed (%s); retrying in %ss", row.id, row.attempts, err, delay)
        enqueue(row.id, delay)


def process(pvr_id: int):
    from models import PVRUpload
    spool = spool_path(pvr_id)

    db = SessionLocal()
    try:
        row = db.get(PVRUpload, pvr_id)
        if not row or row.storage_status != PENDING:
            return                      # deleted, already done, or FAILED (needs Retry)
        if not os.path.exists(spool):
            row.storage_status, row.storage_error = FAILED, "Spool file missing."
            db.commit()
            return
        sig = _signature(spool)
    finally:
        db.close()

    # Compression runs without the lock so admin actions are not blocked by Ghostscript
    t0 = time.perf_counter()
    comp = pdf_compress.compress(spool, work_dir=spool_dir())
    t_compress = time.perf_counter() - t0

    with pvr_lock(pvr_id):
        db = SessionLocal()
        try:
            row = db.get(PVRUpload, pvr_id)
            if (not row or row.storage_status != PENDING or not os.path.exists(spool)
                    or _signature(spool) != sig):
                return                  # deleted / re-uploaded meanwhile: a newer job handles it

            t1 = time.perf_counter()
            try:
                file_id, folder_id = drive_store.upload_pvr(comp.path, row.file_name, row.pvr_date, row.tl_name)
            except Exception as e:
                _fail_or_retry(db, row, f"{type(e).__name__}: {e}")
                return
            t_drive = time.perf_counter() - t1

            old_id = row.drive_file_id
            row.drive_file_id = file_id
            row.drive_folder_id = folder_id or row.drive_folder_id
            row.original_size = comp.original_size
            row.file_size = comp.final_size
            row.page_count = comp.page_count or row.page_count
            row.storage_status, row.storage_error = UPLOADED, None
            t2 = time.perf_counter()
            try:
                db.commit()
            except Exception:
                db.rollback()
                drive_store.trash(file_id)     # don't leave an orphan in Drive
                raise
            t_db = time.perf_counter() - t2
            remove_quietly(spool)
            logger.info("PVR %s stored: compress=%.2fs (%s) drive=%.2fs db=%.3fs size %d->%d",
                        pvr_id, t_compress, comp.note or comp.mode, t_drive, t_db,
                        comp.original_size, comp.final_size)

            if old_id and old_id != file_id:   # re-upload: old file only now goes to trash
                try:
                    drive_store.trash(old_id)
                except Exception as e:
                    logger.warning("PVR %s: could not trash replaced Drive file %s: %s", pvr_id, old_id, e)
        finally:
            db.close()
            if comp.used:
                remove_quietly(comp.path)

"""
Safe PDF compression for PVRs (legal documents).

Modes (settings.PVR_COMPRESS_MODE):
  off       -> file is uploaded byte-for-byte as received
  lossless  -> pikepdf re-pack (stream compression, object streams). No pixel changes.
  balanced  -> Ghostscript /printer with conservative image settings, then lossless pass.
               Only images much larger than PVR_COMPRESS_DPI are downsampled; B/W scans
               stay at 300 dpi; JPEG quality PVR_JPEG_QUALITY.

Safety: the result is used only if it opens with pikepdf, has the same page count and is
at least 10% smaller. Any error -> original file. Compression never fails an upload.
"""
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Optional

import pikepdf

from config import settings

logger = logging.getLogger(__name__)

MIN_SAVING = 0.10
GS_TIMEOUT = 120
_gs_slot = threading.Semaphore(1)       # one Ghostscript process at a time


@dataclass
class CompressResult:
    path: str                  # file to upload (original path if not compressed)
    original_size: int
    final_size: int
    page_count: Optional[int]
    mode: str
    used: bool                 # True if a compressed file replaced the original
    note: str = ""


def page_count(path: str) -> Optional[int]:
    try:
        with pikepdf.open(path) as pdf:
            return len(pdf.pages)
    except Exception as e:
        logger.warning("Could not open PDF %s: %s", path, e)
        return None


def ghostscript_bin() -> Optional[str]:
    return shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")


def _qfactor(quality: int) -> float:
    """Map JPEG quality 1-100 to Ghostscript QFactor (85 -> 0.30; lower = better)."""
    q = max(1, min(100, int(quality)))
    return round((200 - 2 * q) / 100 if q >= 50 else 5000 / q / 100, 2)


def _lossless(src: str, dst: str):
    with pikepdf.open(src) as pdf:
        pdf.save(dst, compress_streams=True, recompress_flate=True,
                 object_stream_mode=pikepdf.ObjectStreamMode.generate)


def _ghostscript(src: str, dst: str, dpi: int, quality: int):
    gs = ghostscript_bin()
    if not gs:
        raise RuntimeError("Ghostscript (gs) is not installed")
    qf = _qfactor(quality)
    acs = f"<< /QFactor {qf} /Blend 1 /HSamples [1 1 1 1] /VSamples [1 1 1 1] >>"
    cmd = [
        gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.6", "-dPDFSETTINGS=/printer",
        "-dDetectDuplicateImages=true", "-dCompressFonts=true",
        "-dDownsampleColorImages=true", f"-dColorImageResolution={dpi}",
        "-dColorImageDownsampleThreshold=1.5", "-dColorImageDownsampleType=/Bicubic",
        "-dDownsampleGrayImages=true", f"-dGrayImageResolution={dpi}",
        "-dGrayImageDownsampleThreshold=1.5", "-dGrayImageDownsampleType=/Bicubic",
        "-dDownsampleMonoImages=true", "-dMonoImageResolution=300",
        "-dMonoImageDownsampleThreshold=1.5",
        f"-sOutputFile={dst}",
        "-c", f"<< /ColorACSImageDict {acs} /GrayACSImageDict {acs} >> setdistillerparams",
        "-f", src,
    ]
    if os.name != "nt" and shutil.which("nice"):
        cmd = ["nice", "-n", "10"] + cmd
    with _gs_slot:
        res = subprocess.run(cmd, capture_output=True, timeout=GS_TIMEOUT)
    if res.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"Ghostscript exit {res.returncode}: {res.stderr.decode(errors='ignore')[:300]}")


def compress(src: str, mode: Optional[str] = None, work_dir: Optional[str] = None) -> CompressResult:
    """Return the file to upload. The caller deletes result.path if result.used is True."""
    mode = (mode or settings.PVR_COMPRESS_MODE or "off").strip().lower()
    orig_size = os.path.getsize(src)
    orig_pages = page_count(src)
    keep_original = CompressResult(src, orig_size, orig_size, orig_pages, mode, False)
    if mode not in ("lossless", "balanced"):
        keep_original.note = "compression off"
        return keep_original
    if orig_pages is None:
        keep_original.note = "original PDF could not be parsed; uploaded as-is"
        return keep_original

    work = tempfile.mkdtemp(prefix="pvrc_", dir=work_dir)
    out = os.path.join(work, "out.pdf")
    t0 = time.perf_counter()
    try:
        stage_in = src
        if mode == "balanced":
            gs_out = os.path.join(work, "gs.pdf")
            try:
                _ghostscript(src, gs_out, settings.PVR_COMPRESS_DPI, settings.PVR_JPEG_QUALITY)
                stage_in = gs_out
            except Exception as e:
                logger.warning("Ghostscript step skipped (%s); doing lossless only", e)
        _lossless(stage_in, out)

        new_size = os.path.getsize(out)
        new_pages = page_count(out)
        if new_pages != orig_pages:
            keep_original.note = f"rejected: page count {new_pages} != {orig_pages}"
        elif new_size > orig_size * (1 - MIN_SAVING):
            keep_original.note = f"rejected: only {100 - new_size * 100 // max(orig_size, 1)}% smaller"
        else:
            final = os.path.join(tempfile.gettempdir() if work_dir is None else work_dir,
                                 f"pvrc_{os.getpid()}_{threading.get_ident()}_{time.time_ns()}.pdf")
            shutil.move(out, final)
            logger.info("PVR compress %s: %d -> %d bytes (%.0f%%) in %.1fs", mode, orig_size, new_size,
                        100 * new_size / orig_size, time.perf_counter() - t0)
            return CompressResult(final, orig_size, new_size, new_pages, mode, True,
                                  f"{orig_size} -> {new_size} bytes")
        logger.info("PVR compress %s: kept original (%s)", mode, keep_original.note)
        return keep_original
    except Exception as e:
        logger.warning("PVR compression failed, uploading original: %s", e)
        keep_original.note = f"compression error: {e}"
        return keep_original
    finally:
        shutil.rmtree(work, ignore_errors=True)

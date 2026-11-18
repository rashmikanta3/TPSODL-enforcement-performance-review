"""
Cloudflare R2 Object Storage helpers for PVR PDF uploads.

Uses boto3 S3-compatible client targeting R2.
All functions are synchronous (called from background threads).
"""
import re
import io
import logging
from functools import lru_cache
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)


class R2NotConfigured(Exception):
    """Raised when R2 credentials / bucket are not set."""


def _require_r2_config():
    missing = []
    if not settings.R2_ACCOUNT_ID:
        missing.append("R2_ACCOUNT_ID")
    if not settings.R2_ACCESS_KEY_ID:
        missing.append("R2_ACCESS_KEY_ID")
    if not settings.R2_SECRET_ACCESS_KEY:
        missing.append("R2_SECRET_ACCESS_KEY")
    if not settings.R2_BUCKET:
        missing.append("R2_BUCKET")
    if missing:
        raise R2NotConfigured(f"Missing R2 config: {', '.join(missing)}")


@lru_cache(maxsize=1)
def _get_s3_client():
    """Lazy singleton boto3 S3 client pointing at Cloudflare R2."""
    _require_r2_config()
    endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _sanitize(text: str) -> str:
    """Replace non-alphanumeric chars with underscore and uppercase."""
    return re.sub(r"[^A-Z0-9]", "_", text.upper())


def build_pvr_key(tl_name: str, tl_code: str, report_date_str: str) -> str:
    """
    Build the R2 object key for a PVR PDF.
    Format: {R2_PREFIX}/{YYYY}/{MM}/{DD}/{TL_NAME}_{TL_CODE}/PVR_{TL_CODE}_{YYYY-MM-DD}.pdf
    report_date_str must be 'YYYY-MM-DD'.
    """
    parts = report_date_str.split("-")
    yyyy, mm, dd = parts[0], parts[1], parts[2]
    safe_name = _sanitize(tl_name)
    safe_code = _sanitize(tl_code)
    prefix = settings.R2_PREFIX.strip("/") if settings.R2_PREFIX else "pvr"
    return f"{prefix}/{yyyy}/{mm}/{dd}/{safe_name}_{safe_code}/PVR_{safe_code}_{report_date_str}.pdf"


def upload_pdf(key: str, pdf_bytes: bytes, content_type: str = "application/pdf") -> str:
    """Upload PDF bytes to R2 and return the key."""
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.R2_BUCKET,
        Key=key,
        Body=pdf_bytes,
        ContentType=content_type,
    )
    logger.info("Uploaded PVR to R2: %s (%d bytes)", key, len(pdf_bytes))
    return key


def download_pdf(key: str) -> bytes:
    """Download and return raw bytes of a PVR PDF from R2."""
    client = _get_s3_client()
    resp = client.get_object(Bucket=settings.R2_BUCKET, Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> None:
    """Delete an object from R2 (best-effort)."""
    try:
        client = _get_s3_client()
        client.delete_object(Bucket=settings.R2_BUCKET, Key=key)
        logger.info("Deleted R2 object: %s", key)
    except ClientError as exc:
        logger.warning("Failed to delete R2 object %s: %s", key, exc)


def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL valid for `expires_in` seconds."""
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )

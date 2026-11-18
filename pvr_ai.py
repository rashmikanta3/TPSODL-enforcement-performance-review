"""
Gemini-based AI quality evaluator for PVR (Patrolling Verification Report) PDFs.

Uses the Gemini REST API via urllib (no SDK dependency).
Sends a base64-encoded PDF as inline_data with a structured prompt.
"""
import base64
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    """Raised when the Gemini API call fails after retries."""


PVR_CHECKLIST = [
    "1. Report header includes TL name, TL code, circle, and date.",
    "2. Patrol route / area of operation is clearly specified.",
    "3. Consumer inspection details (name, ID, address) are present for each visit.",
    "4. Meter reading / status recorded for each consumer inspected.",
    "5. Theft / irregularity observations noted with specific evidence.",
    "6. Photographs or supporting evidence references included.",
    "7. VCR / load booking numbers referenced where applicable.",
    "8. Summary section with total consumers inspected and irregularities found.",
    "9. TL signature / authorisation mark is present.",
    "10. Report is legible, structured, and free of significant omissions.",
]


def _build_prompt() -> str:
    checklist_text = "\n".join(PVR_CHECKLIST)
    return (
        "You are a strict quality auditor for TPSODL Enforcement PVR "
        "(Patrolling Verification Report) documents.\n\n"
        "Evaluate the attached PDF against the following checklist:\n"
        f"{checklist_text}\n\n"
        "Return a JSON object with these exact keys:\n"
        "  score        – integer 0-10 (10 = perfect)\n"
        "  verdict      – one of GOOD, AVERAGE, POOR\n"
        "  summary      – 2-3 sentence overall assessment\n"
        "  findings     – array of objects, each with:\n"
        "                   item (string – checklist item number),\n"
        "                   status (PASS / FAIL / PARTIAL),\n"
        "                   remark (brief explanation)\n"
        "  suggestions  – array of improvement suggestion strings\n\n"
        "Rules:\n"
        "- Score 8-10 = GOOD, 5-7 = AVERAGE, 0-4 = POOR.\n"
        "- Be objective and concise.\n"
        "- Output ONLY valid JSON, no markdown fencing."
    )


def evaluate_pvr(pdf_bytes: bytes) -> dict:
    """
    Send PDF to Gemini for quality evaluation.
    Returns parsed JSON dict with score, verdict, summary, findings, suggestions.
    Retries up to 4 times on 429/500/503 with exponential backoff.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not configured")

    model = settings.GEMINI_MODEL or "gemini-2.0-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    prompt_text = _build_prompt()

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_b64,
                        }
                    },
                    {"text": prompt_text},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        },
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }

    max_retries = 4
    backoff_secs = [10, 20, 30, 60]

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp_body = resp.read().decode("utf-8")
            return _parse_response(resp_body)
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            if status_code in (429, 500, 503) and attempt < max_retries:
                wait = backoff_secs[attempt] if attempt < len(backoff_secs) else 60
                logger.warning(
                    "Gemini API %d on attempt %d/%d – retrying in %ds",
                    status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise GeminiError(
                f"Gemini API error {status_code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                wait = backoff_secs[attempt] if attempt < len(backoff_secs) else 60
                logger.warning(
                    "Gemini URL error on attempt %d/%d – retrying in %ds: %s",
                    attempt + 1, max_retries, wait, exc,
                )
                time.sleep(wait)
                continue
            raise GeminiError(f"Gemini connection error: {exc}") from exc

    raise GeminiError("Gemini API failed after all retries")


def _parse_response(raw: str) -> dict:
    """Extract the JSON evaluation from the Gemini API response body."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Invalid JSON from Gemini: {raw[:300]}") from exc

    # Navigate the standard Gemini response structure
    try:
        text = envelope["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiError(
            f"Unexpected Gemini response structure: {raw[:300]}"
        ) from exc

    # Strip optional markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last line (``` markers)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiError(
            f"Gemini returned non-JSON text: {cleaned[:300]}"
        ) from exc

    # Clamp score and derive verdict
    score = int(result.get("score", 0))
    score = max(0, min(10, score))
    result["score"] = score
    if score >= 8:
        result["verdict"] = "GOOD"
    elif score >= 5:
        result["verdict"] = "AVERAGE"
    else:
        result["verdict"] = "POOR"

    return result


def format_message(result: dict) -> str:
    """Format AI result into a human-readable summary string."""
    lines = [
        f"Score: {result.get('score', '?')}/10 — Verdict: {result.get('verdict', '?')}",
        f"Summary: {result.get('summary', 'N/A')}",
        "",
        "Findings:",
    ]
    for f in result.get("findings", []):
        lines.append(
            f"  [{f.get('status', '?')}] Item {f.get('item', '?')}: {f.get('remark', '')}"
        )
    suggestions = result.get("suggestions", [])
    if suggestions:
        lines.append("")
        lines.append("Suggestions:")
        for s in suggestions:
            lines.append(f"  • {s}")
    return "\n".join(lines)

"""
TPSODL Enforcement MIS - Automated WhatsApp Scheduled Message Dispatcher
--------------------------------------------------------------------------
Schedules (IST - Asia/Kolkata):
1. "Daily Squad Operations & Performance Summary"
   - Once daily at 11:30 AM.
   - Squad table image(s) (22 squads per image so it stays readable on a phone)
     + caption with squad status counts and the list of unreported squads.

2. "TPSODL ENFORCEMENT DAILY PERFORMANCE SUMMARY"
   - Every hour from 11:00 AM to 9:00 PM (11:00, 12:00, ... 21:00).
   - KPI poster + circle table image + caption with totals and a circle table.

Sends through the Baileys container (POST /send-image, /send-message, header x-api-key).
Needs only packages already in requirements.txt (SQLAlchemy, Pillow, python-dotenv).

Usage:
  python schedule_messege_sender.py                  start the scheduler (keep it running)
  python schedule_messege_sender.py --now hourly     send the performance summary now
  python schedule_messege_sender.py --now squad      send the squad summary now
  python schedule_messege_sender.py --preview hourly save PNG + caption to ./wa_preview (no send)
  python schedule_messege_sender.py --groups         list WhatsApp groups and their JIDs
  python schedule_messege_sender.py --check          test database + gateway connection
  (add --date YYYY-MM-DD to --now / --preview for another day)

NOTE: run only ONE scheduler (this file OR send_message.py / the in-app scheduler),
otherwise the group receives every report twice.
"""
from __future__ import annotations
import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==============================================================================
# CONFIGURATION (.env or environment variables)
# ==============================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tpsodl.db")

# Base URL of the Baileys container. A full endpoint like .../send-image is also accepted.
BAILEYS_API_URL = os.getenv("BAILEYS_API_URL", "http://127.0.0.1:3000")
BAILEYS_API_KEY = os.getenv("BAILEYS_API_KEY", "")
TARGET_GROUP_JID = os.getenv("TARGET_GROUP_JID", "120363430050205896@g.us")

HOURLY_START, HOURLY_END = 11, 21          # 11:00 AM .. 09:00 PM
SQUAD_TIME = (11, 30)                      # 11:30 AM
GRACE_MINUTES = 20                         # retry a missed slot (gateway down) for this long
STATE_FILE = os.getenv("WA_STATE_FILE", "./data/wa_sender_state.json")

CIRCLES = ["BERHAMPUR", "CITY", "ASKA", "BHANJANAGAR", "JEYPORE", "RAYAGADA"]
ACTIVE_MODES = ("INDEPENDENT_WITH_TL", "INDEPENDENT_WITHOUT_TL_COLLECTION", "MERGED")

# India has no daylight saving, so a fixed +05:30 offset is exact on any server clock
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def gateway_base() -> str:
    url = BAILEYS_API_URL.rstrip("/")
    for suffix in ("/send-image", "/send-message"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


# ==============================================================================
# FORMATTING (Indian number style, same as the dashboard)
# ==============================================================================
def _indian(n) -> str:
    n = int(round(float(n or 0)))
    s, neg = str(abs(n)), n < 0
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + s


def fmt_num(v) -> str:
    return _indian(v)


def fmt_kw(v) -> str:
    v = float(v or 0)
    return f"{_indian(v) if v == int(v) else f'{v:,.1f}'} kW"


def format_inr(val) -> str:
    val = float(val or 0.0)
    if abs(val) >= 1_00_00_000:
        return f"₹{val / 1_00_00_000:.2f} Cr"
    if abs(val) >= 1_00_000:
        return f"₹{val / 1_00_000:.2f} L"
    return f"₹{_indian(val)}"


def short_inr(val) -> str:
    """Very compact rupee value for the monospace caption table (max ~6 chars)."""
    val = float(val or 0.0)
    if val >= 1_00_00_000:
        return f"{val / 1_00_00_000:.1f}Cr"
    if val >= 1_00_000:
        return f"{val / 1_00_000:.1f}L"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return f"{val:.0f}"


def strip_code(name) -> str:
    """'Sanjay Behera (TL101)' -> 'Sanjay Behera' (employee codes are not shown)."""
    s = re.sub(r"\s*[(\[][^()\[\]]*[)\]]\s*$", "", str(name or "")).strip()
    return s or str(name or "")


# ==============================================================================
# DATABASE
# ==============================================================================
_engine = None


def get_db_engine():
    global _engine
    if _engine is None:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def run_query(sql: str, params: dict) -> list[dict]:
    with get_db_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


# Field squads only (office teams / teams without vehicle are not credited) - same rule as the dashboard
FIELD_ONLY = "(COALESCE(t.has_vehicle, TRUE) = TRUE AND COALESCE(t.is_office_team, FALSE) = FALSE)"


def circle_expr(col: str) -> str:
    return f"CASE WHEN UPPER({col}) IN ('CITY', 'BERHAMPUR CITY') THEN 'CITY' ELSE UPPER({col}) END"


SQL_LOAD = f"""
    SELECT {circle_expr('l.circle')} AS circle,
           COUNT(l.id) AS cases,
           COALESCE(SUM(l.booked_load), 0) AS load_kw
    FROM load_bookings l
    LEFT JOIN teams t ON l.team_id = t.id
    WHERE l.booking_date = :day AND (l.team_id IS NULL OR {FIELD_ONLY})
    GROUP BY 1
"""

# disconnection_records has no circle column: take it from the VCR master (fallback: the team's circle)
SQL_DC = f"""
    SELECT {circle_expr('COALESCE(v.circle, t.circle)')} AS circle,
           COUNT(d.id) AS dc_count,
           COALESCE(SUM(d.amount_pending), 0) AS dc_arrear
    FROM disconnection_records d
    LEFT JOIN teams t ON d.team_id = t.id
    LEFT JOIN vcr_masters v ON v.vcr_number = d.vcr_number
    WHERE d.dc_date = :day AND (d.team_id IS NULL OR {FIELD_ONLY})
    GROUP BY 1
"""

SQL_COLLECTION = f"""
    SELECT {circle_expr('c.circle')} AS circle,
           COALESCE(SUM(c.amount_paid), 0) AS collection_rs,
           COUNT(c.id) AS mr_count
    FROM collections c
    LEFT JOIN teams t ON c.team_name = t.name
    WHERE c.payment_date = :day AND (c.team_name IS NULL OR t.id IS NULL OR {FIELD_ONLY})
    GROUP BY 1
"""

SQL_SQUADS = """
    SELECT
        t.id AS team_id,
        t.name AS team_name,
        t.circle AS circle,
        COALESCE(dtl.name, dto.tl_name, deftl.name, t.assigned_team_lead) AS operated_by_tl,
        (COALESCE(t.is_office_team, FALSE) = TRUE OR COALESCE(t.has_vehicle, TRUE) = FALSE) AS is_office,
        dto.operation_mode AS operation_mode,
        mt.name AS merged_with,
        dto.remarks AS remarks,
        COALESCE(vlb.run_km, 0) AS km_run,
        COALESCE(lb.cases, 0) AS cases,
        COALESCE(lb.load_kw, 0) AS load_kw,
        COALESCE(dc.dc_count, 0) AS dc_count,
        COALESCE(dc.dc_amount, 0) AS dc_amount,
        COALESCE(col.amount_paid, 0) AS amount_collected,
        COALESCE(att.present_staff, 0) AS present_staff,
        COALESCE(emp.total_staff, 0) AS total_staff
    FROM teams t
    LEFT JOIN daily_team_operations dto ON dto.team_id = t.id AND dto.operation_date = :day
    LEFT JOIN team_leads dtl ON dtl.id = dto.daily_tl_id
    LEFT JOIN team_leads deftl ON deftl.id = t.default_tl_id
    LEFT JOIN teams mt ON mt.id = dto.merged_with_team_id
    LEFT JOIN (SELECT team_id, SUM(run_km) AS run_km FROM vehicle_log_books
               WHERE date = :day GROUP BY team_id) vlb ON vlb.team_id = t.id
    LEFT JOIN (SELECT team_id, COUNT(id) AS cases, SUM(booked_load) AS load_kw FROM load_bookings
               WHERE booking_date = :day GROUP BY team_id) lb ON lb.team_id = t.id
    LEFT JOIN (SELECT team_id, COUNT(id) AS dc_count, SUM(amount_pending) AS dc_amount FROM disconnection_records
               WHERE dc_date = :day GROUP BY team_id) dc ON dc.team_id = t.id
    LEFT JOIN (SELECT team_name, SUM(amount_paid) AS amount_paid FROM collections
               WHERE payment_date = :day GROUP BY team_name) col ON col.team_name = t.name
    LEFT JOIN (SELECT team_id, COUNT(id) AS total_staff FROM employees
               WHERE is_active = TRUE GROUP BY team_id) emp ON emp.team_id = t.id
    LEFT JOIN (SELECT operation_id, COUNT(id) AS present_staff FROM attendance
               WHERE status = 'P' GROUP BY operation_id) att ON att.operation_id = dto.id
    WHERE t.is_active = TRUE
    ORDER BY t.circle, t.name
"""


def fetch_hourly_kpi_metrics(day: date) -> dict:
    """Today's circle-wise Load Booking, DC and Collection (aggregated in SQL) + active squad count."""
    p = {"day": day}
    merged = {c: {"circle": c, "cases": 0, "load_kw": 0.0, "dc_count": 0, "dc_arrear": 0.0,
                  "collection_rs": 0.0, "mr_count": 0} for c in CIRCLES}
    for sql in (SQL_LOAD, SQL_DC, SQL_COLLECTION):
        for r in run_query(sql, p):
            key = r.pop("circle") or "UNKNOWN"
            row = merged.setdefault(key, {"circle": key, "cases": 0, "load_kw": 0.0, "dc_count": 0,
                                          "dc_arrear": 0.0, "collection_rs": 0.0, "mr_count": 0})
            row.update({k: float(v or 0) for k, v in r.items()})
    rows = list(merged.values())

    squads = fetch_squad_operations_metrics(day)
    active = sum(1 for s in squads if s["mode"] in ACTIVE_MODES)
    totals = {k: sum(r[k] for r in rows) for k in ("cases", "load_kw", "dc_count", "dc_arrear", "collection_rs", "mr_count")}
    return {"day": day, "rows": rows, "totals": totals, "active_squads": active, "total_squads": len(squads)}


def fetch_squad_operations_metrics(day: date) -> list[dict]:
    rows = run_query(SQL_SQUADS, {"day": day})
    for r in rows:
        r["is_office"] = bool(r["is_office"])
        r["mode"] = "OFFICE_DUTY_NO_VEHICLE" if r["is_office"] else (r["operation_mode"] or "UNREPORTED")
        r["operated_by_tl"] = strip_code(r["operated_by_tl"]) or "Unassigned"
        for k in ("km_run", "cases", "dc_count", "present_staff", "total_staff"):
            r[k] = int(r[k] or 0)
        for k in ("load_kw", "dc_amount", "amount_collected"):
            r[k] = float(r[k] or 0)
    return rows


# ==============================================================================
# IMAGE RENDERING (Pillow) - large fonts, phone-friendly widths
# ==============================================================================
NAVY, ACCENT, INK, MUTED = "#0B2545", "#F4B400", "#0F172A", "#64748B"
ZEBRA, TOTAL_BG, LINE = "#F6F8FB", "#DCE6F2", "#E2E8F0"
MODE_STYLE = {
    "INDEPENDENT_WITH_TL": ("Active with TL", "#DCFCE7", "#166534", "🟢"),
    "INDEPENDENT_WITHOUT_TL_COLLECTION": ("Collection Only", "#DBEAFE", "#1E40AF", "🔵"),
    "MERGED": ("Merged", "#FEF3C7", "#92400E", "🟠"),
    "OFFICE_DUTY_NO_VEHICLE": ("Office (No Veh)", "#E2E8F0", "#334155", "⚪"),
    "NON_OPERATIONAL": ("Non-Operational", "#FEE2E2", "#991B1B", "🔴"),
    "UNREPORTED": ("Unreported", "#F1F5F9", "#64748B", "⚫"),
}
_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        for folder in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "C:/Windows/Fonts/", ""):
            try:
                _fonts[key] = ImageFont.truetype(folder + name, size)
                break
            except OSError:
                continue
        else:
            try:
                _fonts[key] = ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
            except OSError:
                _fonts[key] = ImageFont.load_default(size=size)
    return _fonts[key]


def _fit(draw, txt, f, max_w):
    txt = str(txt)
    if draw.textlength(txt, font=f) <= max_w:
        return txt
    while txt and draw.textlength(txt + "…", font=f) > max_w:
        txt = txt[:-1]
    return txt + "…"


def _cell(draw, box, txt, f, fill=INK, align="left", pad=14):
    x, y, w, h = box
    t = _fit(draw, txt, f, w - 2 * pad)
    tw = draw.textlength(t, font=f)
    tx = x + pad if align == "left" else (x + w - pad - tw if align == "right" else x + (w - tw) / 2)
    draw.text((tx, y + h / 2), t, font=f, fill=fill, anchor="lm")


def _header(draw, W, title, subtitle):
    draw.rectangle([0, 0, W, 130], fill=NAVY)
    draw.rectangle([0, 122, W, 130], fill=ACCENT)
    draw.text((40, 30), "TPSODL ENFORCEMENT", font=font(20, True), fill=ACCENT, anchor="lm")
    draw.text((40, 66), title, font=font(32, True), fill="#FFFFFF", anchor="lm")
    draw.text((40, 102), subtitle, font=font(18), fill="#CBD5E1", anchor="lm")
    return 130


def _footer(draw, W, H, note=""):
    draw.line([40, H - 52, W - 40, H - 52], fill=LINE, width=2)
    draw.text((40, H - 28), f"TPSODL Enforcement MIS  •  Generated {now_ist():%d-%m-%Y %I:%M %p}",
              font=font(16), fill=MUTED, anchor="lm")
    if note:
        draw.text((W - 40, H - 28), note, font=font(16, True), fill=MUTED, anchor="rm")


def _png_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def generate_hourly_kpi_poster(data: dict, as_of: datetime) -> str:
    W, PAD, tile_h, row_h = 1080, 40, 150, 52
    rows, t = data["rows"], data["totals"]
    H = 130 + 30 + 2 * tile_h + 16 + 40 + 52 + (len(rows) + 1) * row_h + 40 + 60
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    y = _header(d, W, "Daily Enforcement Performance",
                f"ALL CIRCLES  •  {data['day']:%d-%m-%Y}  •  as of {as_of:%I:%M %p}") + 30

    tiles = [
        ("LOAD BOOKED", fmt_kw(t["load_kw"]), f"{fmt_num(t['cases'])} theft cases", "#1D4ED8"),
        ("COLLECTION", format_inr(t["collection_rs"]), f"{fmt_num(t['mr_count'])} MR receipts", "#0E8A5F"),
        ("DC EXECUTED", fmt_num(t["dc_count"]), f"{format_inr(t['dc_arrear'])} arrears", "#B91C1C"),
        ("ACTIVE SQUADS", fmt_num(data["active_squads"]), f"of {fmt_num(data['total_squads'])} squads", "#C2410C"),
        ("THEFT CASES", fmt_num(t["cases"]), "detected", "#7B3FC4"),
        ("MR RECEIPTS", fmt_num(t["mr_count"]), "issued", "#334155"),
    ]
    gap, tw = 16, (W - 2 * PAD - 32) / 3
    for i, (label, value, sub, bg) in enumerate(tiles):
        x, ty = PAD + (i % 3) * (tw + gap), y + (i // 3) * (tile_h + gap)
        d.rounded_rectangle([x, ty, x + tw, ty + tile_h], radius=14, fill=bg)
        d.text((x + 20, ty + 28), label, font=font(18, True), fill="#E2E8F0", anchor="lm")
        size = 40
        while d.textlength(value, font=font(size, True)) > tw - 40 and size > 24:
            size -= 2
        d.text((x + 20, ty + 76), value, font=font(size, True), fill="#FFFFFF", anchor="lm")
        d.text((x + 20, ty + 122), _fit(d, sub, font(18), tw - 40), font=font(18), fill="#E2E8F0", anchor="lm")
    y += 2 * tile_h + gap + 40

    cols = [("Circle", 230, "left", lambda r: r["circle"]),
            ("Load", 150, "right", lambda r: fmt_kw(r["load_kw"])),
            ("Cases", 90, "right", lambda r: fmt_num(r["cases"])),
            ("Collection", 150, "right", lambda r: format_inr(r["collection_rs"])),
            ("MR", 80, "right", lambda r: fmt_num(r["mr_count"])),
            ("DC", 80, "right", lambda r: fmt_num(r["dc_count"])),
            ("DC Arrears", 140, "right", lambda r: format_inr(r["dc_arrear"]))]
    scale = (W - 2 * PAD) / sum(c[1] for c in cols)
    d.rounded_rectangle([PAD, y, W - PAD, y + 52], radius=8, fill=NAVY)
    x = PAD
    for title, w, align, _ in cols:
        _cell(d, (x, y, w * scale, 52), title, font(19, True), "#FFFFFF", align)
        x += w * scale
    y += 52
    total_row = {"circle": "TOTAL", **t}
    for i, r in enumerate(rows + [total_row]):
        is_tot = i == len(rows)
        d.rectangle([PAD, y, W - PAD, y + row_h], fill=TOTAL_BG if is_tot else (ZEBRA if i % 2 else "#FFFFFF"))
        x = PAD
        for title, w, align, f in cols:
            _cell(d, (x, y, w * scale, row_h), f(r), font(20, is_tot or align == "left"), INK, align)
            x += w * scale
        y += row_h
    _footer(d, W, H)
    return _png_b64(img)


ROWS_PER_PAGE = 22


def generate_squad_operations_pages(rows: list[dict], counts: dict, day: date) -> list[str]:
    W, PAD, row_h, head_h = 1480, 40, 54, 54
    cols = [("#", 56, "center"), ("Squad", 220, "left"), ("Operated By (TL)", 240, "left"),
            ("Mode", 175, "center"), ("Form D", 100, "center"), ("KM", 95, "right"),
            ("Load (Cases)", 185, "right"), ("DC / Arrears", 185, "right"), ("Collection", 150, "right")]
    scale = (W - 2 * PAD) / sum(c[1] for c in cols)
    widths = [c[1] * scale for c in cols]
    chips = [(MODE_STYLE[m][0], counts.get(m, 0), c) for m, c in (
        ("INDEPENDENT_WITH_TL", "#16A34A"), ("INDEPENDENT_WITHOUT_TL_COLLECTION", "#2563EB"), ("MERGED", "#D97706"),
        ("OFFICE_DUTY_NO_VEHICLE", "#64748B"), ("NON_OPERATIONAL", "#DC2626"), ("UNREPORTED", "#94A3B8"))]
    field = [r for r in rows if not r["is_office"]]
    tot = {"km": sum(r["km_run"] for r in field), "kw": sum(r["load_kw"] for r in field),
           "cases": sum(r["cases"] for r in field), "dc": sum(r["dc_count"] for r in field),
           "dc_amt": sum(r["dc_amount"] for r in field), "coll": sum(r["amount_collected"] for r in field)}

    chunks = [rows[i:i + ROWS_PER_PAGE] for i in range(0, len(rows), ROWS_PER_PAGE)] or [[]]
    pages = []
    for p, chunk in enumerate(chunks, 1):
        last = p == len(chunks)
        H = 130 + 24 + 64 + 24 + head_h + max(len(chunk) + (1 if last else 0), 1) * row_h + 40 + 60
        img = Image.new("RGB", (W, H), "#FFFFFF")
        d = ImageDraw.Draw(img)
        page_txt = f"  •  page {p}/{len(chunks)}" if len(chunks) > 1 else ""
        y = _header(d, W, "Daily Squad Operations & Performance Summary",
                    f"ALL CIRCLES  •  {day:%d-%m-%Y}  •  {len(rows)} squads{page_txt}") + 24

        cw = (W - 2 * PAD - 5 * 12) / 6
        for i, (label, val, colr) in enumerate(chips):
            x = PAD + i * (cw + 12)
            d.rounded_rectangle([x, y, x + cw, y + 64], radius=10, fill="#F8FAFC", outline=LINE, width=2)
            d.rounded_rectangle([x, y, x + 8, y + 64], radius=4, fill=colr)
            d.text((x + 24, y + 22), label, font=font(16, True), fill=MUTED, anchor="lm")
            d.text((x + 24, y + 46), fmt_num(val), font=font(22, True), fill=INK, anchor="lm")
        y += 88

        d.rounded_rectangle([PAD, y, W - PAD, y + head_h], radius=8, fill=NAVY)
        x = PAD
        for (title, _, align), w in zip(cols, widths):
            _cell(d, (x, y, w, head_h), title, font(18, True), "#FFFFFF", align, pad=6 if align == "center" else 14)
            x += w
        y += head_h
        if not rows:
            d.text((W / 2, y + row_h / 2), "No squad operations recorded for this day.", font=font(20), fill=MUTED, anchor="mm")

        for j, r in enumerate(chunk):
            n = (p - 1) * ROWS_PER_PAGE + j + 1
            d.rectangle([PAD, y, W - PAD, y + row_h], fill=ZEBRA if j % 2 else "#FFFFFF")
            label, bg, fg, _ = MODE_STYLE.get(r["mode"], MODE_STYLE["UNREPORTED"])
            off = r["is_office"]
            values = [str(n), None, r["operated_by_tl"], None, f"{r['present_staff']} / {r['total_staff']}",
                      "-" if off else fmt_num(r["km_run"]),
                      "-" if off else f"{fmt_kw(r['load_kw'])} ({r['cases']})",
                      "-" if off else f"{r['dc_count']} / {format_inr(r['dc_amount'])}",
                      "-" if off else format_inr(r["amount_collected"])]
            x = PAD
            for k, ((title, _, align), w) in enumerate(zip(cols, widths)):
                if title == "Squad":
                    sub = f"{r['circle']}  →  {r['merged_with']}" if r["mode"] == "MERGED" and r.get("merged_with") else r["circle"]
                    d.text((x + 14, y + 19), _fit(d, r["team_name"], font(18, True), w - 28), font=font(18, True), fill=INK, anchor="lm")
                    d.text((x + 14, y + 39), _fit(d, sub, font(14), w - 28), font=font(14), fill=MUTED, anchor="lm")
                elif title == "Mode":
                    pf = font(15, True)
                    pw = min(d.textlength(label, font=pf) + 24, w - 12)
                    px = x + (w - pw) / 2
                    d.rounded_rectangle([px, y + 13, px + pw, y + row_h - 13], radius=12, fill=bg)
                    d.text((px + pw / 2, y + row_h / 2), _fit(d, label, pf, pw - 16), font=pf, fill=fg, anchor="mm")
                else:
                    is_coll = title == "Collection" and not off
                    _cell(d, (x, y, w, row_h), values[k], font(18, is_coll), "#0E7A53" if is_coll else INK,
                          align, pad=6 if align == "center" else 14)
                x += w
            y += row_h

        if last and rows:
            d.rectangle([PAD, y, W - PAD, y + row_h], fill=TOTAL_BG)
            d.line([PAD, y, W - PAD, y], fill=NAVY, width=2)
            _cell(d, (PAD, y, sum(widths[:5]), row_h), f"TOTAL — {len(rows)} squads", font(19, True))
            x = PAD + sum(widths[:5])
            for w, v in zip(widths[5:], [fmt_num(tot["km"]), f"{fmt_kw(tot['kw'])} ({fmt_num(tot['cases'])})",
                                          f"{fmt_num(tot['dc'])} / {format_inr(tot['dc_amt'])}", format_inr(tot["coll"])]):
                _cell(d, (x, y, w, row_h), v, font(17, True), INK, "right", pad=10)
                x += w
        _footer(d, W, H, f"Page {p} of {len(chunks)}" if len(chunks) > 1 else "")
        pages.append(_png_b64(img))
    return pages


# ==============================================================================
# WHATSAPP CAPTIONS (bold *x*, italic _x_, monospace ```x``` for aligned tables)
# ==============================================================================
DIVIDER = "━━━━━━━━━━━━━━━━━━"


def hourly_caption(data: dict, as_of: datetime) -> str:
    t, rows = data["totals"], data["rows"]
    table = ["CIRCLE      kW Case  Coll  DC"]
    for r in rows:
        table.append(f"{r['circle'][:9]:<9}{r['load_kw']:>5.1f}{int(r['cases']):>5}"
                     f"{short_inr(r['collection_rs']):>6}{int(r['dc_count']):>4}")
    kw_tot = f"{t['load_kw']:.1f}" if t["load_kw"] < 1000 else f"{t['load_kw']:.0f}"
    table.append(f"{'TOTAL':<9}{kw_tot:>5}{int(t['cases']):>5}"
                 f"{short_inr(t['collection_rs']):>6}{int(t['dc_count']):>4}")
    best = max(rows, key=lambda r: (r["load_kw"], r["collection_rs"]), default=None)
    lines = [
        "⚡ *TPSODL ENFORCEMENT*",
        "*DAILY PERFORMANCE SUMMARY*",
        f"📅 {data['day']:%d %b %Y}  •  🕐 {as_of:%I:%M %p}",
        DIVIDER,
        f"⚡ *Load Booked:* {fmt_kw(t['load_kw'])}  ({fmt_num(t['cases'])} cases)",
        f"💰 *Collection:* {format_inr(t['collection_rs'])}  ({fmt_num(t['mr_count'])} MR)",
        f"🔌 *DC Executed:* {fmt_num(t['dc_count'])}  ({format_inr(t['dc_arrear'])} arrears)",
        f"🚗 *Active Squads:* {data['active_squads']} / {data['total_squads']}",
        DIVIDER,
        "📊 *Circle-wise*",
        "```" + "\n".join(table) + "```",
    ]
    if best and (best["load_kw"] or best["collection_rs"]):
        lines.append(f"🏆 *Top circle:* {best['circle']} – {fmt_kw(best['load_kw'])}, {format_inr(best['collection_rs'])}")
    lines.append("_TPSODL Enforcement MIS • auto report_")
    return "\n".join(lines)


def squad_caption(rows: list[dict], counts: dict, day: date, as_of: datetime) -> str:
    field = [r for r in rows if not r["is_office"]]
    active = sum(counts.get(m, 0) for m in ACTIVE_MODES)
    present = sum(r["present_staff"] for r in rows)
    staff = sum(r["total_staff"] for r in rows)
    lines = [
        "📋 *TPSODL ENFORCEMENT*",
        "*DAILY SQUAD OPERATIONS & PERFORMANCE*",
        f"📅 {day:%d %b %Y}  •  🕐 status at {as_of:%I:%M %p}",
        DIVIDER,
        f"🚗 *{len(rows)} squads*  •  ✅ *{active} operational*",
    ]
    for mode, (label, _, _, dot) in MODE_STYLE.items():
        lines.append(f"{dot} {label}: *{counts.get(mode, 0)}*")
    lines += [
        DIVIDER,
        f"👷 *Form D attendance:* {fmt_num(present)} / {fmt_num(staff)} present",
        f"⚡ *Load:* {fmt_kw(sum(r['load_kw'] for r in field))}  ({fmt_num(sum(r['cases'] for r in field))} cases)",
        f"🔌 *DC:* {fmt_num(sum(r['dc_count'] for r in field))}  •  💰 *Coll:* {format_inr(sum(r['amount_collected'] for r in field))}",
    ]
    pending = [r["team_name"] for r in rows if r["mode"] == "UNREPORTED"]
    if pending:
        shown = ", ".join(pending[:12]) + (f" +{len(pending) - 12} more" if len(pending) > 12 else "")
        lines += [DIVIDER, f"⚠️ *Not reported yet ({len(pending)}):*", shown]
    lines.append("_Full squad table in the image above ☝️_")
    return "\n".join(lines)


def mode_counts(rows: list[dict]) -> dict:
    counts = {m: 0 for m in MODE_STYLE}
    for r in rows:
        counts[r["mode"] if r["mode"] in counts else "UNREPORTED"] += 1
    return counts


# ==============================================================================
# BAILEYS GATEWAY
# ==============================================================================
def _gateway(method: str, path: str, payload: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(
        gateway_base() + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "x-api-key": BAILEYS_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Baileys HTTP {e.code} on {path}: {e.read().decode(errors='ignore')[:200]}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise RuntimeError(f"Baileys not reachable at {gateway_base()}: {e}") from None


def gateway_connected() -> bool:
    try:
        return bool(_gateway("GET", "/health", timeout=10).get("connected"))
    except RuntimeError:
        return False


def post_to_baileys(image_b64: str | None, caption: str, retries: int = 3) -> None:
    """Sends an image + caption (or plain text when image_b64 is None). Retries on failure."""
    path, payload = (("/send-image", {"jid": TARGET_GROUP_JID, "imageBase64": image_b64, "caption": caption})
                     if image_b64 else ("/send-message", {"jid": TARGET_GROUP_JID, "message": caption}))
    for attempt in range(1, retries + 1):
        try:
            _gateway("POST", path, payload, timeout=90)
            return
        except RuntimeError as e:
            if attempt == retries:
                raise
            print(f"[!] {e} - retrying ({attempt}/{retries})", flush=True)
            time.sleep(5 * attempt)


# ==============================================================================
# JOBS
# ==============================================================================
def build_hourly(day: date, as_of: datetime):
    data = fetch_hourly_kpi_metrics(day)
    return hourly_caption(data, as_of), [generate_hourly_kpi_poster(data, as_of)]


def build_squad(day: date, as_of: datetime):
    rows = fetch_squad_operations_metrics(day)
    counts = mode_counts(rows)
    return squad_caption(rows, counts, day, as_of), generate_squad_operations_pages(rows, counts, day)


def send_report(caption: str, images: list[str]) -> None:
    """First image carries the caption, the rest follow without caption."""
    for i, img in enumerate(images):
        post_to_baileys(img, caption if i == 0 else "")
        time.sleep(2)
    if not images:
        post_to_baileys(None, caption)


def job_send_hourly_performance_summary(as_of: datetime | None = None) -> None:
    as_of = as_of or now_ist()
    caption, images = build_hourly(as_of.date(), as_of)
    send_report(caption, images)
    print(f"[✓] {as_of:%d-%m-%Y %H:%M} Hourly Performance Summary sent to {TARGET_GROUP_JID}", flush=True)


def job_send_daily_squad_operations(as_of: datetime | None = None) -> None:
    as_of = as_of or now_ist()
    caption, images = build_squad(as_of.date(), as_of)
    send_report(caption, images)
    print(f"[✓] {as_of:%d-%m-%Y %H:%M} Squad Operations Summary sent ({len(images)} image/s)", flush=True)


# ==============================================================================
# SCHEDULER (no extra packages; restart-safe - a slot is never sent twice)
# ==============================================================================
def _load_sent() -> list:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_sent(sent: list) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(sent[-300:], f)


def due_jobs(now: datetime, sent: set) -> list:
    jobs = []
    if HOURLY_START <= now.hour <= HOURLY_END:
        slot = now.replace(minute=0, second=0, microsecond=0)
        key = f"hourly {slot:%Y-%m-%d %H:%M}"
        if now < slot + timedelta(minutes=GRACE_MINUTES) and key not in sent:
            jobs.append((key, job_send_hourly_performance_summary))
    slot = now.replace(hour=SQUAD_TIME[0], minute=SQUAD_TIME[1], second=0, microsecond=0)
    key = f"squad {slot:%Y-%m-%d}"
    if slot <= now < slot + timedelta(minutes=GRACE_MINUTES) and key not in sent:
        jobs.append((key, job_send_daily_squad_operations))
    return jobs


def main_loop() -> None:
    print("=" * 72)
    print("TPSODL Enforcement Automated WhatsApp Scheduler started")
    print(f"• Squad Operations    : daily at {SQUAD_TIME[0]:02d}:{SQUAD_TIME[1]:02d} IST")
    print(f"• Performance Summary : every hour {HOURLY_START:02d}:00 - {HOURLY_END:02d}:00 IST")
    print(f"• Target Group JID    : {TARGET_GROUP_JID}")
    print(f"• Gateway             : {gateway_base()}  (connected: {gateway_connected()})")
    print("=" * 72, flush=True)
    attempts = {}
    while True:
        now = now_ist()
        sent = _load_sent()
        for key, job in due_jobs(now, set(sent)):
            if attempts.get(key, 0) >= 5:
                continue
            attempts[key] = attempts.get(key, 0) + 1
            if not gateway_connected():
                print(f"[!] {key}: WhatsApp gateway not connected, will retry next minute", flush=True)
                continue
            try:
                job(now)
                sent.append(key)
                _save_sent(sent)
            except Exception as e:  # never let one failure stop the scheduler
                print(f"[-] {key} failed (attempt {attempts[key]}/5): {e}", flush=True)
        time.sleep(60 - datetime.now().second + 2)


# ==============================================================================
# ENTRYPOINT
# ==============================================================================
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="TPSODL WhatsApp report scheduler")
    ap.add_argument("--now", choices=["hourly", "squad"], help="send a report immediately")
    ap.add_argument("--preview", choices=["hourly", "squad"], help="save images + caption to ./wa_preview")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--groups", action="store_true", help="list WhatsApp groups")
    ap.add_argument("--check", action="store_true", help="test database and gateway")
    a = ap.parse_args(argv)

    if a.groups:
        for g in _gateway("GET", "/groups"):
            print(f"{g.get('jid', g.get('id')):<40} {g.get('name', g.get('subject', ''))}")
        return
    if a.check:
        try:
            run_query("SELECT COUNT(*) AS n FROM teams", {})
            print("[✓] Database OK")
        except Exception as e:
            print(f"[-] Database error: {e}")
        print(f"[{'✓' if gateway_connected() else '-'}] Gateway {gateway_base()} connected: {gateway_connected()}")
        return

    report = a.now or a.preview
    if not report:
        try:
            main_loop()
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
        return

    as_of = now_ist()
    if a.date:
        as_of = datetime.combine(date.fromisoformat(a.date), as_of.time())
    caption, images = (build_hourly if report == "hourly" else build_squad)(as_of.date(), as_of)

    if a.preview:
        os.makedirs("wa_preview", exist_ok=True)
        with open(f"wa_preview/{report}.txt", "w", encoding="utf-8") as f:
            f.write(caption)
        for i, img in enumerate(images, 1):
            with open(f"wa_preview/{report}_{i}.png", "wb") as f:
                f.write(base64.b64decode(img))
        print(caption)
        print(f"\nSaved {len(images)} image(s) to ./wa_preview")
        return

    send_report(caption, images)
    print(f"[✓] {report} report sent to {TARGET_GROUP_JID}")


if __name__ == "__main__":
    main(sys.argv[1:])
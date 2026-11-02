import io
import calendar
from datetime import datetime, date
from typing import Optional, List, Dict
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

SUPPORTED_CIRCLES = ["JEYPORE", "RAYAGADA", "BHANJANAGAR", "ASKA", "BERHAMPUR", "CITY"]

# =========================================================================
# DYNAMIC AGENCY CONFIGURATION BY CIRCLE
# =========================================================================
DEFAULT_AGENCY = {
    "name": "AMMAN ASSOCIATED SERVICES PRIVATE LIMITED",
    "address": "Corporate Office: DCB 126, DLF Cybercity, Technology Corridor, Patia, Bhubaneswar - 751024"
}

_NIRMAL = {
    "name": "M/S NIRMAL KUMAR SAMANTARAY",
    "address": "Electrical Contractor & Labour Provider Plot No D/1165,Sector-10 CDA Cuttack 753014 Mob-9337140466"
}

# Add or update specific circles and their agency company/address details here
CIRCLE_AGENCY_MAP: Dict[str, Dict[str, str]] = {
    "JEYPORE": DEFAULT_AGENCY,
    "RAYAGADA": DEFAULT_AGENCY,
    "BHANJANAGAR": _NIRMAL,
    "ASKA": _NIRMAL,
    "BERHAMPUR": _NIRMAL,
    "CITY": _NIRMAL,
}


def get_agency_header(circle_name: Optional[str]) -> Dict[str, str]:
    """Returns the company name and base address for a given circle."""
    if not circle_name:
        return DEFAULT_AGENCY
    return CIRCLE_AGENCY_MAP.get(circle_name.strip().upper(), DEFAULT_AGENCY)


# =========================================================================
# THEME + SHARED HELPERS
# =========================================================================
# Black & white print-safe palette: pure black text/rules + light greys only.
NAVY = colors.black                      # (name kept) heading text and heavy rules
INK = colors.black
GREY_TXT = colors.HexColor('#333333')
GRID = colors.HexColor('#444444')
HEADER_BG = colors.HexColor('#d0d0d0')   # table header row
ZEBRA = colors.HexColor('#f4f4f4')
TOTAL_BG = colors.HexColor('#e2e2e2')
SUNDAY_BG = colors.HexColor('#e6e6e6')
META_BG = colors.HexColor('#f4f4f4')

PAGE_W, PAGE_H = landscape(A4)          # 841.89 x 595.27
FOOTER_MARGIN = 95                      # space reserved for the signature block


def t(value) -> str:
    """Escape user data for safe use inside Paragraph markup."""
    return escape(str(value if value is not None else ""))


def fit(widths: List[float], total: float) -> List[float]:
    """Scale column widths proportionally so the table fills `total` points."""
    s = float(sum(widths))
    return [w * total / s for w in widths]


def fmt_date(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%d-%m-%Y")
    s = str(v or "")
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return s


def get_report_styles():
    base = getSampleStyleSheet()['Normal']

    def style(name, **kw):
        return ParagraphStyle(name, parent=base, **kw)

    return {
        'company': style('Company', fontName='Helvetica-Bold', fontSize=13, leading=16,
                         alignment=1, textColor=NAVY),
        'sub': style('Sub', fontName='Helvetica', fontSize=7.5, leading=10,
                     alignment=1, textColor=GREY_TXT),
        'title': style('Title', fontName='Helvetica-Bold', fontSize=10.5, leading=14,
                       alignment=1, textColor=INK),
        'meta': style('Meta', fontName='Helvetica', fontSize=8.5, leading=11, textColor=INK),
        'meta_right': style('MetaR', fontName='Helvetica', fontSize=8.5, leading=11,
                            textColor=INK, alignment=2),
        'th': style('TH', fontName='Helvetica-Bold', fontSize=8, leading=10,
                    alignment=1, textColor=colors.black),
        'th_sm': style('THSm', fontName='Helvetica-Bold', fontSize=7, leading=8.5,
                       alignment=1, textColor=colors.black),
        'cell': style('Cell', fontName='Helvetica', fontSize=8, leading=10, textColor=INK),
        'cell_sm': style('CellSm', fontName='Helvetica', fontSize=7.5, leading=9, textColor=INK),
        'cell_center': style('CellC', fontName='Helvetica', fontSize=8, leading=10,
                             alignment=1, textColor=INK),
        'cell_bold_center': style('CellBC', fontName='Helvetica-Bold', fontSize=8, leading=10,
                                  alignment=1, textColor=INK),
        'cell_bold_right': style('CellBR', fontName='Helvetica-Bold', fontSize=8, leading=10,
                                 alignment=2, textColor=INK),
        'day': style('Day', fontName='Helvetica', fontSize=7, leading=9,
                     alignment=1, textColor=INK),
        'legend': style('Legend', fontName='Helvetica', fontSize=7, leading=9, textColor=GREY_TXT),
    }


def add_header(story, st, circle_name, title_lines, sub_line=None):
    """Agency name/address, double rule, then one or more title lines."""
    agency = get_agency_header(circle_name)
    story.append(Paragraph(t(agency["name"]), st['company']))
    story.append(Paragraph(t(agency["address"]), st['sub']))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.6, color=NAVY, spaceBefore=0, spaceAfter=1.5))
    story.append(HRFlowable(width="100%", thickness=0.5, color=NAVY, spaceBefore=0, spaceAfter=5))
    for line in title_lines:
        story.append(Paragraph(line, st['title']))
    if sub_line:
        story.append(Paragraph(sub_line, st['sub']))
    story.append(Spacer(1, 6))


def meta_bar(st, items, total_w):
    """One-row info bar: [(label, value), ...]; last item is right-aligned."""
    cells = []
    for i, (label, value) in enumerate(items):
        style = st['meta_right'] if (i == len(items) - 1 and len(items) > 1) else st['meta']
        cells.append(Paragraph(f"<b>{t(label)}:</b> {t(value)}", style))
    bar = Table([cells], colWidths=fit([1] * len(cells), total_w))
    bar.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, GRID),
        ('BACKGROUND', (0, 0), (-1, -1), META_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return bar


def base_table_style(pad=3):
    return [
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('BOX', (0, 0), (-1, -1), 1.0, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1.0, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, GRID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), pad),
        ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]


def total_row_style(row_idx):
    return [
        ('BACKGROUND', (0, row_idx), (-1, row_idx), TOTAL_BG),
        ('LINEABOVE', (0, row_idx), (-1, row_idx), 1.2, NAVY),
        ('TOPPADDING', (0, row_idx), (-1, row_idx), 5),
        ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 5),
    ]


def make_signature_footer(sig_lines: List[str]):
    """
    Draws ONE signature block (with a signing line) at the bottom right of
    every page, plus the generation time and page number.
    """
    generated = datetime.now().strftime("%d-%m-%Y %H:%M")

    def draw_footer(canv, doc):
        w = doc.pagesize[0]
        left = doc.leftMargin
        right = w - doc.rightMargin

        canv.saveState()
        canv.setStrokeColor(NAVY)

        x = right - 230
        canv.setStrokeColor(colors.HexColor('#374151'))
        canv.setLineWidth(0.5)
        canv.line(x, 72, right, 72)

        y = 62
        canv.setFillColor(INK)
        for i, text in enumerate(sig_lines):
            canv.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 8)
            canv.drawString(x, y, text)
            y -= 10

        canv.setFont("Helvetica", 7)
        canv.setFillColor(GREY_TXT)
        canv.drawString(left, 18, f"Generated on {generated}")
        canv.drawRightString(right, 18, f"Page {doc.page}")
        canv.restoreState()

    return draw_footer


def new_doc(buffer, title, margin_lr=30, top=28):
    return SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=margin_lr,
        rightMargin=margin_lr,
        topMargin=top,
        bottomMargin=FOOTER_MARGIN,
        title=title,
        author="Enforcement & Vigilance Cell, TPSODL",
    )


EE_SIGNATURE = lambda circle: [
    "Executive Engineer (Elect.)",
    "Enforcement & Vigilance Cell",
    f"TPSODL, {circle.upper()} Circle",
]


# =========================================================================
# 1. CIRCLE LOG SUMMARY (Signature: Executive Engineer)
# =========================================================================
def build_circle_log_pdf(circle_name: str, year: int, month: int, rows: list, total_km: int) -> bytes:
    buffer = io.BytesIO()
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()

    doc = new_doc(buffer, f"Vehicle Log Summary - {circle_up} - {month_name} {year}", margin_lr=36, top=30)
    usable = PAGE_W - 72
    st = get_report_styles()
    story = []

    add_header(story, st, circle_name, [
        f"VIGILANCE ENFORCEMENT CELL, {t(circle_up)} CIRCLE",
        f"MONTH OF {month_name} VEHICLE LOG BOOK TOTAL KILOMETER DETAILS - {year}",
    ])
    story.append(meta_bar(st, [("Circle Name", circle_up), ("Period", f"{month_name} {year}")], usable))
    story.append(Spacer(1, 8))

    headers = [
        Paragraph("Sl<br/>No.", st['th']),
        Paragraph("Area / Team", st['th']),
        Paragraph("Team Leader", st['th']),
        Paragraph("Supervisor", st['th']),
        Paragraph("Vehicle No.", st['th']),
        Paragraph("Total Monthly<br/>Km's Running", st['th']),
    ]
    data = [headers]

    for idx, r in enumerate(rows, start=1):
        data.append([
            Paragraph(str(idx), st['cell_center']),
            Paragraph(t(r.get('team_name', '')), st['cell']),
            Paragraph(t(r.get('team_lead') or r.get('team_leader') or '-'), st['cell']),
            Paragraph(t(r.get('supervisor') or '-'), st['cell']),
            Paragraph(t(r.get('vehicle_no') or 'N/A'), st['cell_center']),
            Paragraph(t(r.get('total_km', 0)), st['cell_bold_center']),
        ])

    if not rows:
        data.append([Paragraph("No records found for this period.", st['cell_center'])] + [""] * 5)

    data.append([
        Paragraph(f"TOTAL KILOMETERS OF {t(circle_up)} CIRCLE", st['cell_bold_right']),
        "", "", "", "",
        Paragraph(f"{total_km} KM", st['cell_bold_center']),
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=4) + [
        ('ROWBACKGROUNDS', (0, 1), (-1, last - 1), [colors.white, ZEBRA]),
        ('SPAN', (0, last), (4, last)),
    ] + total_row_style(last)
    if not rows:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=fit([35, 174, 185, 185, 95, 95], usable), repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)

    cb = make_signature_footer(EE_SIGNATURE(circle_name))
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()


# =========================================================================
# 2. FORM D ATTENDANCE
#    Employees are listed team-wise (grouped & sorted), with a team header
#    row before each team. Total row sums ONLY the last four summary columns.
# =========================================================================
_STATUS_FMT = {
    "P": "P",
    "A": '<font color="#b91c1c"><b>A</b></font>',
    "L": '<font color="#b45309"><b>L</b></font>',
    "WO": '<font color="#475569" size="5"><b>WO</b></font>',   # smaller so it never wraps in a narrow day column
}


def _att_status(attendance_map: dict, emp: dict, year: int, month: int, d: int) -> str:
    """Looks up a day's status; accepts (emp_id, 'YYYY-MM-DD') or {emp_code: {day: status}} maps."""
    date_key = f"{year}-{str(month).zfill(2)}-{str(d).zfill(2)}"
    status = attendance_map.get((emp.get('id'), date_key))
    if status is None:
        by_code = attendance_map.get(emp.get('emp_code'))
        if isinstance(by_code, dict):
            status = by_code.get(d)
    return status or "-"


def build_form_d_pdf(
    circle_name: str,
    year: int,
    month: int,
    employees: list,
    attendance_map: dict,
    team_lead: Optional[str] = None,
    team_name: Optional[str] = None
) -> bytes:
    buffer = io.BytesIO()
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()
    _, num_days = calendar.monthrange(year, month)

    doc = new_doc(buffer, f"Form D Attendance - {circle_up} - {month_name} {year}", margin_lr=20, top=25)
    usable = PAGE_W - 40
    st = get_report_styles()
    story = []

    scope = f"Team: {t(team_name)} | " if team_name else ""
    add_header(
        story, st, circle_name,
        [f"FORM D - ATTENDANCE REGISTER FOR THE MONTH OF {month_name} {year}"],
        sub_line=f"Circle: {t(circle_up)} | {scope}Days in Month: {num_days}",
    )

    # ---- column geometry (fills the page, day columns flex with month length)
    fixed_left = [26, 82, 125]
    summary_w = [40, 40, 40, 34]
    day_w = min(16.0, (usable - sum(fixed_left) - sum(summary_w)) / num_days)
    col_widths = fixed_left + [day_w] * num_days + summary_w

    first_day_col = 3
    last_day_col = 2 + num_days
    sum_cols = list(range(last_day_col + 1, last_day_col + 5))

    # ---- header row (day number + weekday initial)
    weekday_letters = "MTWTFSS"
    sundays = []
    day_headers = []
    for d in range(1, num_days + 1):
        wd = calendar.weekday(year, month, d)
        if wd == 6:
            sundays.append(first_day_col + d - 1)
        day_headers.append(Paragraph(
            f"<b>{d}</b><br/><font size=5.5>{weekday_letters[wd]}</font>", st['th_sm']))

    headers = [
        Paragraph("Sl", st['th']),
        Paragraph("Designation", st['th']),
        Paragraph("Employee Name", st['th']),
        *day_headers,
        Paragraph("Present<br/>Days", st['th_sm']),
        Paragraph("Absent<br/>Days", st['th_sm']),
        Paragraph("Leave<br/>Days", st['th_sm']),
        Paragraph("Weekly<br/>Off", st['th_sm']),
    ]
    data = [headers]
    n_cols = len(headers)

    grand_p = grand_a = grand_l = grand_wo = 0
    team_header_rows = []
    emp_rows = []
    current_team = object()
    show_team_rows = not team_name   # single-team report already names the team in the header

    for idx, emp in enumerate(employees, start=1):
        emp_team = emp.get('team_name') or "UNASSIGNED"
        if show_team_rows and emp_team != current_team:
            current_team = emp_team
            team_header_rows.append(len(data))
            data.append([Paragraph(f"<b>TEAM: {t(emp_team.upper())}</b>", st['cell'])] + [""] * (n_cols - 1))

        p_c = a_c = l_c = wo_c = 0
        day_cells = []

        for d in range(1, num_days + 1):
            status = _att_status(attendance_map, emp, year, month, d)

            if status == "P":
                p_c += 1
            elif status == "A":
                a_c += 1
            elif status == "L":
                l_c += 1
            elif status == "WO":
                wo_c += 1

            day_cells.append(Paragraph(_STATUS_FMT.get(status, t(status)), st['day']))

        grand_p += p_c
        grand_a += a_c
        grand_l += l_c
        grand_wo += wo_c

        emp_rows.append(len(data))
        data.append([
            Paragraph(str(idx), st['cell_center']),
            Paragraph(t(emp.get('designation') or '-'), st['cell_sm']),
            Paragraph(t(emp.get('name', '')), st['cell_sm']),
            *day_cells,
            Paragraph(str(p_c), st['cell_bold_center']),
            Paragraph(str(a_c), st['cell_bold_center']),
            Paragraph(str(l_c), st['cell_bold_center']),
            Paragraph(str(wo_c), st['cell_bold_center']),
        ])

    if not employees:
        data.append([Paragraph("No employees found.", st['cell_center'])] + [""] * (n_cols - 1))

    # ---- total row: label + the four summary totals only; day cells stay blank
    data.append([
        Paragraph("TOTAL", st['cell_bold_right']),
        "", "",
        *[""] * num_days,
        Paragraph(str(grand_p), st['cell_bold_center']),
        Paragraph(str(grand_a), st['cell_bold_center']),
        Paragraph(str(grand_l), st['cell_bold_center']),
        Paragraph(str(grand_wo), st['cell_bold_center']),
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=3) + [
        # tighter padding in the narrow day columns
        ('LEFTPADDING', (first_day_col, 0), (last_day_col, -1), 1),
        ('RIGHTPADDING', (first_day_col, 0), (last_day_col, -1), 1),
        ('ALIGN', (first_day_col, 0), (last_day_col, -1), 'CENTER'),
        # label spans Sl..Name; blank day cells merged
        ('SPAN', (0, last), (2, last)),
        ('SPAN', (first_day_col, last), (last_day_col, last)),
    ]
    # light shading on Sunday columns (employee rows only)
    for r in emp_rows:
        for c in sundays:
            cmds.append(('BACKGROUND', (c, r), (c, r), SUNDAY_BG))
    # team header rows span the full width
    for r in team_header_rows:
        cmds += [
            ('SPAN', (0, r), (-1, r)),
            ('BACKGROUND', (0, r), (-1, r), HEADER_BG),
            ('LINEABOVE', (0, r), (-1, r), 1.0, colors.black),
            ('LEFTPADDING', (0, r), (-1, r), 6),
        ]
    # emphasise the four summary columns
    cmds.append(('LINEBEFORE', (sum_cols[0], 0), (sum_cols[0], -1), 1.0, NAVY))
    cmds += total_row_style(last)
    if not employees:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "P - Present &nbsp;&nbsp; A - Absent &nbsp;&nbsp; L - Leave &nbsp;&nbsp; "
        "WO - Weekly Off &nbsp;&nbsp; (shaded columns: Sundays)", st['legend']))

    if team_lead:
        sig_lines = [f"({team_lead})", f"Enforcement Cell, TPSODL, {circle_up} Circle"]
    else:
        sig_lines = EE_SIGNATURE(circle_name)

    cb = make_signature_footer(sig_lines)
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()



# =========================================================================
# 3. TEAM VEHICLE LOG BOOK (Signature column + one sign block)
# =========================================================================
def build_team_log_pdf(team_name: str, circle: str, team_lead: str, year: int, month: int, daily_logs: list) -> bytes:
    buffer = io.BytesIO()
    month_name = calendar.month_name[month].upper()
    circle_up = circle.upper()

    doc = new_doc(buffer, f"Daily Vehicle Log - {team_name} - {month_name} {year}", margin_lr=28, top=28)
    usable = PAGE_W - 56
    st = get_report_styles()
    story = []

    add_header(story, st, circle, [
        f"VIGILANCE ENFORCEMENT CELL, {t(circle_up)} CIRCLE",
        f"DAILY VEHICLE LOG BOOK - {t(team_name.upper())}",
    ])
    story.append(meta_bar(st, [
        ("Team Name", team_name),
        ("Team Leader", team_lead or "N/A"),
        ("Period", f"{month_name} {year}"),
    ], usable))
    story.append(Spacer(1, 8))

    headers = [
        Paragraph("Date", st['th']),
        Paragraph("Vehicle No.", st['th']),
        Paragraph("Supervisor", st['th']),
        Paragraph("Time<br/>(In - Out)", st['th']),
        Paragraph("Journey Route (From - To)", st['th']),
        Paragraph("Start<br/>KM", st['th']),
        Paragraph("End<br/>KM", st['th']),
        Paragraph("Run<br/>KM", st['th']),
        Paragraph("Signature", st['th']),
    ]
    data = [headers]

    total_km = 0
    for r in (daily_logs or []):
        run_km = int(r.get('total_km') or r.get('run_km') or 0)
        total_km += run_km
        start_t = r.get('start_time') or r.get('time_in') or ''
        end_t = r.get('end_time') or r.get('time_out') or ''
        if start_t and end_t:
            time_txt = f"{t(start_t)} - {t(end_t)}"
        elif start_t or end_t:
            time_txt = f"{t(start_t or '-')} - {t(end_t or '-')}"
        else:
            time_txt = "-"
        data.append([
            Paragraph(fmt_date(r.get('date', '')), st['cell_center']),
            Paragraph(t(r.get('vehicle_no') or 'N/A'), st['cell_center']),
            Paragraph(t(r.get('supervisor_name') or r.get('supervisor') or r.get('driver_name') or '-'), st['cell']),
            Paragraph(time_txt, st['cell_center']),
            Paragraph(t(r.get('area_movement') or r.get('journey_route') or r.get('route_details') or '-'), st['cell']),
            Paragraph(t(r.get('start_km', 0)), st['cell_center']),
            Paragraph(t(r.get('end_km', 0)), st['cell_center']),
            Paragraph(str(run_km), st['cell_bold_center']),
            Paragraph("", st['cell_center']),   # left blank for physical signature
        ])

    if not daily_logs:
        data.append([Paragraph("No vehicle entries logged for this month.", st['cell_center'])] + [""] * 8)

    data.append([
        Paragraph("TOTAL MONTHLY KILOMETER'S RUNNING", st['cell_bold_right']),
        "", "", "", "", "", "",
        Paragraph(f"{total_km} KM", st['cell_bold_center']),
        "",
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=6) + [
        ('ROWBACKGROUNDS', (0, 1), (-1, last - 1), [colors.white, ZEBRA]),
        ('SPAN', (0, last), (6, last)),
    ] + total_row_style(last)
    if not daily_logs:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=fit([55, 65, 100, 105, 200, 48, 48, 48, 95], usable), repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)

    cb = make_signature_footer([f"({team_lead})", f"Enforcement Cell, TPSODL, {circle_up} Circle"])
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()


# =========================================================================
# 4. TEAM PERFORMANCE REPORT (month-wise, one row per team, no date column)
# =========================================================================
def _g(r, *keys, default=None):
    """Read the first non-empty value from a dict or ORM object across alternate key names."""
    for k in keys:
        v = r.get(k) if isinstance(r, dict) else getattr(r, k, None)
        if v not in (None, ""):
            return v
    return default


def build_team_performance_pdf(
    circle_name: str,
    year: int,
    month: int,
    performance_rows: List[dict]
) -> bytes:
    buffer = io.BytesIO()
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()

    doc = new_doc(buffer, f"Team Performance - {circle_up} - {month_name} {year}", margin_lr=30, top=28)
    usable = PAGE_W - 60
    st = get_report_styles()
    story = []

    add_header(
        story, st, circle_name,
        [f"TEAM-WISE OPERATIONAL PERFORMANCE REPORT - {month_name} {year}"],
        sub_line=f"Enforcement & Vigilance Cell | Circle: {t(circle_up)}",
    )

    headers = [
        Paragraph("Sl", st['th']),
        Paragraph("Team Name", st['th']),
        Paragraph("Team Leader", st['th']),
        Paragraph("Supervisor", st['th']),
        Paragraph("Load Booked<br/>(KW)", st['th']),
        Paragraph("Amount Coll.<br/>(Rs.)", st['th']),
        Paragraph("No. of<br/>DC", st['th']),
        Paragraph("KM Run", st['th']),
        Paragraph("Emp Present<br/>(Man-days)", st['th']),
    ]
    data = [headers]

    tot_load = tot_amount = 0.0
    tot_dc = tot_km = tot_emp = 0

    for idx, r in enumerate(performance_rows or [], start=1):
        load_val = float(_g(r, 'load_booked_kw', 'load_booked', default=0.0))
        amt_val = float(_g(r, 'amount_collected', default=0.0))
        dc_val = int(_g(r, 'dc_count', 'number_of_dc', default=0))
        km_val = int(_g(r, 'km_run', 'total_km', default=0))
        emp_val = int(_g(r, 'emp_present_count', default=0))

        tot_load += load_val
        tot_amount += amt_val
        tot_dc += dc_val
        tot_km += km_val
        tot_emp += emp_val

        data.append([
            Paragraph(str(idx), st['cell_center']),
            Paragraph(t(_g(r, 'team_name', default='-')), st['cell']),
            Paragraph(t(_g(r, 'assigned_team_lead', 'team_lead', default='-')), st['cell']),
            Paragraph(t(_g(r, 'supervisor_name', 'supervisor', default='-')), st['cell']),
            Paragraph(f"{load_val:,.2f}", st['cell_center']),
            Paragraph(f"{amt_val:,.2f}", st['cell_center']),
            Paragraph(str(dc_val), st['cell_center']),
            Paragraph(str(km_val), st['cell_center']),
            Paragraph(str(emp_val), st['cell_bold_center']),
        ])

    if not performance_rows:
        data.append([Paragraph("No performance records found for this period.", st['cell_center'])] + [""] * 8)

    data.append([
        Paragraph("TOTAL", st['cell_bold_right']),
        "", "", "",
        Paragraph(f"{tot_load:,.2f}", st['cell_bold_center']),
        Paragraph(f"{tot_amount:,.2f}", st['cell_bold_center']),
        Paragraph(str(tot_dc), st['cell_bold_center']),
        Paragraph(str(tot_km), st['cell_bold_center']),
        Paragraph(str(tot_emp), st['cell_bold_center']),
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=4) + [
        ('ROWBACKGROUNDS', (0, 1), (-1, last - 1), [colors.white, ZEBRA]),
        ('SPAN', (0, last), (3, last)),
    ] + total_row_style(last)
    if not performance_rows:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=fit([30, 140, 135, 135, 80, 95, 55, 65, 75], usable), repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)

    cb = make_signature_footer(EE_SIGNATURE(circle_name))
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()


# =========================================================================
# 5. MR COLLECTION REGISTER (PDF) - every MR entry of the month
# =========================================================================
def build_collection_pdf(
    circle_name: str,
    year: int,
    month: int,
    records: list
) -> bytes:
    buffer = io.BytesIO()
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()

    doc = new_doc(buffer, f"MR Collection Register - {circle_up} - {month_name} {year}", margin_lr=28, top=28)
    usable = PAGE_W - 56
    st = get_report_styles()
    story = []

    add_header(
        story, st, circle_name,
        [f"MR COLLECTION REGISTER - {month_name} {year}"],
        sub_line=f"Enforcement & Vigilance Cell | Circle: {t(circle_up)}",
    )

    headers = [
        Paragraph("Sl", st['th']),
        Paragraph("VCR No.", st['th']),
        Paragraph("MR No.", st['th']),
        Paragraph("Date of<br/>Payment", st['th']),
        Paragraph("Division", st['th']),
        Paragraph("Sub Division", st['th']),
        Paragraph("Section", st['th']),
        Paragraph("Amount<br/>Paid (Rs.)", st['th']),
    ]
    data = [headers]

    tot_amount = 0.0
    for idx, r in enumerate(records or [], start=1):
        amt = float(_g(r, "amount_paid", default=0.0))
        tot_amount += amt

        data.append([
            Paragraph(str(idx), st['cell_center']),
            Paragraph(t(_g(r, "vcr_number", "vcr_no", default="-")), st['cell_center']),
            Paragraph(t(_g(r, "mr_number", "mr_no", default="-")), st['cell_center']),
            Paragraph(fmt_date(_g(r, "payment_date", default="-")), st['cell_center']),
            Paragraph(t(_g(r, "division", default="-")), st['cell']),
            Paragraph(t(_g(r, "subdivision", "sub_division", default="-")), st['cell']),
            Paragraph(t(_g(r, "section", default="-")), st['cell']),
            Paragraph(f"{amt:,.2f}", st['cell_bold_right']),
        ])

    if not records:
        data.append([Paragraph("No MR collection records found for this period.", st['cell_center'])] + [""] * 7)

    data.append([
        Paragraph("TOTAL AMOUNT PAID", st['cell_bold_right']),
        "", "", "", "", "", "",
        Paragraph(f"{tot_amount:,.2f}", st['cell_bold_right']),
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=3) + [
        ('ROWBACKGROUNDS', (0, 1), (-1, last - 1), [colors.white, ZEBRA]),
        ('SPAN', (0, last), (6, last)),
    ] + total_row_style(last)
    if not records:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=fit([30, 110, 110, 75, 120, 120, 120, 95], usable), repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)

    cb = make_signature_footer(EE_SIGNATURE(circle_name))
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()


# =========================================================================
# 6. LOAD BOOKING REGISTER (PDF) - every booking entry of the month
# =========================================================================
def build_load_booking_pdf(
    bookings: list,
    circle: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    period_label: Optional[str] = None
) -> bytes:
    buffer = io.BytesIO()
    circle_up = (circle or "ALL CIRCLES").strip().upper()
    if period_label:
        date_str = period_label
    elif from_date and to_date:
        date_str = f"{fmt_date(from_date)} to {fmt_date(to_date)}"
    else:
        date_str = "ALL DATES"

    doc = new_doc(buffer, f"Load Booking Register - {circle_up} - {date_str}", margin_lr=24, top=28)
    usable = PAGE_W - 48
    st = get_report_styles()
    story = []

    add_header(
        story, st, circle if circle and circle.upper() != "ALL" else None,
        [f"UNAUTHORIZED LOAD BOOKING REGISTER - {t(date_str.upper())}"],
        sub_line=f"Enforcement & Vigilance Cell | Circle: {t(circle_up)}",
    )

    headers = [
        Paragraph("Sl", st['th']),
        Paragraph("Booking<br/>Date", st['th']),
        Paragraph("Page<br/>No.", st['th']),
        Paragraph("Officer", st['th']),
        Paragraph("Team", st['th']),
        Paragraph("Division", st['th']),
        Paragraph("Sub Division", st['th']),
        Paragraph("Section", st['th']),
        Paragraph("Theft Type", st['th']),
        Paragraph("Load<br/>(kW)", st['th']),
        Paragraph("Status", st['th']),
    ]
    data = [headers]

    tot_load = 0.0
    for idx, b in enumerate(bookings or [], start=1):
        load_kw = float(_g(b, "booked_load", default=0.0))
        tot_load += load_kw

        data.append([
            Paragraph(str(idx), st['cell_center']),
            Paragraph(fmt_date(_g(b, "booking_date", default="-")), st['cell_center']),
            Paragraph(t(_g(b, "page_no", default="-")), st['cell_center']),
            Paragraph(t(_g(b, "punch_emp", default="-")), st['cell_sm']),
            Paragraph(t(_g(b, "team_name", default="-")), st['cell_sm']),
            Paragraph(t(_g(b, "division", default="-")), st['cell_sm']),
            Paragraph(t(_g(b, "subdivision", default="-")), st['cell_sm']),
            Paragraph(t(_g(b, "section", default="-")), st['cell_sm']),
            Paragraph(t(_g(b, "theft_type", default="-")), st['cell_center']),
            Paragraph(f"{load_kw:,.2f}", st['cell_bold_right']),
            Paragraph(t(_g(b, "status", default="PROCESSED")), st['cell_center']),
        ])

    if not bookings:
        data.append([Paragraph("No load booking records found for this period.", st['cell_center'])] + [""] * 10)

    data.append([
        Paragraph("TOTAL BOOKED LOAD (kW)", st['cell_bold_right']),
        "", "", "", "", "", "", "", "",
        Paragraph(f"{tot_load:,.2f}", st['cell_bold_right']),
        "",
    ])
    last = len(data) - 1

    cmds = base_table_style(pad=3) + [
        ('ROWBACKGROUNDS', (0, 1), (-1, last - 1), [colors.white, ZEBRA]),
        ('SPAN', (0, last), (8, last)),
    ] + total_row_style(last)
    if not bookings:
        cmds.append(('SPAN', (0, 1), (-1, 1)))

    table = Table(data, colWidths=fit([25, 58, 40, 90, 90, 85, 85, 85, 75, 60, 60], usable), repeatRows=1)
    table.setStyle(TableStyle(cmds))
    story.append(table)

    cb = make_signature_footer(EE_SIGNATURE(circle if circle and circle.upper() != "ALL" else "ALL"))
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buffer.getvalue()
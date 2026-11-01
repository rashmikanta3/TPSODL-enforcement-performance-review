import io
import calendar
from datetime import datetime, date
from typing import Optional, List, Dict
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.utils import get_column_letter

# Agency header configuration matching reports_pdf.py
DEFAULT_AGENCY = {
    "name": "AMMAN ASSOCIATED SERVICES PRIVATE LIMITED",
    "address": "Corporate Office: DCB 126, DLF Cybercity, Technology Corridor, Patia, Bhubaneswar - 751024"
}

_NIRMAL = {
    "name": "M/S NIRMAL KUMAR SAMANTARAY",
    "address": "Electrical Contractor & Labour Provider Plot No D/1165,Sector-10 CDA Cuttack 753014 Mob-9337140466"
}

CIRCLE_AGENCY_MAP: Dict[str, Dict[str, str]] = {
    "JEYPORE": DEFAULT_AGENCY,
    "RAYAGADA": DEFAULT_AGENCY,
    "BHANJANAGAR": _NIRMAL,
    "ASKA": _NIRMAL,
    "BERHAMPUR": _NIRMAL,
    "CITY": _NIRMAL,
}

def get_agency_header(circle_name: Optional[str]) -> Dict[str, str]:
    if not circle_name:
        return DEFAULT_AGENCY
    return CIRCLE_AGENCY_MAP.get(circle_name.strip().upper(), DEFAULT_AGENCY)


def apply_sheet_protection(ws):
    """
    SPREADSHEET PROTECTION: EXCEL DOWNLOADS MUST BE READ-ONLY & TAMPER-PROOF
    Locks worksheet so users cannot edit data cells or formulas.
    Explicitly disables formatting, insertion, deletion, and enforces password protection.
    """
    for row in ws.iter_rows():
        for cell in row:
            cell.protection = Protection(locked=True)
    ws.protection.sheet = True
    ws.protection.enable()
    ws.protection.password = "TPSODL@MIS"
    ws.protection.formatCells = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    ws.protection.insertColumns = False
    ws.protection.insertRows = False
    ws.protection.insertHyperlinks = False
    ws.protection.deleteColumns = False
    ws.protection.deleteRows = False
    ws.protection.selectLockedCells = True
    ws.protection.selectUnlockedCells = True


# =========================================================================
# 1. FORM D ATTENDANCE (EXCEL)
# =========================================================================
def build_form_d_excel(
    circle_name: str,
    year: int,
    month: int,
    employees: list,
    attendance_map: dict,
    team_lead: Optional[str] = None,
    team_name: Optional[str] = None
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Form D - {calendar.month_abbr[month]} {year}"
    ws.views.sheetView[0].showGridLines = True

    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()
    _, num_days = calendar.monthrange(year, month)
    agency = get_agency_header(circle_name)

    total_cols = 3 + num_days + 4  # Sl, Designation, Employee Name + Days + 4 Summaries
    last_col_letter = get_column_letter(total_cols)

    # Typography & Colors matching Form D PDF theme
    font_company = Font(name="Calibri", size=13, bold=True, color="000000")
    font_address = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True, color="000000")
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_th_sub = Font(name="Calibri", size=7.5, bold=True, color="475569")
    font_cell = Font(name="Calibri", size=9, bold=False, color="000000")
    font_cell_bold = Font(name="Calibri", size=9, bold=True, color="000000")
    
    font_status_p = Font(name="Calibri", size=9, bold=True, color="15803D")
    font_status_a = Font(name="Calibri", size=9, bold=True, color="B91C1C")
    font_status_l = Font(name="Calibri", size=9, bold=True, color="B45309")
    font_status_wo = Font(name="Calibri", size=8, bold=True, color="475569")

    thin_border_side = Side(style='thin', color='444444')
    thick_border_side = Side(style='medium', color='000000')
    double_border_side = Side(style='double', color='000000')

    grid_border = Border(
        left=thin_border_side, right=thin_border_side,
        top=thin_border_side, bottom=thin_border_side
    )

    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    sunday_fill = PatternFill(start_color="E6E6E6", end_color="E6E6E6", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Row 1: Company Header
    ws.merge_cells(f"A1:{last_col_letter}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_company
    ws["A1"].alignment = align_center

    # Row 2: Office Address
    ws.merge_cells(f"A2:{last_col_letter}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_address
    ws["A2"].alignment = align_center

    # Row 3: Register Title
    ws.merge_cells(f"A3:{last_col_letter}3")
    ws["A3"] = f"FORM D - ATTENDANCE REGISTER FOR THE MONTH OF {month_name} {year}"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    # Row 4: Meta Bar
    ws.merge_cells(f"A4:{last_col_letter}4")
    team_txt = f" | Team: {team_name}" if team_name else ""
    ws["A4"] = f"Circle: {circle_up}{team_txt} | Days in Month: {num_days}"
    ws["A4"].font = font_meta
    ws["A4"].alignment = align_center
    ws["A4"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    # Rows 5 & 6: Header Grid
    fixed_headers = [("A", "Sl"), ("B", "Designation"), ("C", "Employee Name")]
    for col_let, text in fixed_headers:
        ws.merge_cells(f"{col_let}5:{col_let}6")
        cell = ws[f"{col_let}5"]
        cell.value = text
        cell.font = font_th
        cell.alignment = align_center
        cell.fill = header_fill

    weekday_letters = "MTWTFSS"
    sunday_cols = []

    # Days 1 to num_days
    for d in range(1, num_days + 1):
        col_idx = 3 + d
        wd = calendar.weekday(year, month, d)
        if wd == 6:
            sunday_cols.append(col_idx)

        c5 = ws.cell(row=5, column=col_idx, value=d)
        c5.font = font_th
        c5.alignment = align_center
        c5.fill = header_fill

        c6 = ws.cell(row=6, column=col_idx, value=weekday_letters[wd])
        c6.font = font_th_sub
        c6.alignment = align_center
        c6.fill = header_fill

    # Summary Headers (merged rows 5 & 6)
    sum_headers = ["Present\nDays", "Absent\nDays", "Leave\nDays", "Weekly\nOff"]
    first_sum_col = 3 + num_days + 1
    for i, h_text in enumerate(sum_headers):
        col_idx = first_sum_col + i
        col_let = get_column_letter(col_idx)
        ws.merge_cells(f"{col_let}5:{col_let}6")
        cell = ws[f"{col_let}5"]
        cell.value = h_text
        cell.font = font_th
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.fill = header_fill

    for r in (5, 6):
        for col_idx in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=col_idx)
            cell.border = grid_border
            if not cell.fill.start_color.rgb:
                cell.fill = header_fill

    # Rows 7+: Employee Attendance Rows
    current_row = 7
    for idx, emp in enumerate(employees, start=1):
        emp_id = emp.get("id")
        ws.cell(row=current_row, column=1, value=idx).alignment = align_center
        ws.cell(row=current_row, column=2, value=emp.get("designation") or "-").alignment = align_left
        ws.cell(row=current_row, column=3, value=emp.get("name") or "").alignment = align_left

        ws.cell(row=current_row, column=1).font = font_cell
        ws.cell(row=current_row, column=2).font = font_cell
        ws.cell(row=current_row, column=3).font = font_cell

        is_zebra = (idx % 2 == 0)

        for d in range(1, num_days + 1):
            col_idx = 3 + d
            date_key = f"{year}-{str(month).zfill(2)}-{str(d).zfill(2)}"
            status = attendance_map.get((emp_id, date_key), "-")
            
            c = ws.cell(row=current_row, column=col_idx, value=status if status != "-" else "")
            c.alignment = align_center
            if status == "P":
                c.font = font_status_p
            elif status == "A":
                c.font = font_status_a
            elif status == "L":
                c.font = font_status_l
            elif status == "WO":
                c.font = font_status_wo
            else:
                c.font = font_cell

            # Sunday Shading
            if col_idx in sunday_cols:
                c.fill = sunday_fill
            elif is_zebra:
                c.fill = zebra_fill

        # Dynamic Excel Formulas for per-employee totals
        start_day_let = get_column_letter(4)
        end_day_let = get_column_letter(3 + num_days)
        
        c_p = ws.cell(row=current_row, column=first_sum_col)
        c_p.value = f'=COUNTIF({start_day_let}{current_row}:{end_day_let}{current_row},"P")'
        c_p.alignment = align_center
        c_p.font = font_cell_bold

        c_a = ws.cell(row=current_row, column=first_sum_col + 1)
        c_a.value = f'=COUNTIF({start_day_let}{current_row}:{end_day_let}{current_row},"A")'
        c_a.alignment = align_center
        c_a.font = font_cell_bold

        c_l = ws.cell(row=current_row, column=first_sum_col + 2)
        c_l.value = f'=COUNTIF({start_day_let}{current_row}:{end_day_let}{current_row},"L")'
        c_l.alignment = align_center
        c_l.font = font_cell_bold

        c_wo = ws.cell(row=current_row, column=first_sum_col + 3)
        c_wo.value = f'=COUNTIF({start_day_let}{current_row}:{end_day_let}{current_row},"WO")'
        c_wo.alignment = align_center
        c_wo.font = font_cell_bold

        for col_idx in range(1, total_cols + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.border = grid_border
            if col_idx not in sunday_cols and not cell.fill.start_color.rgb and is_zebra:
                cell.fill = zebra_fill

        current_row += 1

    # TOTAL ROW
    total_row = current_row
    ws.merge_cells(f"A{total_row}:C{total_row}")
    total_label = ws[f"A{total_row}"]
    total_label.value = "TOTAL"
    total_label.font = font_cell_bold
    total_label.alignment = align_right

    start_d_let = get_column_letter(4)
    end_d_let = get_column_letter(3 + num_days)
    ws.merge_cells(f"{start_d_let}{total_row}:{end_d_let}{total_row}")

    data_start_row = 7
    data_end_row = total_row - 1 if employees else 7
    
    # Grand SUM formulas for each summary column
    for i in range(4):
        col_idx = first_sum_col + i
        col_let = get_column_letter(col_idx)
        c_tot = ws.cell(row=total_row, column=col_idx)
        c_tot.value = f"=SUM({col_let}{data_start_row}:{col_let}{data_end_row})" if employees else 0
        c_tot.alignment = align_center
        c_tot.font = font_cell_bold

    for col_idx in range(1, total_cols + 1):
        cell = ws.cell(row=total_row, column=col_idx)
        cell.fill = total_fill
        cell.border = Border(
            left=thin_border_side, right=thin_border_side,
            top=thick_border_side, bottom=double_border_side
        )

    # Legend Row
    legend_row = total_row + 2
    ws.merge_cells(f"A{legend_row}:{last_col_letter}{legend_row}")
    leg_cell = ws[f"A{legend_row}"]
    leg_cell.value = "P - Present    A - Absent    L - Leave    WO - Weekly Off    (shaded columns: Sundays)"
    leg_cell.font = Font(name="Calibri", size=8.5, italic=True, color="475569")
    leg_cell.alignment = align_left

    # Signature Block (Right side)
    sig_row = legend_row + 2
    sig_col_start = get_column_letter(total_cols - 4)
    ws.merge_cells(f"{sig_col_start}{sig_row}:{last_col_letter}{sig_row}")
    
    sig_name = f"({team_lead})" if team_lead else "(Executive Engineer)"
    ws[f"{sig_col_start}{sig_row}"] = sig_name
    ws[f"{sig_col_start}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col_start}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col_start}{sig_row+1}:{last_col_letter}{sig_row+1}")
    ws[f"{sig_col_start}{sig_row+1}"] = f"Enforcement Cell, TPSODL, {circle_up} Circle"
    ws[f"{sig_col_start}{sig_row+1}"].font = font_cell
    ws[f"{sig_col_start}{sig_row+1}"].alignment = align_center

    # Column Widths
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 24
    for d in range(1, num_days + 1):
        ws.column_dimensions[get_column_letter(3 + d)].width = 4.2
    for i in range(4):
        ws.column_dimensions[get_column_letter(first_sum_col + i)].width = 11

    # Row Heights
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 18
    ws.row_dimensions[4].height = 18
    ws.row_dimensions[5].height = 16
    ws.row_dimensions[6].height = 14
    for r in range(7, total_row + 1):
        ws.row_dimensions[r].height = 18

    # SPREADSHEET PROTECTION: Read-only & Tamper-proof
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =========================================================================
# 2. CIRCLE VEHICLE LOG SUMMARY (EXCEL)
# =========================================================================
def build_circle_log_excel(circle_name: str, year: int, month: int, rows: list, total_km: int) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()
    ws.title = f"Circle Summary - {calendar.month_abbr[month]} {year}"
    ws.views.sheetView[0].showGridLines = True

    agency = get_agency_header(circle_name)
    total_cols = 6
    last_col_let = get_column_letter(total_cols)

    font_comp = Font(name="Calibri", size=13, bold=True)
    font_addr = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True)
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_cell = Font(name="Calibri", size=9)
    font_cell_bold = Font(name="Calibri", size=9, bold=True)

    thin_border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                         top=Side(style='thin', color='444444'), bottom=Side(style='thin', color='444444'))
    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Company Header & Titles
    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_comp
    ws["A1"].alignment = align_center

    ws.merge_cells(f"A2:{last_col_let}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_addr
    ws["A2"].alignment = align_center

    ws.merge_cells(f"A3:{last_col_let}3")
    ws["A3"] = f"VIGILANCE ENFORCEMENT CELL, {circle_up} CIRCLE"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    ws.merge_cells(f"A4:{last_col_let}4")
    ws["A4"] = f"MONTH OF {month_name} VEHICLE LOG BOOK TOTAL KILOMETER DETAILS - {year}"
    ws["A4"].font = font_title
    ws["A4"].alignment = align_center

    ws.merge_cells(f"A5:{last_col_let}5")
    ws["A5"] = f"Circle Name: {circle_up} | Period: {month_name} {year}"
    ws["A5"].font = font_meta
    ws["A5"].alignment = align_center
    ws["A5"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        "Sl No.", "Area / Team", "Team Leader",
        "Supervisor", "Vehicle No.", "Total Monthly Km's Running"
    ]
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_idx, value=h_text)
        cell.font = font_th
        cell.alignment = align_center
        cell.fill = header_fill
        cell.border = thin_border

    current_row = 7
    for idx, r in enumerate(rows, 1):
        ws.cell(row=current_row, column=1, value=idx).alignment = align_center
        ws.cell(row=current_row, column=2, value=r.get('team_name', '')).alignment = align_left
        ws.cell(row=current_row, column=3, value=r.get('team_lead') or r.get('team_leader') or '-').alignment = align_left
        ws.cell(row=current_row, column=4, value=r.get('supervisor') or '-').alignment = align_left
        ws.cell(row=current_row, column=5, value=r.get('vehicle_no') or 'N/A').alignment = align_center
        
        km_cell = ws.cell(row=current_row, column=6, value=int(r.get('total_km') or 0))
        km_cell.alignment = align_center
        km_cell.font = font_cell_bold
        km_cell.number_format = "#,##0"

        for col_idx in range(1, total_cols + 1):
            c = ws.cell(row=current_row, column=col_idx)
            c.border = thin_border
            if not c.font.bold:
                c.font = font_cell
            if idx % 2 == 0:
                c.fill = zebra_fill
        current_row += 1

    total_row = current_row
    ws.merge_cells(f"A{total_row}:E{total_row}")
    t_label = ws[f"A{total_row}"]
    t_label.value = f"TOTAL KILOMETERS OF {circle_up} CIRCLE"
    t_label.font = font_cell_bold
    t_label.alignment = align_right

    t_km = ws.cell(row=total_row, column=6)
    data_start = 7
    data_end = total_row - 1 if rows else 7
    t_km.value = f"=SUM(F{data_start}:F{data_end})" if rows else 0
    t_km.alignment = align_center
    t_km.font = font_cell_bold
    t_km.number_format = "#,##0"

    for col_idx in range(1, total_cols + 1):
        c = ws.cell(row=total_row, column=col_idx)
        c.fill = total_fill
        c.border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                          top=Side(style='medium', color='000000'), bottom=Side(style='double', color='000000'))

    # Signature Block
    sig_row = total_row + 3
    sig_col = get_column_letter(total_cols - 1)
    ws.merge_cells(f"{sig_col}{sig_row}:{last_col_let}{sig_row}")
    ws[f"{sig_col}{sig_row}"] = "Executive Engineer (Elect.)"
    ws[f"{sig_col}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+1}:{last_col_let}{sig_row+1}")
    ws[f"{sig_col}{sig_row+1}"] = "Enforcement & Vigilance Cell"
    ws[f"{sig_col}{sig_row+1}"].font = font_cell
    ws[f"{sig_col}{sig_row+1}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+2}:{last_col_let}{sig_row+2}")
    ws[f"{sig_col}{sig_row+2}"] = f"TPSODL, {circle_up} Circle"
    ws[f"{sig_col}{sig_row+2}"].font = font_cell
    ws[f"{sig_col}{sig_row+2}"].alignment = align_center

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 26
    ws.column_dimensions["D"].width = 26
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 22

    # SPREADSHEET PROTECTION: Read-only & Tamper-proof
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =========================================================================
# 3. TEAM VEHICLE DAILY LOG BOOK (EXCEL)
# =========================================================================
def build_team_log_excel(team_name: str, circle: str, team_lead: str, year: int, month: int, daily_logs: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    month_name = calendar.month_name[month].upper()
    circle_up = circle.upper()
    ws.title = f"Log Book - {calendar.month_abbr[month]} {year}"
    ws.views.sheetView[0].showGridLines = True

    agency = get_agency_header(circle)
    total_cols = 9
    last_col_let = get_column_letter(total_cols)

    font_comp = Font(name="Calibri", size=13, bold=True)
    font_addr = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True)
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_cell = Font(name="Calibri", size=9)
    font_cell_bold = Font(name="Calibri", size=9, bold=True)

    thin_border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                         top=Side(style='thin', color='444444'), bottom=Side(style='thin', color='444444'))
    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_comp
    ws["A1"].alignment = align_center

    ws.merge_cells(f"A2:{last_col_let}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_addr
    ws["A2"].alignment = align_center

    ws.merge_cells(f"A3:{last_col_let}3")
    ws["A3"] = f"VIGILANCE ENFORCEMENT CELL, {circle_up} CIRCLE"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    ws.merge_cells(f"A4:{last_col_let}4")
    ws["A4"] = f"DAILY VEHICLE LOG BOOK - {team_name.upper()}"
    ws["A4"].font = font_title
    ws["A4"].alignment = align_center

    ws.merge_cells(f"A5:{last_col_let}5")
    ws["A5"] = f"Team Name: {team_name} | Team Leader: {team_lead or 'N/A'} | Period: {month_name} {year}"
    ws["A5"].font = font_meta
    ws["A5"].alignment = align_center
    ws["A5"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        "Date", "Vehicle No.", "Supervisor", "Time (In - Out)",
        "Journey Route (From - To)", "Start KM", "End KM", "Run KM", "Signature"
    ]
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_idx, value=h_text)
        cell.font = font_th
        cell.alignment = align_center
        cell.fill = header_fill
        cell.border = thin_border

    current_row = 7
    for idx, r in enumerate(daily_logs or [], 1):
        raw_d = r.get('date', '')
        if hasattr(raw_d, "strftime"):
            d_str = raw_d.strftime("%d-%m-%Y")
        else:
            d_str = str(raw_d)
            try:
                d_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
            except Exception:
                pass

        start_t = r.get('start_time') or r.get('time_in') or ''
        end_t = r.get('end_time') or r.get('time_out') or ''
        if start_t and end_t:
            time_txt = f"{start_t} - {end_t}"
        elif start_t or end_t:
            time_txt = f"{start_t or '-'} - {end_t or '-'}"
        else:
            time_txt = "-"

        ws.cell(row=current_row, column=1, value=d_str).alignment = align_center
        ws.cell(row=current_row, column=2, value=r.get('vehicle_no') or 'N/A').alignment = align_center
        ws.cell(row=current_row, column=3, value=r.get('supervisor_name') or r.get('supervisor') or r.get('driver_name') or '-').alignment = align_left
        ws.cell(row=current_row, column=4, value=time_txt).alignment = align_center
        ws.cell(row=current_row, column=5, value=r.get('area_movement') or r.get('journey_route') or r.get('route_details') or '-').alignment = align_left

        s_km = ws.cell(row=current_row, column=6, value=int(r.get('start_km') or 0))
        s_km.alignment = align_center
        s_km.number_format = "#,##0"

        e_km = ws.cell(row=current_row, column=7, value=int(r.get('end_km') or 0))
        e_km.alignment = align_center
        e_km.number_format = "#,##0"

        # Formula: End KM - Start KM
        run_km_cell = ws.cell(row=current_row, column=8, value=f"=MAX(0, G{current_row}-F{current_row})")
        run_km_cell.alignment = align_center
        run_km_cell.font = font_cell_bold
        run_km_cell.number_format = "#,##0"

        ws.cell(row=current_row, column=9, value="").alignment = align_center

        for col_idx in range(1, total_cols + 1):
            c = ws.cell(row=current_row, column=col_idx)
            c.border = thin_border
            if not c.font.bold:
                c.font = font_cell
            if idx % 2 == 0:
                c.fill = zebra_fill
        current_row += 1

    total_row = current_row
    ws.merge_cells(f"A{total_row}:G{total_row}")
    t_label = ws[f"A{total_row}"]
    t_label.value = "TOTAL MONTHLY KILOMETER'S RUNNING"
    t_label.font = font_cell_bold
    t_label.alignment = align_right

    t_run = ws.cell(row=total_row, column=8)
    data_start = 7
    data_end = total_row - 1 if daily_logs else 7
    t_run.value = f"=SUM(H{data_start}:H{data_end})" if daily_logs else 0
    t_run.alignment = align_center
    t_run.font = font_cell_bold
    t_run.number_format = "#,##0"

    ws.cell(row=total_row, column=9, value="")

    for col_idx in range(1, total_cols + 1):
        c = ws.cell(row=total_row, column=col_idx)
        c.fill = total_fill
        c.border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                          top=Side(style='medium', color='000000'), bottom=Side(style='double', color='000000'))

    # Signature
    sig_row = total_row + 3
    sig_col = get_column_letter(total_cols - 2)
    ws.merge_cells(f"{sig_col}{sig_row}:{last_col_let}{sig_row}")
    ws[f"{sig_col}{sig_row}"] = f"({team_lead})" if team_lead else "(Team Leader)"
    ws[f"{sig_col}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+1}:{last_col_let}{sig_row+1}")
    ws[f"{sig_col}{sig_row+1}"] = f"Enforcement Cell, TPSODL, {circle_up} Circle"
    ws[f"{sig_col}{sig_row+1}"].font = font_cell
    ws[f"{sig_col}{sig_row+1}"].alignment = align_center

    ws.column_dimensions["A"].width = 13
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 32
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 12
    ws.column_dimensions["H"].width = 13
    ws.column_dimensions["I"].width = 15

    # SPREADSHEET PROTECTION: Read-only & Tamper-proof
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =========================================================================
# 4. TEAM PERFORMANCE REPORT (EXCEL)
# =========================================================================
def build_team_performance_excel(circle_name: str, year: int, month: int, performance_rows: List[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()
    ws.title = f"Performance - {calendar.month_abbr[month]} {year}"
    ws.views.sheetView[0].showGridLines = True

    agency = get_agency_header(circle_name)
    total_cols = 8
    last_col_let = get_column_letter(total_cols)

    font_comp = Font(name="Calibri", size=13, bold=True)
    font_addr = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True)
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_cell = Font(name="Calibri", size=9)
    font_cell_bold = Font(name="Calibri", size=9, bold=True)

    thin_border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                         top=Side(style='thin', color='444444'), bottom=Side(style='thin', color='444444'))
    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_comp
    ws["A1"].alignment = align_center

    ws.merge_cells(f"A2:{last_col_let}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_addr
    ws["A2"].alignment = align_center

    ws.merge_cells(f"A3:{last_col_let}3")
    ws["A3"] = f"TEAM-WISE OPERATIONAL PERFORMANCE REPORT - {month_name} {year}"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    ws.merge_cells(f"A4:{last_col_let}4")
    ws["A4"] = f"Enforcement & Vigilance Cell | Circle: {circle_up}"
    ws["A4"].font = font_meta
    ws["A4"].alignment = align_center
    ws["A4"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        "Date", "Team Name", "Mode of Team Operation",
        "Load Booked (KW)", "Amount Coll. (Rs.)", "No. of DC",
        "KM Run (Day)", "Emp Present"
    ]
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_idx, value=h_text)
        cell.font = font_th
        cell.alignment = align_center
        cell.fill = header_fill
        cell.border = thin_border

    current_row = 6
    for idx, r in enumerate(performance_rows, 1):
        raw_d = r.get('date', '')
        if hasattr(raw_d, "strftime"):
            d_str = raw_d.strftime("%d-%m-%Y")
        else:
            d_str = str(raw_d)
            try:
                d_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
            except Exception:
                pass

        mode = r.get('operation_mode') or 'Operated Independently'
        if mode == "Merged" and r.get('merged_with_team'):
            mode = f"Merged with {r.get('merged_with_team')}"
        elif not r.get('team_leader_present', True):
            mode += " (TL Absent)"

        ws.cell(row=current_row, column=1, value=d_str).alignment = align_center
        ws.cell(row=current_row, column=2, value=r.get('team_name', '')).alignment = align_left
        ws.cell(row=current_row, column=3, value=mode).alignment = align_left

        c_load = ws.cell(row=current_row, column=4, value=float(r.get('load_booked', 0.0) or 0.0))
        c_load.alignment = align_center
        c_load.number_format = "0.00"

        c_amt = ws.cell(row=current_row, column=5, value=float(r.get('amount_collected', 0.0) or 0.0))
        c_amt.alignment = align_right
        c_amt.number_format = "#,##0.00"

        c_dc = ws.cell(row=current_row, column=6, value=int(r.get('number_of_dc', 0) or 0))
        c_dc.alignment = align_center
        c_dc.number_format = "#,##0"

        c_km = ws.cell(row=current_row, column=7, value=int(r.get('total_km', 0) or 0))
        c_km.alignment = align_center
        c_km.number_format = "#,##0"

        c_emp = ws.cell(row=current_row, column=8, value=int(r.get('emp_present_count', 0) or 0))
        c_emp.alignment = align_center
        c_emp.font = font_cell_bold

        for col_idx in range(1, total_cols + 1):
            c = ws.cell(row=current_row, column=col_idx)
            c.border = thin_border
            if not c.font.bold:
                c.font = font_cell
            if idx % 2 == 0:
                c.fill = zebra_fill
        current_row += 1

    total_row = current_row
    ws.merge_cells(f"A{total_row}:C{total_row}")
    t_label = ws[f"A{total_row}"]
    t_label.value = "TOTAL"
    t_label.font = font_cell_bold
    t_label.alignment = align_right

    data_start = 6
    data_end = total_row - 1 if performance_rows else 6

    ws.cell(row=total_row, column=4, value=f"=SUM(D{data_start}:D{data_end})" if performance_rows else 0).number_format = "0.00"
    ws.cell(row=total_row, column=5, value=f"=SUM(E{data_start}:E{data_end})" if performance_rows else 0).number_format = "#,##0.00"
    ws.cell(row=total_row, column=6, value=f"=SUM(F{data_start}:F{data_end})" if performance_rows else 0).number_format = "#,##0"
    ws.cell(row=total_row, column=7, value=f"=SUM(G{data_start}:G{data_end})" if performance_rows else 0).number_format = "#,##0"
    ws.cell(row=total_row, column=8, value="-").alignment = align_center

    for c_i in [4, 5, 6, 7]:
        ws.cell(row=total_row, column=c_i).alignment = align_center if c_i != 5 else align_right
        ws.cell(row=total_row, column=c_i).font = font_cell_bold

    for col_idx in range(1, total_cols + 1):
        c = ws.cell(row=total_row, column=col_idx)
        c.fill = total_fill
        c.border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                          top=Side(style='medium', color='000000'), bottom=Side(style='double', color='000000'))

    # Signature
    sig_row = total_row + 3
    sig_col = get_column_letter(total_cols - 2)
    ws.merge_cells(f"{sig_col}{sig_row}:{last_col_let}{sig_row}")
    ws[f"{sig_col}{sig_row}"] = "Executive Engineer (Elect.)"
    ws[f"{sig_col}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+1}:{last_col_let}{sig_row+1}")
    ws[f"{sig_col}{sig_row+1}"] = "Enforcement & Vigilance Cell"
    ws[f"{sig_col}{sig_row+1}"].font = font_cell
    ws[f"{sig_col}{sig_row+1}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+2}:{last_col_let}{sig_row+2}")
    ws[f"{sig_col}{sig_row+2}"] = f"TPSODL, {circle_up} Circle"
    ws[f"{sig_col}{sig_row+2}"].font = font_cell
    ws[f"{sig_col}{sig_row+2}"].alignment = align_center

    ws.column_dimensions["A"].width = 13
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 28
    ws.column_dimensions["D"].width = 17
    ws.column_dimensions["E"].width = 19
    ws.column_dimensions["F"].width = 13
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 14

    # SPREADSHEET PROTECTION: Read-only & Tamper-proof
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =========================================================================
# 5. FIELD COLLECTION REGISTER (EXCEL)
# =========================================================================
def build_collection_excel(circle_name: str, year: int, month: int, records: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    month_name = calendar.month_name[month].upper()
    circle_up = circle_name.upper()
    ws.title = f"Collections - {calendar.month_abbr[month]} {year}"
    ws.views.sheetView[0].showGridLines = True

    agency = get_agency_header(circle_name)
    total_cols = 10
    last_col_let = get_column_letter(total_cols)

    font_comp = Font(name="Calibri", size=13, bold=True)
    font_addr = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True)
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_cell = Font(name="Calibri", size=9)
    font_cell_bold = Font(name="Calibri", size=9, bold=True)

    thin_border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                         top=Side(style='thin', color='444444'), bottom=Side(style='thin', color='444444'))
    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_comp
    ws["A1"].alignment = align_center

    ws.merge_cells(f"A2:{last_col_let}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_addr
    ws["A2"].alignment = align_center

    ws.merge_cells(f"A3:{last_col_let}3")
    ws["A3"] = f"VIGILANCE ENFORCEMENT CELL, {circle_up} CIRCLE"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    ws.merge_cells(f"A4:{last_col_let}4")
    ws["A4"] = f"FIELD COLLECTION REGISTER - {month_name} {year}"
    ws["A4"].font = font_title
    ws["A4"].alignment = align_center

    ws.merge_cells(f"A5:{last_col_let}5")
    ws["A5"] = f"Circle: {circle_up} | Period: {month_name} {year}"
    ws["A5"].font = font_meta
    ws["A5"].alignment = align_center
    ws["A5"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    headers = [
        "Sl No.", "Payment Date", "Division", "Subdivision", "Section",
        "MR No.", "VCR No.", "Collecting Officer", "Team Name", "Amount Paid (Rs.)"
    ]
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_idx, value=h_text)
        cell.font = font_th
        cell.alignment = align_center
        cell.fill = header_fill
        cell.border = thin_border

    current_row = 7
    for idx, r in enumerate(records or [], 1):
        raw_d = r.payment_date if hasattr(r, "payment_date") else r.get("payment_date")
        if hasattr(raw_d, "strftime"):
            d_str = raw_d.strftime("%d-%m-%Y")
        else:
            d_str = str(raw_d or "-")

        div = getattr(r, "division", None) if hasattr(r, "division") else r.get("division")
        subdiv = getattr(r, "subdivision", None) if hasattr(r, "subdivision") else r.get("subdivision")
        sec = getattr(r, "section", None) if hasattr(r, "section") else r.get("section")
        mr = getattr(r, "mr_no", None) if hasattr(r, "mr_no") else r.get("mr_no")
        vcr = getattr(r, "vcr_no", None) if hasattr(r, "vcr_no") else r.get("vcr_no")
        officer = getattr(r, "collecting_officer", None) if hasattr(r, "collecting_officer") else r.get("collecting_officer")
        tm_name = getattr(r, "team_name", None) if hasattr(r, "team_name") else r.get("team_name")
        amt = float(getattr(r, "amount_paid", 0.0) if hasattr(r, "amount_paid") else r.get("amount_paid", 0.0) or 0.0)

        ws.cell(row=current_row, column=1, value=idx).alignment = align_center
        ws.cell(row=current_row, column=2, value=d_str).alignment = align_center
        ws.cell(row=current_row, column=3, value=div or "-").alignment = align_left
        ws.cell(row=current_row, column=4, value=subdiv or "-").alignment = align_left
        ws.cell(row=current_row, column=5, value=sec or "-").alignment = align_left
        ws.cell(row=current_row, column=6, value=mr or "-").alignment = align_center
        ws.cell(row=current_row, column=7, value=vcr or "-").alignment = align_center
        ws.cell(row=current_row, column=8, value=officer or "-").alignment = align_left
        ws.cell(row=current_row, column=9, value=tm_name or "-").alignment = align_left
        
        c_amt = ws.cell(row=current_row, column=10, value=amt)
        c_amt.alignment = align_right
        c_amt.number_format = "#,##0.00"

        for col_idx in range(1, total_cols + 1):
            c = ws.cell(row=current_row, column=col_idx)
            c.border = thin_border
            if not c.font.bold:
                c.font = font_cell
            if idx % 2 == 0:
                c.fill = zebra_fill
        current_row += 1

    total_row = current_row
    ws.merge_cells(f"A{total_row}:I{total_row}")
    t_label = ws[f"A{total_row}"]
    t_label.value = "TOTAL COLLECTIONS"
    t_label.font = font_cell_bold
    t_label.alignment = align_right

    data_start = 7
    data_end = total_row - 1 if records else 7
    c_tot = ws.cell(row=total_row, column=10, value=f"=SUM(J{data_start}:J{data_end})" if records else 0)
    c_tot.alignment = align_right
    c_tot.font = font_cell_bold
    c_tot.number_format = "#,##0.00"

    for col_idx in range(1, total_cols + 1):
        c = ws.cell(row=total_row, column=col_idx)
        c.fill = total_fill
        c.border = Border(left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
                          top=Side(style='medium', color='000000'), bottom=Side(style='double', color='000000'))

    # Signature
    sig_row = total_row + 3
    sig_col = get_column_letter(total_cols - 2)
    ws.merge_cells(f"{sig_col}{sig_row}:{last_col_let}{sig_row}")
    ws[f"{sig_col}{sig_row}"] = "Executive Engineer (Elect.)"
    ws[f"{sig_col}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+1}:{last_col_let}{sig_row+1}")
    ws[f"{sig_col}{sig_row+1}"] = "Enforcement & Vigilance Cell"
    ws[f"{sig_col}{sig_row+1}"].font = font_cell
    ws[f"{sig_col}{sig_row+1}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+2}:{last_col_let}{sig_row+2}")
    ws[f"{sig_col}{sig_row+2}"] = f"TPSODL, {circle_up} Circle"
    ws[f"{sig_col}{sig_row+2}"].font = font_cell
    ws[f"{sig_col}{sig_row+2}"].alignment = align_center

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 16
    ws.column_dimensions["G"].width = 16
    ws.column_dimensions["H"].width = 20
    ws.column_dimensions["I"].width = 20
    ws.column_dimensions["J"].width = 18

    # SPREADSHEET PROTECTION: Read-only & Tamper-proof
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =========================================================================
# 6. ALL LOAD BOOKINGS REGISTER (EXCEL)
# =========================================================================
def build_load_booking_excel(
    bookings: list,
    circle: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None
) -> bytes:
    """
    Exports a structured .xlsx register for all load bookings with:
    - Sl No., Booking Date, Page No, Punching Officer, Team, Circle, Division, Subdivision, Section, PIN Code, Theft Category, Booked Load (kW), Status.
    - Auto-calculated =SUM() for Booked Load (kW) column.
    - Full worksheet protection (read-only, password locked with 'TPSODL@MIS').
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Load Bookings Register"
    ws.views.sheetView[0].showGridLines = True

    circle_up = (circle or "ALL CIRCLES").strip().upper()
    agency = get_agency_header(circle if circle and circle != "ALL" else None)

    total_cols = 13
    last_col_let = get_column_letter(total_cols)

    font_company = Font(name="Calibri", size=13, bold=True, color="000000")
    font_address = Font(name="Calibri", size=9, bold=False, color="333333")
    font_title = Font(name="Calibri", size=11, bold=True, color="000000")
    font_sub = Font(name="Calibri", size=10, bold=True, color="1E3A8A")
    font_meta = Font(name="Calibri", size=9, bold=True, color="1E293B")
    
    font_th = Font(name="Calibri", size=9, bold=True, color="000000")
    font_cell = Font(name="Calibri", size=9, bold=False, color="000000")
    font_cell_bold = Font(name="Calibri", size=9, bold=True, color="000000")
    font_theft = Font(name="Calibri", size=9, bold=True, color="B91C1C")

    thin_border_side = Side(style='thin', color='444444')
    thick_border_side = Side(style='medium', color='000000')
    double_border_side = Side(style='double', color='000000')

    grid_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    total_border = Border(left=thin_border_side, right=thin_border_side, top=thick_border_side, bottom=double_border_side)

    header_fill = PatternFill(start_color="D0D0D0", end_color="D0D0D0", fill_type="solid")
    total_fill = PatternFill(start_color="E2E2E2", end_color="E2E2E2", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Row 1: Company Header
    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = agency["name"]
    ws["A1"].font = font_company
    ws["A1"].alignment = align_center

    # Row 2: Office Address
    ws.merge_cells(f"A2:{last_col_let}2")
    ws["A2"] = agency["address"]
    ws["A2"].font = font_address
    ws["A2"].alignment = align_center

    # Row 3: TPSODL Title
    ws.merge_cells(f"A3:{last_col_let}3")
    ws["A3"] = "TP SOUTHERN ODISHA DISTRIBUTION LIMITED (TPSODL)"
    ws["A3"].font = font_title
    ws["A3"].alignment = align_center

    # Row 4: Register Title
    ws.merge_cells(f"A4:{last_col_let}4")
    ws["A4"] = "CONSOLIDATED UNAUTHORIZED LOAD BOOKING REGISTER"
    ws["A4"].font = font_sub
    ws["A4"].alignment = align_center

    # Row 5: Metadata
    ws.merge_cells(f"A5:{last_col_let}5")
    date_str = f"Date Range: {from_date} to {to_date}" if from_date and to_date else "All Dates"
    ws["A5"] = f"Circle Scope: {circle_up}   |   {date_str}   |   Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["A5"].font = font_meta
    ws["A5"].alignment = align_center

    # Row 6: Column Headers
    headers = [
        "Sl No.",
        "Booking Date",
        "Page No",
        "Punching Officer",
        "Team / Squad",
        "Circle",
        "Division",
        "Subdivision",
        "Section",
        "PIN Code",
        "Theft Category",
        "Booked Load (kW)",
        "Status"
    ]

    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=6, column=col_idx, value=h_text)
        cell.font = font_th
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = grid_border

    start_data_row = 7
    cur_row = start_data_row

    for idx, b in enumerate(bookings, start=1):
        ws.cell(row=cur_row, column=1, value=idx).alignment = align_center
        ws.cell(row=cur_row, column=2, value=str(b.get("booking_date", ""))).alignment = align_center
        ws.cell(row=cur_row, column=3, value=str(b.get("page_no") or "-")).alignment = align_center
        ws.cell(row=cur_row, column=4, value=str(b.get("punch_emp") or "-")).alignment = align_left
        ws.cell(row=cur_row, column=5, value=str(b.get("team_name") or "Unassigned")).alignment = align_left
        ws.cell(row=cur_row, column=6, value=str(b.get("circle") or "-")).alignment = align_center
        ws.cell(row=cur_row, column=7, value=str(b.get("division") or "-")).alignment = align_left
        ws.cell(row=cur_row, column=8, value=str(b.get("subdivision") or "-")).alignment = align_left
        ws.cell(row=cur_row, column=9, value=str(b.get("section") or "-")).alignment = align_left
        ws.cell(row=cur_row, column=10, value=str(b.get("pincode") or "-")).alignment = align_center
        
        theft_c = ws.cell(row=cur_row, column=11, value=str(b.get("theft_type") or "-"))
        theft_c.alignment = align_center
        theft_c.font = font_theft
        
        load_val = float(b.get("booked_load") or 0.0)
        load_c = ws.cell(row=cur_row, column=12, value=load_val)
        load_c.alignment = align_right
        load_c.font = font_cell_bold
        load_c.number_format = "#,##0.00"

        ws.cell(row=cur_row, column=13, value=str(b.get("status") or "PROCESSED")).alignment = align_center

        row_fill = zebra_fill if idx % 2 == 0 else PatternFill(fill_type=None)
        for c_idx in range(1, total_cols + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.border = grid_border
            if c_idx != 11 and c_idx != 12:
                cell.font = font_cell
            if row_fill.fill_type:
                cell.fill = row_fill

        cur_row += 1

    end_data_row = cur_row - 1

    # Total Row with =SUM() Formula
    total_row = cur_row
    ws.merge_cells(f"A{total_row}:K{total_row}")
    ws[f"A{total_row}"] = "TOTAL BOOKED LOAD (kW):"
    ws[f"A{total_row}"].font = font_cell_bold
    ws[f"A{total_row}"].alignment = align_right
    ws[f"A{total_row}"].fill = total_fill

    sum_cell = ws.cell(row=total_row, column=12)
    if end_data_row >= start_data_row:
        sum_cell.value = f"=SUM(L{start_data_row}:L{end_data_row})"
    else:
        sum_cell.value = 0.0
    sum_cell.font = font_cell_bold
    sum_cell.alignment = align_right
    sum_cell.fill = total_fill
    sum_cell.number_format = "#,##0.00"

    ws.cell(row=total_row, column=13, value="").fill = total_fill

    for c_idx in range(1, total_cols + 1):
        ws.cell(row=total_row, column=c_idx).border = total_border

    # Signatures
    sig_row = total_row + 4
    ws.cell(row=sig_row, column=2, value="Prepared By (Enforcement Officer)").font = font_cell_bold
    ws.cell(row=sig_row, column=2).alignment = align_center

    sig_col = "J"
    ws.merge_cells(f"{sig_col}{sig_row}:{last_col_let}{sig_row}")
    ws[f"{sig_col}{sig_row}"] = "Executive Engineer (Elect.) / Authorized Signatory"
    ws[f"{sig_col}{sig_row}"].font = font_cell_bold
    ws[f"{sig_col}{sig_row}"].alignment = align_center

    ws.merge_cells(f"{sig_col}{sig_row+1}:{last_col_let}{sig_row+1}")
    ws[f"{sig_col}{sig_row+1}"] = f"TPSODL Enforcement Cell, {circle_up}"
    ws[f"{sig_col}{sig_row+1}"].font = font_cell
    ws[f"{sig_col}{sig_row+1}"].alignment = align_center

    # Column widths
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 22
    ws.column_dimensions["F"].width = 16
    ws.column_dimensions["G"].width = 20
    ws.column_dimensions["H"].width = 20
    ws.column_dimensions["I"].width = 20
    ws.column_dimensions["J"].width = 12
    ws.column_dimensions["K"].width = 16
    ws.column_dimensions["L"].width = 18
    ws.column_dimensions["M"].width = 14

    # Enforce Read-Only Worksheet Protection
    apply_sheet_protection(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()



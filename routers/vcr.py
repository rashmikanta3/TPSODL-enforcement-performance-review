import io
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from database import get_db
from models import VCRMaster, User, get_assigned_circles, is_circle_authorized
from auth import get_current_actor, verify_write_permission

router = APIRouter()

@router.get("/template")
def download_vcr_template():
    """Generates and streams an official Excel (.xlsx) template for VCR Master bulk ingestion."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VCR_Master_Template"

    headers = [
        "VCR Number",
        "Consumer Name",
        "Consumer Address",
        "Circle",
        "Division",
        "Section",
        "Provisional Bill Date"
    ]
    ws.append(headers)

    # Style header row
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    # Sample reference data rows
    sample_rows = [
        ["VCR-2026-001", "Ramesh Chandra Sahu", "Main Road, Aska", "ASKA", "AED ASKA-I", "ESO ASKA-1", "2026-11-01"],
        ["VCR-2026-002", "Binod Kumar Jena", "Bada Bazar, Berhampur", "BERHAMPUR", "GANJAM NORTH", "ESO CHATRAPUR-I", "2026-11-02"],
        ["VCR-2026-003", "Kailash Patra", "Gandhi Nagar, Berhampur", "BERHAMPUR CITY", "BERHAMPUR-II", "ESO GANDHINAGAR", "2026-11-03"]
    ]
    for row in sample_rows:
        ws.append(row)

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=VCR_Master_Bulk_Template.xlsx"}
    )

@router.post("/bulk-upload")
async def bulk_upload_vcr_excel(
    file: UploadFile = File(...),
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """
    Ingests VCR master records in bulk from an uploaded Excel (.xlsx/.xlsm) spreadsheet.
    Enforces strict deduplication and circle scoping for Sub-Admin.
    """
    if current_user:
        verify_write_permission(current_user)

    if not file.filename.lower().endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx / .xlsm) files are supported")

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel workbook: {str(e)}")

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return {
            "success": False,
            "total_rows": 0,
            "inserted_count": 0,
            "skipped_duplicates": 0,
            "errors": [{"row": 0, "vcr": "N/A", "reason": "Spreadsheet contains no data rows"}]
        }

    # Header index mapping
    raw_header = [str(col).strip().lower().replace(" ", "_").replace(".", "").replace("-", "_") if col else "" for col in rows[0]]
    col_map = {}
    for idx, h in enumerate(raw_header):
        if "vcr" in h:
            col_map["vcr_number"] = idx
        elif "consumer_name" in h or "name" in h:
            col_map["consumer_name"] = idx
        elif "address" in h:
            col_map["consumer_address"] = idx
        elif "circle" in h:
            col_map["circle"] = idx
        elif "subdivision" in h or "sub_div" in h:
            col_map["subdivision"] = idx
        elif "division" in h or "div" in h:
            col_map["division"] = idx
        elif "section" in h or "sec" in h:
            col_map["section"] = idx
        elif "date" in h or "bill" in h:
            col_map["provisional_bill_date"] = idx

    def get_val(r, key, default_idx):
        idx = col_map.get(key, default_idx)
        return r[idx] if len(r) > idx else None

    # Load existing VCRs in DB for fast in-memory check
    file_vcrs = [
        str(get_val(r, "vcr_number", 0)).strip().upper()
        for r in rows[1:] if r and get_val(r, "vcr_number", 0)
    ]
    existing_db_vcrs = set()
    if file_vcrs:
        for i in range(0, len(file_vcrs), 1000):
            chunk = file_vcrs[i:i + 1000]
            existing_records = db.query(VCRMaster.vcr_number).filter(VCRMaster.vcr_number.in_(chunk)).all()
            for rec in existing_records:
                existing_db_vcrs.add(rec[0].strip().upper())

    seen_sheet_vcrs = set()
    inserted_records = []
    skipped_duplicates = 0
    errors = []
    total_data_rows = 0

    for idx, row in enumerate(rows[1:], start=2):
        if not row or not any(row):
            continue
        total_data_rows += 1

        vcr_raw = get_val(row, "vcr_number", 0)
        vcr_num = str(vcr_raw).strip() if vcr_raw is not None else ""
        if not vcr_num:
            errors.append({"row": idx, "vcr": "MISSING", "reason": "Mandatory column 'VCR Number' is empty"})
            continue

        vcr_key = vcr_num.upper()

        # Deduplication check
        if vcr_key in seen_sheet_vcrs or vcr_key in existing_db_vcrs:
            skipped_duplicates += 1
            continue

        # Circle
        circ_raw = get_val(row, "circle", 3)
        circ = str(circ_raw).strip().upper() if circ_raw else "BERHAMPUR"
        if circ == "CITY":
            circ = "BERHAMPUR CITY"

        # Circle validation for Sub-Admin
        if current_user and current_user.role == "SUB_ADMIN":
            if not is_circle_authorized(current_user, circ):
                raise HTTPException(
                    status_code=403,
                    detail=f"Unauthorized: You do not have permissions for circle: {circ}"
                )

        # Consumer Name & Address
        cons_name_raw = get_val(row, "consumer_name", 1)
        cons_name = str(cons_name_raw).strip() if cons_name_raw else "Unknown Consumer"

        cons_addr_raw = get_val(row, "consumer_address", 2)
        cons_addr = str(cons_addr_raw).strip() if cons_addr_raw else None

        # Division & Section
        div_raw = get_val(row, "division", 4)
        div = str(div_raw).strip() if div_raw else None

        subdiv_raw = get_val(row, "subdivision", 999)
        subdiv = str(subdiv_raw).strip() if subdiv_raw else None

        sec_raw = get_val(row, "section", 5)
        sec = str(sec_raw).strip() if sec_raw else None

        # Bill Date
        b_date_raw = get_val(row, "provisional_bill_date", 6)
        b_date = None
        if isinstance(b_date_raw, datetime):
            b_date = b_date_raw.date()
        elif isinstance(b_date_raw, date):
            b_date = b_date_raw
        elif b_date_raw:
            try:
                b_date = datetime.strptime(str(b_date_raw).strip()[:10], "%Y-%m-%d").date()
            except Exception:
                b_date = None

        new_vcr = VCRMaster(
            vcr_number=vcr_num,
            consumer_name=cons_name,
            consumer_address=cons_addr,
            circle=circ,
            division=div,
            subdivision=subdiv,
            section=sec,
            provisional_bill_date=b_date
        )

        inserted_records.append(new_vcr)
        seen_sheet_vcrs.add(vcr_key)
        existing_db_vcrs.add(vcr_key)

    if inserted_records:
        db.add_all(inserted_records)
        db.commit()

    return {
        "success": True,
        "total_rows": total_data_rows,
        "inserted_count": len(inserted_records),
        "skipped_duplicates": skipped_duplicates,
        "errors": errors[:50]
    }

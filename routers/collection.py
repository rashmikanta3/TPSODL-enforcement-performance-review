import io
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
import openpyxl
from database import get_db
from models import Collection, Team, User, get_assigned_circles, is_circle_authorized
from auth import get_current_actor, verify_write_permission

router = APIRouter()

@router.get("/stats")
def get_collection_stats(
    circle: Optional[str] = "ALL",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """
    Returns KPI metrics matching the user snippet:
    - Total Amount Collected (INR)
    - Total Money Receipts (MR Count)
    Scopes query to authorized circles for Sub-Admin.
    """
    q = db.query(
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("total_amt"),
        func.count(Collection.id).label("total_cnt")
    )

    if current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")

        if circle and circle.strip().upper() != "ALL":
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(status_code=403, detail=f"Unauthorized: You do not have permissions for circle: {circle}")
            if c_up in ("CITY", "BERHAMPUR CITY"):
                q = q.filter(Collection.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                q = q.filter(Collection.circle == c_up)
        else:
            q = q.filter(Collection.circle.in_(expanded))
    elif circle and circle.strip().upper() != "ALL":
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(Collection.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(Collection.circle == c_up)

    if from_date:
        q = q.filter(Collection.payment_date >= from_date)
    if to_date:
        q = q.filter(Collection.payment_date <= to_date)

    res = q.one()
    return {
        "total_amount": round(float(res.total_amt), 2),
        "total_count": int(res.total_cnt),
        "circle": circle or "ALL",
        "from_date": str(from_date) if from_date else None,
        "to_date": str(to_date) if to_date else None
    }

@router.post("/upload")
@router.post("/bulk-upload")
async def upload_collection_excel(
    file: UploadFile = File(...),
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    if not current_user or current_user.role not in ["ADMIN", "SUB_ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Only Circle Sub-Admins and System Admins are authorized to upload VCR or Collection data."
        )
    verify_write_permission(current_user)

    if not file.filename.lower().endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx) files are supported")
    
    contents = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return {
            "success": False,
            "total_rows": 0,
            "updated_count": 0,
            "failed_count": 0,
            "errors": [{"row": 0, "mr": "N/A", "reason": "File is empty or contains only headers"}]
        }

    # Inspect Header row to map columns flexibly
    header = [str(col).strip().lower().replace(" ", "_").replace(".", "") if col else "" for col in rows[0]]
    col_map = {}
    for idx, h in enumerate(header):
        if "circle" in h: col_map["circle"] = idx
        elif "subdivision" in h or "sub_div" in h: col_map["subdivision"] = idx
        elif "division" in h or "div" in h: col_map["division"] = idx
        elif "section" in h or "sec" in h: col_map["section"] = idx
        elif "mr" in h: col_map["mr_number"] = idx
        elif "vcr" in h: col_map["vcr_number"] = idx
        elif "date" in h or "payment" in h: col_map["payment_date"] = idx
        elif "amount" in h or "paid" in h: col_map["amount_paid"] = idx
        elif "officer" in h or "collected_by" in h or "name_of_collecting" in h: col_map["collected_by"] = idx
        elif "team" in h or "squad" in h: col_map["team_name"] = idx

    def get_val(r, key, default_idx):
        idx = col_map.get(key, default_idx)
        return r[idx] if len(r) > idx else None

    # Collect sheet MR numbers for bulk deduplication
    mr_idx = col_map.get("mr_number", 4)
    sheet_mrs = [str(r[mr_idx]).strip().upper() for r in rows[1:] if r and len(r) > mr_idx and r[mr_idx]]
    existing_mrs = set()
    if sheet_mrs:
        for i in range(0, len(sheet_mrs), 1000):
            chunk = sheet_mrs[i:i+1000]
            for (m,) in db.query(Collection.mr_number).filter(Collection.mr_number.in_(chunk)).all():
                if m:
                    existing_mrs.add(m.strip().upper())

    seen_mrs_in_file = set()
    total_data_rows = 0
    updated_count = 0
    skipped_duplicates = 0
    errors = []
    new_records = []

    for idx, row in enumerate(rows[1:], start=2):
        if not row or not any(row):
            continue
        total_data_rows += 1

        try:
            mr_raw = get_val(row, "mr_number", 4)
            mr_num = str(mr_raw).strip() if mr_raw is not None else ""
            if not mr_num:
                errors.append({"row": idx, "mr": "MISSING", "reason": "MR Number is missing"})
                continue

            mr_key = mr_num.upper()

            # Strict Deduplication: DB + in-file check
            if mr_key in seen_mrs_in_file or mr_key in existing_mrs:
                skipped_duplicates += 1
                errors.append({"row": idx, "mr": mr_num, "reason": f"MR Number '{mr_num}' already exists in database or repeated in sheet (Duplicate)"})
                continue

            circle_raw = get_val(row, "circle", 0)
            circle = str(circle_raw).strip().upper() if circle_raw else "BERHAMPUR"
            if circle == "CITY":
                circle = "BERHAMPUR CITY"

            # Enforce Sub-Admin multiple circle authorization
            if current_user and current_user.role == "SUB_ADMIN":
                if not is_circle_authorized(current_user, circle):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Unauthorized: You do not have permissions for circle: {circle}"
                    )

            # Date
            p_date_raw = get_val(row, "payment_date", 6)
            if isinstance(p_date_raw, datetime):
                p_date = p_date_raw.date()
            elif isinstance(p_date_raw, date):
                p_date = p_date_raw
            elif p_date_raw:
                p_date = datetime.strptime(str(p_date_raw).strip()[:10], "%Y-%m-%d").date()
            else:
                p_date = date.today()

            div_raw = get_val(row, "division", 1)
            div = str(div_raw).strip() if div_raw else None

            subdiv_raw = get_val(row, "subdivision", 2)
            subdiv = str(subdiv_raw).strip() if subdiv_raw else None

            sec_raw = get_val(row, "section", 3)
            sec = str(sec_raw).strip() if sec_raw else None

            vcr_raw = get_val(row, "vcr_number", 5)
            vcr_num = str(vcr_raw).strip() if vcr_raw else ""

            amt_raw = get_val(row, "amount_paid", 7)
            try:
                amount = float(amt_raw) if amt_raw is not None else 0.0
            except ValueError:
                amount = 0.0

            collected_by_raw = get_val(row, "collected_by", 8)
            collected_by = str(collected_by_raw).strip() if collected_by_raw else None

            team_name_raw = get_val(row, "team_name", 9)
            team_name = str(team_name_raw).strip() if team_name_raw else "GENERAL SQUAD"

            coll = Collection(
                payment_date=p_date,
                mr_number=mr_num,
                vcr_number=vcr_num,
                amount_paid=amount,
                collected_by_name=collected_by,
                team_name=team_name,
                circle=circle,
                division=div,
                subdivision=subdiv,
                section=sec
            )
            new_records.append(coll)
            seen_mrs_in_file.add(mr_key)
            updated_count += 1
        except HTTPException:
            raise
        except Exception as ex:
            errors.append({"row": idx, "mr": str(get_val(row, "mr_number", 4) or "N/A"), "reason": str(ex)})

    if new_records:
        db.bulk_save_objects(new_records)
        db.commit()

    return {
        "success": True,
        "total_rows": total_data_rows,
        "updated_count": updated_count,
        "skipped_duplicates": skipped_duplicates,
        "failed_count": len(errors),
        "errors": errors[:50],
        "message": f"Processed {total_data_rows} rows: {updated_count} collections inserted, {skipped_duplicates} duplicate MRs skipped."
    }

@router.get("/template")
def download_sample_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Collection Register"
    
    headers = [
        "Circle", "Division", "Subdivision", "Section",
        "MR_No", "VCR_No", "Date_of_Payment", "Amount_Paid",
        "Name_of_Collecting_Officer", "Team_Name"
    ]
    ws.append(headers)
    ws.append([
        "BERHAMPUR", "BED-1 (Berhampur)", "Town Sub-Division", "Hillpatna Section",
        "MR-100234", "VCR-2026-001", "2026-11-01", 15400.0,
        "R. K. Mohapatra", "SQUAD BERHAMPUR-1"
    ])
    ws.append([
        "JEYPORE", "JED (Jeypore Electric Division)", "Jeypore Town Sub-Division", "Parabeda Section",
        "MR-100235", "2026-11-01", 22500.0,
        "A. K. Tripathy", "SQUAD JEYPORE-1"
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=TPSODL_Collection_Register_Template.xlsx"}
    )

@router.get("/recent")
def list_collections(
    circle: Optional[str] = None,
    team_name: Optional[str] = None,
    limit: int = 30,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    q = db.query(Collection)
    if current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")

        if circle and circle.strip().upper() != "ALL":
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(status_code=403, detail=f"Unauthorized: You do not have permissions for circle: {circle}")
            if c_up in ("CITY", "BERHAMPUR CITY"):
                q = q.filter(Collection.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                q = q.filter(Collection.circle == c_up)
        else:
            q = q.filter(Collection.circle.in_(expanded))
    elif circle and circle.strip().upper() != "ALL":
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(Collection.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(Collection.circle == c_up)

    if team_name:
        q = q.filter(Collection.team_name == team_name.strip())
    results = q.order_by(Collection.payment_date.desc(), Collection.id.desc()).limit(limit).all()
    return [
        {
            "id": c.id,
            "payment_date": str(c.payment_date),
            "mr_number": c.mr_number,
            "vcr_number": c.vcr_number or "-",
            "amount_paid": c.amount_paid,
            "collected_by": c.collected_by_emp_id or "-",
            "team_name": c.team_name,
            "circle": c.circle,
            "division": c.division or "-",
            "subdivision": c.subdivision or "-",
            "section": c.section or "-"
        }
        for c in results
    ]

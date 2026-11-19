import io
from fastapi.responses import Response
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import DisconnectionRecord, VCRMaster, TeamLead, Employee, DailyTeamOperation, Team, User, get_assigned_circles, is_circle_authorized
from schemas import DCPunchRequest
from auth import get_current_actor, verify_write_permission

router = APIRouter()

@router.get("/vcr-lookup")
def lookup_vcr(
    vcr_number: str,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """
    Looks up VCR Master. Circle, Division, Subdivision, Section,
    Consumer Name, and Address are automatically mapped from the VCR.
    Enforces circle scoping for Sub-Admin.
    """
    v = db.query(VCRMaster).filter(VCRMaster.vcr_number == vcr_number.strip()).first()
    if not v:
        raise HTTPException(status_code=404, detail=f"VCR Number '{vcr_number}' not found in VCR Master")

    if current_user and current_user.role == "SUB_ADMIN":
        if not is_circle_authorized(current_user, v.circle):
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized: VCR '{vcr_number}' belongs to circle '{v.circle}', but you are authorized only for: {', '.join(get_assigned_circles(current_user))}"
            )

    return {
        "vcr_number": v.vcr_number,
        "consumer_name": v.consumer_name or "N/A",
        "consumer_address": v.consumer_address or "N/A",
        "circle": v.circle,
        "division": v.division or "",
        "subdivision": getattr(v, "subdivision", "") or "",
        "section": v.section or "",
        "inspection_date": str(v.inspection_date) if v.inspection_date else None
    }

@router.post("/punch")
def punch_dc(
    req: DCPunchRequest,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    vcr = db.query(VCRMaster).filter(VCRMaster.vcr_number == req.vcr_number.strip()).first()
    if not vcr:
        raise HTTPException(status_code=404, detail=f"VCR '{req.vcr_number}' is not registered in VCR Master")

    if current_user:
        verify_write_permission(current_user, vcr.circle)
        if current_user.role == "USER":
            if req.team_id and current_user.team_id and req.team_id != current_user.team_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access Denied: You cannot submit DC records for another squad (Team ID: {req.team_id})."
                )

    tl_code = (req.dc_authority_tl_code or req.dc_authority_emp_id or "").strip()
    if not tl_code:
        raise HTTPException(status_code=400, detail="DC Authority Officer / Team Leader code is required")

    # Find TeamLead
    tl = db.query(TeamLead).filter(func.lower(TeamLead.tl_code) == tl_code.lower()).first()
    if not tl:
        tl = db.query(TeamLead).filter(func.lower(TeamLead.name).like(f"%{tl_code.lower()}%")).first()

    final_team_id = req.team_id
    if not final_team_id and tl:
        # Dynamic attribution: check if TL was designated on daily operations for this date
        op = db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == req.dc_date,
            DailyTeamOperation.daily_tl_id == tl.id,
            DailyTeamOperation.is_team_active == True
        ).first()
        if op:
            final_team_id = op.team_id
        else:
            # Fallback to team where TL is default_tl
            def_team = db.query(Team).filter(Team.default_tl_id == tl.id, Team.is_active == True).first()
            if def_team:
                final_team_id = def_team.id

    if not final_team_id:
        # Check BA Employee fallback if legacy code was passed
        emp = db.query(Employee).filter(func.lower(Employee.emp_code) == tl_code.lower()).first()
        if emp and emp.team_id:
            final_team_id = emp.team_id

    if not final_team_id:
        # Fallback to first active field team in mapped circle
        fallback_team = db.query(Team).filter(
            Team.circle == vcr.circle,
            Team.is_active == True,
            Team.has_vehicle == True,
            Team.is_office_team == False
        ).first()
        final_team_id = fallback_team.id if fallback_team else None

    # Squad user isolation: enforce current_user.team_id
    if current_user and current_user.role == "USER" and current_user.team_id:
        final_team_id = current_user.team_id

    if not final_team_id:
        raise HTTPException(status_code=400, detail="Unable to attribute DC to any squad. Please select an active operating field squad.")

    tm = db.query(Team).filter(Team.id == final_team_id).first()
    if tm and (tm.is_office_team or not tm.has_vehicle):
        raise HTTPException(
            status_code=400,
            detail=f"Operation not permitted: Squad '{tm.name}' is designated as an Office Team (Without Vehicle). Office Teams do not execute field enforcement disconnections."
        )

    if not req.allow_duplicate:
        existing_dc = db.query(DisconnectionRecord).filter(
            func.lower(DisconnectionRecord.vcr_number) == req.vcr_number.strip().lower()
        ).order_by(DisconnectionRecord.id.desc()).first()
        if existing_dc:
            tm = db.query(Team).filter(Team.id == existing_dc.team_id).first()
            tm_name = tm.name if tm else "N/A"
            raise HTTPException(
                status_code=409,
                detail=f"VCR Number '{req.vcr_number}' has already been disconnected on {existing_dc.dc_date} by squad '{tm_name}'. Confirm to proceed."
            )

    rec = DisconnectionRecord(
        dc_date=req.dc_date,
        vcr_number=req.vcr_number.strip(),
        dc_authority_tl_code=tl.tl_code if tl else tl_code,
        dc_authority_emp_id=None,
        team_id=final_team_id,
        amount_pending=req.amount_pending,
        remarks=req.remarks.strip() if req.remarks else None,
        is_locked=True
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    tm = db.query(Team).filter(Team.id == final_team_id).first()
    tm_name = tm.name if tm else "N/A"

    return {
        "success": True,
        "id": rec.id,
        "team_id": final_team_id,
        "team_name": tm_name,
        "circle": vcr.circle,
        "message": f"Disconnection record for VCR '{req.vcr_number}' saved and attributed to {tm_name} ({vcr.circle})!"
    }

@router.get("/recent")
def get_recent_dc(
    circle: Optional[str] = None,
    limit: int = 5,
    vcr_number: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """Returns recent disconnection records with locked status and squad scoping."""
    q = db.query(DisconnectionRecord, VCRMaster.circle.label("vcr_circle")).join(VCRMaster, DisconnectionRecord.vcr_number == VCRMaster.vcr_number)
    if current_user and current_user.role == "USER":
        if current_user.team_id:
            q = q.filter(DisconnectionRecord.team_id == current_user.team_id)
        else:
            q = q.filter(DisconnectionRecord.team_id == -1)
    elif current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")
        if circle and circle.strip().upper() not in ("", "ALL"):
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(status_code=403, detail=f"Unauthorized for circle: {circle}")
            if c_up in ("CITY", "BERHAMPUR CITY"):
                q = q.filter(VCRMaster.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                q = q.filter(VCRMaster.circle == c_up)
        else:
            q = q.filter(VCRMaster.circle.in_(expanded))
    elif circle and circle.strip().upper() not in ("", "ALL"):
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(VCRMaster.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(VCRMaster.circle == c_up)

    if vcr_number and vcr_number.strip():
        q = q.filter(DisconnectionRecord.vcr_number.ilike(f"%{vcr_number.strip()}%"))

    results = q.order_by(DisconnectionRecord.id.desc()).limit(limit).all()
    return [
        {
            "id": d.id,
            "dc_date": str(d.dc_date),
            "vcr_number": d.vcr_number,
            "circle": v_circle,
            "dc_authority_tl_code": d.dc_authority_tl_code,
            "team_id": d.team_id,
            "team_name": d.team.name if d.team else "Unassigned",
            "amount_pending": d.amount_pending,
            "remarks": d.remarks or "",
            "is_locked": bool(getattr(d, "is_locked", True))
        }
        for d, v_circle in results
    ]

@router.delete("/{dc_id}")
def delete_dc(
    dc_id: int,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    rec = db.query(DisconnectionRecord).filter(DisconnectionRecord.id == dc_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Disconnection record not found")
    if not current_user or current_user.role == "USER":
        raise HTTPException(
            status_code=403,
            detail="This record is locked after submission. Contact your Circle Admin or MIS In-Charge to make corrections."
        )
    if current_user.role == "SUB_ADMIN":
        if rec.vcr and not is_circle_authorized(current_user, rec.vcr.circle):
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permissions for this circle.")
        if not current_user.can_edit:
            raise HTTPException(status_code=403, detail="View-only Sub-Admin account cannot delete records.")

    db.delete(rec)
    db.commit()
    return {"success": True, "id": dc_id, "message": "Disconnection record deleted successfully"}

@router.patch("/{dc_id}/toggle-lock")
def toggle_dc_lock(
    dc_id: int,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    if not current_user or current_user.role not in ["ADMIN", "SUB_ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only Admins and Sub-Admins can lock or unlock disconnection records."
        )
    rec = db.query(DisconnectionRecord).filter(DisconnectionRecord.id == dc_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Disconnection record not found")
    if current_user.role == "SUB_ADMIN" and rec.vcr and not is_circle_authorized(current_user, rec.vcr.circle):
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permissions for this circle.")

    rec.is_locked = not bool(getattr(rec, "is_locked", True))
    db.commit()
    db.refresh(rec)
    state_str = "locked" if rec.is_locked else "unlocked"
    return {
        "success": True,
        "id": rec.id,
        "is_locked": bool(rec.is_locked),
        "message": f"Disconnection record {state_str} successfully"
    }



@router.get("/export-excel")
def export_dc_excel(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    circle: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """Exports Disconnection Records within date range to an Excel (.xlsx) file."""
    q = db.query(DisconnectionRecord, VCRMaster).join(VCRMaster, DisconnectionRecord.vcr_number == VCRMaster.vcr_number)
    if current_user and current_user.role == "USER":
        if current_user.team_id:
            q = q.filter(DisconnectionRecord.team_id == current_user.team_id)
        else:
            q = q.filter(DisconnectionRecord.team_id == -1)
    elif current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")
        if circle and circle.strip().upper() not in ("", "ALL"):
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(status_code=403, detail=f"Unauthorized for circle: {circle}")
            if c_up in ("CITY", "BERHAMPUR CITY"):
                q = q.filter(VCRMaster.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                q = q.filter(VCRMaster.circle == c_up)
        else:
            q = q.filter(VCRMaster.circle.in_(expanded))
    elif circle and circle.strip().upper() not in ("", "ALL"):
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(VCRMaster.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(VCRMaster.circle == c_up)

    if start_date:
        q = q.filter(DisconnectionRecord.dc_date >= start_date)
    if end_date:
        q = q.filter(DisconnectionRecord.dc_date <= end_date)

    records = q.order_by(DisconnectionRecord.dc_date.desc(), DisconnectionRecord.id.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Disconnections"

    headers = [
        "ID", "DC Date", "VCR Number", "Circle", "Consumer Name", "Consumer Address",
        "Division", "Section", "Officer / TL Code", "Squad Name",
        "Amount Pending (INR)", "Remarks", "Locked"
    ]
    ws.append(headers)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    for d, v in records:
        ws.append([
            d.id,
            str(d.dc_date) if d.dc_date else "",
            d.vcr_number,
            v.circle if v else "",
            v.consumer_name if v else "",
            v.consumer_address if v else "",
            v.division if v else "",
            v.section if v else "",
            d.dc_authority_tl_code or "",
            d.team.name if d.team else "Unassigned",
            float(d.amount_pending or 0),
            d.remarks or "",
            "YES" if getattr(d, "is_locked", True) else "NO"
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"Disconnections_{date.today().isoformat()}.xlsx"
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

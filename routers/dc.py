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
        "provisional_bill_date": str(v.provisional_bill_date) if v.provisional_bill_date else None
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

    if not final_team_id:
        raise HTTPException(status_code=400, detail="Unable to attribute DC to any squad. Please select an active operating field squad.")

    tm = db.query(Team).filter(Team.id == final_team_id).first()
    if tm and (tm.is_office_team or not tm.has_vehicle):
        raise HTTPException(
            status_code=400,
            detail=f"Operation not permitted: Squad '{tm.name}' is designated as an Office Team (Without Vehicle). Office Teams do not execute field enforcement disconnections."
        )

    rec = DisconnectionRecord(
        dc_date=req.dc_date,
        vcr_number=req.vcr_number.strip(),
        dc_authority_tl_code=tl.tl_code if tl else tl_code,
        dc_authority_emp_id=None,
        team_id=final_team_id,
        amount_pending=req.amount_pending,
        remarks=req.remarks.strip() if req.remarks else None
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

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Team, TeamLead, Employee, DailyTeamOperation, Attendance, User, get_assigned_circles, is_circle_authorized
from schemas import SaveOperationRequest
from auth import get_current_actor, verify_write_permission

router = APIRouter()

@router.get("/teams-by-circle/{circle}")
def get_teams_by_circle(
    circle: str,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    c_up = circle.strip().upper()
    if current_user and current_user.role == "SUB_ADMIN" and not is_circle_authorized(current_user, c_up):
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized: You do not have permissions for circle: {circle}"
        )

    # Handle CITY / BERHAMPUR CITY
    if c_up in ("CITY", "BERHAMPUR CITY"):
        teams = db.query(Team).filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]), Team.is_active == True).order_by(Team.name).all()
    else:
        teams = db.query(Team).filter(Team.circle == c_up, Team.is_active == True).order_by(Team.name).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "circle": t.circle,
            "default_tl_id": t.default_tl_id,
            "assigned_team_lead": (t.default_tl.name if t.default_tl else t.assigned_team_lead) or "TPSODL Official",
            "supervisor_name": t.supervisor_name or "",
            "has_vehicle": bool(t.has_vehicle),
            "is_office_team": bool(t.is_office_team or not t.has_vehicle)
        }
        for t in teams
    ]

@router.get("/tls-by-circle/{circle}")
def get_tls_by_circle(
    circle: str,
    team_id: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """
    Returns list of TPSODL Team Leaders (permanent regular company officers) for the circle/team.
    Team Leaders supervise squads and authorize enforcement raids, but do NOT punch Form D attendance.
    """
    c_up = circle.strip().upper()
    if current_user and current_user.role == "SUB_ADMIN" and not is_circle_authorized(current_user, c_up):
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized: You do not have permissions for circle: {circle}"
        )

    q = db.query(TeamLead).filter(TeamLead.is_active == True)
    if c_up in ("CITY", "BERHAMPUR CITY"):
        q = q.filter(TeamLead.circle.in_(["CITY", "BERHAMPUR CITY"]))
    else:
        q = q.filter(TeamLead.circle == c_up)

    tls = q.order_by(TeamLead.name).all()
    return [
        {
            "id": tl.id,
            "tl_code": tl.tl_code,
            "name": tl.name,
            "designation": tl.designation or "Team Leader (TPSODL)",
            "circle": tl.circle
        }
        for tl in tls
    ]

@router.get("/team-members/{team_id}")
def get_team_members(team_id: int, db: Session = Depends(get_db)):
    """Returns BA contractor employees assigned to this squad."""
    emps = db.query(Employee).filter(
        Employee.team_id == team_id,
        Employee.is_active == True
    ).order_by(Employee.name).all()

    return [
        {
            "id": e.id,
            "emp_code": e.emp_code,
            "name": e.name,
            "designation": e.designation or "Squad Member (BA)",
            "circle": e.circle
        }
        for e in emps
    ]

@router.get("/status")
def get_daily_status(operation_date: date, team_id: int, db: Session = Depends(get_db)):
    op = db.query(DailyTeamOperation).filter(
        DailyTeamOperation.operation_date == operation_date,
        DailyTeamOperation.team_id == team_id
    ).first()
    if not op:
        return {"exists": False}
    
    attendances = db.query(Attendance).filter(Attendance.operation_id == op.id).all()
    att_map = {a.employee_id: a.status for a in attendances}

    tl_name = (op.daily_tl.name if op.daily_tl else op.tl_name) or ""

    return {
        "exists": True,
        "operation_id": op.id,
        "daily_tl_id": op.daily_tl_id,
        "tl_name": tl_name,
        "is_team_active": getattr(op, "is_team_active", True),
        "operating_with_tl": getattr(op, "operating_with_tl", True),
        "operation_mode": op.operation_mode,
        "merged_with_team_id": op.merged_with_team_id,
        "remarks": op.remarks or "",
        "attendance": att_map
    }

@router.get("/active-squads")
def get_active_squads(
    operation_date: date,
    circle: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    teams_q = db.query(Team).filter(Team.is_active == True)
    
    if current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")

        if circle:
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(
                    status_code=403,
                    detail=f"Unauthorized: You do not have permissions for circle: {circle}"
                )
            if c_up in ("CITY", "BERHAMPUR CITY"):
                teams_q = teams_q.filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                teams_q = teams_q.filter(Team.circle == c_up)
        else:
            teams_q = teams_q.filter(Team.circle.in_(expanded))
    elif circle:
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            teams_q = teams_q.filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            teams_q = teams_q.filter(Team.circle == c_up)

    teams = teams_q.all()

    active_teams = []
    for t in teams:
        op = db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == operation_date,
            DailyTeamOperation.team_id == t.id
        ).first()

        if op and (op.operation_mode == "NON_OPERATIONAL" or not getattr(op, "is_team_active", True)):
            continue

        tl_name = None
        if op and op.daily_tl:
            tl_name = f"{op.daily_tl.name} ({op.daily_tl.tl_code})"
        elif op and op.tl_name:
            tl_name = op.tl_name
        elif t.default_tl:
            tl_name = f"{t.default_tl.name} ({t.default_tl.tl_code})"
        else:
            tl_name = t.assigned_team_lead or "TPSODL TL"

        is_office = bool(t.is_office_team or not t.has_vehicle)
        mode = op.operation_mode if op else ("OFFICE_DUTY_NO_VEHICLE" if is_office else "INDEPENDENT_WITH_TL")

        active_teams.append({
            "id": t.id,
            "name": t.name,
            "circle": t.circle,
            "mode": mode,
            "tl_name": tl_name,
            "has_vehicle": bool(t.has_vehicle),
            "is_office_team": is_office
        })

    return active_teams

@router.post("/save")
def save_daily_attendance(
    req: SaveOperationRequest,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == req.team_id).first()
    target_circle = req.circle or (team.circle if team else None)

    if current_user:
        verify_write_permission(current_user, target_circle)

    # Determine mode based on inputs & team vehicle configuration
    is_office = bool(team and (team.is_office_team or not team.has_vehicle))
    final_mode = req.operation_mode
    if not req.is_team_active:
        final_mode = "NON_OPERATIONAL"
    elif is_office or req.operation_mode == "OFFICE_DUTY_NO_VEHICLE":
        final_mode = "OFFICE_DUTY_NO_VEHICLE"
        if not (req.remarks and req.remarks.strip()):
            req.remarks = "Office / Administrative Duty Only (No Vehicle Assigned)"
    elif not req.operating_with_tl:
        if req.operation_mode == "MERGED":
            final_mode = "MERGED"
        else:
            final_mode = "INDEPENDENT_WITHOUT_TL_COLLECTION"
    else:
        final_mode = "INDEPENDENT_WITH_TL"

    if final_mode == "NON_OPERATIONAL" and not (req.remarks and req.remarks.strip()):
        req.remarks = "Squad marked Inactive for the day"
    
    if final_mode == "MERGED" and (not req.merged_with_team_id or req.merged_with_team_id == req.team_id):
        raise HTTPException(status_code=400, detail="Please select a valid partner squad in this circle to merge with")

    target_tl_id = req.daily_tl_id or req.daily_team_lead_id
    tl_name = req.tl_name.strip() if req.tl_name else None

    # Resolve TL if needed
    if target_tl_id:
        tl_obj = db.query(TeamLead).filter(TeamLead.id == target_tl_id).first()
        if tl_obj and not tl_name:
            tl_name = tl_obj.name
    elif tl_name:
        tl_obj = db.query(TeamLead).filter(TeamLead.name == tl_name).first()
        if tl_obj:
            target_tl_id = tl_obj.id

    op = db.query(DailyTeamOperation).filter(
        DailyTeamOperation.operation_date == req.operation_date,
        DailyTeamOperation.team_id == req.team_id
    ).first()

    if not op:
        op = DailyTeamOperation(
            operation_date=req.operation_date,
            team_id=req.team_id,
            daily_tl_id=target_tl_id,
            tl_name=tl_name,
            is_team_active=req.is_team_active,
            operating_with_tl=req.operating_with_tl,
            operation_mode=final_mode,
            merged_with_team_id=req.merged_with_team_id if final_mode == "MERGED" else None,
            remarks=req.remarks.strip() if req.remarks else None
        )
        db.add(op)
        db.flush()
    else:
        op.daily_tl_id = target_tl_id
        op.tl_name = tl_name
        op.is_team_active = req.is_team_active
        op.operating_with_tl = req.operating_with_tl
        op.operation_mode = final_mode
        op.merged_with_team_id = req.merged_with_team_id if final_mode == "MERGED" else None
        op.remarks = req.remarks.strip() if req.remarks else None
        db.query(Attendance).filter(Attendance.operation_id == op.id).delete()

    # Save BA squad members' attendance (TL does not punch in this portal)
    for item in req.attendance:
        db.add(Attendance(
            operation_id=op.id,
            employee_id=item.employee_id,
            status=item.status
        ))

    db.commit()
    return {
        "success": True,
        "message": f"Daily operations and {len(req.attendance)} BA squad members' attendance saved successfully!",
        "mode": final_mode,
        "final_mode": final_mode
    }

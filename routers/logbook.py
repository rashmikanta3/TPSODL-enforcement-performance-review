from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import VehicleLogBook, Team, User, get_assigned_circles, is_circle_authorized
from schemas import LogBookEntry
from auth import get_current_actor, verify_write_permission

router = APIRouter()

@router.post("/save")
def save_logbook(
    req: LogBookEntry,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    if req.end_km < req.start_km:
        raise HTTPException(status_code=400, detail="End KM cannot be less than Start KM")
    
    team = db.query(Team).filter(Team.id == req.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user:
        verify_write_permission(current_user, team.circle)
        if current_user.role == "USER":
            if not current_user.team_id or current_user.team_id != req.team_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access Denied: You can only record logbook entries for your assigned squad (Team ID: {current_user.team_id})."
                )

    if team.is_office_team or not team.has_vehicle:
        raise HTTPException(
            status_code=400,
            detail=f"Operation not permitted: Squad '{team.name}' is designated as an Office Team (Without Vehicle) and cannot record vehicle logbook kilometer runs."
        )
        
    perm_tl = team.assigned_team_lead or "N/A"
    run_km = req.end_km - req.start_km

    entry = VehicleLogBook(
        date=req.date,
        team_id=req.team_id,
        vehicle_no=req.vehicle_no.strip(),
        supervisor_name=req.supervisor_name.strip() if req.supervisor_name else team.supervisor_name,
        permanent_team_lead=perm_tl,
        start_km=req.start_km,
        end_km=req.end_km,
        run_km=run_km,
        start_time=req.start_time.strip(),
        end_time=req.end_time.strip(),
        area_movement=req.area_movement.strip() if req.area_movement else None,
        is_locked=True
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"success": True, "id": entry.id, "run_km": run_km, "message": f"Log book saved! Total Run: {run_km} KM"}

@router.get("/eligible-teams")
def get_eligible_logbook_teams(
    circle: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """Returns active field squads with assigned vehicles (excluding Office Teams)."""
    q = db.query(Team).filter(
        Team.is_active == True,
        Team.has_vehicle == True,
        Team.is_office_team == False
    )
    if current_user and current_user.role == "USER":
        if current_user.team_id:
            q = q.filter(Team.id == current_user.team_id)
        else:
            q = q.filter(Team.id == -1)
    elif circle:
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(Team.circle == c_up)
            
    teams = q.order_by(Team.name.asc()).all()
    return [{
        "id": t.id,
        "name": t.name,
        "circle": t.circle,
        "supervisor_name": t.supervisor_name,
        "assigned_team_lead": t.assigned_team_lead,
        "has_vehicle": t.has_vehicle,
        "is_office_team": t.is_office_team
    } for t in teams]

@router.get("/recent")
def get_recent_logs(
    team_id: Optional[int] = None,
    circle: Optional[str] = None,
    limit: int = 30,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    q = db.query(VehicleLogBook, Team.name.label("team_name"), Team.circle.label("team_circle")).join(Team, VehicleLogBook.team_id == Team.id)
    
    if current_user and current_user.role == "USER":
        if current_user.team_id:
            q = q.filter(VehicleLogBook.team_id == current_user.team_id)
        else:
            q = q.filter(VehicleLogBook.team_id == -1)
    elif current_user and current_user.role == "SUB_ADMIN":
        allowed = get_assigned_circles(current_user)
        expanded = list(allowed)
        if "BERHAMPUR CITY" in allowed and "CITY" not in expanded:
            expanded.append("CITY")
        if "CITY" in allowed and "BERHAMPUR CITY" not in expanded:
            expanded.append("BERHAMPUR CITY")

        if circle:
            c_up = circle.strip().upper()
            if not is_circle_authorized(current_user, c_up):
                raise HTTPException(status_code=403, detail=f"Unauthorized: You do not have permissions for circle: {circle}")
            if c_up in ("CITY", "BERHAMPUR CITY"):
                q = q.filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]))
            else:
                q = q.filter(Team.circle == c_up)
        else:
            q = q.filter(Team.circle.in_(expanded))
    elif circle:
        c_up = circle.strip().upper()
        if c_up in ("CITY", "BERHAMPUR CITY"):
            q = q.filter(Team.circle.in_(["CITY", "BERHAMPUR CITY"]))
        else:
            q = q.filter(Team.circle == c_up)

    if team_id:
        q = q.filter(VehicleLogBook.team_id == team_id)
    
    results = q.order_by(VehicleLogBook.date.desc(), VehicleLogBook.id.desc()).limit(limit).all()
    
    out = []
    for log, t_name, t_circle in results:
        out.append({
            "id": log.id,
            "date": str(log.date),
            "team_id": log.team_id,
            "team_name": t_name,
            "circle": t_circle,
            "vehicle_no": log.vehicle_no,
            "supervisor_name": log.supervisor_name or "",
            "permanent_team_lead": log.permanent_team_lead or "",
            "start_km": log.start_km,
            "end_km": log.end_km,
            "run_km": log.run_km,
            "start_time": log.start_time,
            "end_time": log.end_time,
            "area_movement": log.area_movement or "",
            "is_locked": bool(getattr(log, "is_locked", True))
        })
    return out

@router.delete("/{log_id}")
def delete_logbook(
    log_id: int,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    entry = db.query(VehicleLogBook).filter(VehicleLogBook.id == log_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Log book entry not found")
    if not current_user or current_user.role == "USER":
        raise HTTPException(
            status_code=403,
            detail="This record is locked after submission. Contact your Circle Admin or MIS In-Charge to make corrections."
        )
    if current_user.role == "SUB_ADMIN":
        if entry.team and not is_circle_authorized(current_user, entry.team.circle):
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permissions for this circle.")
        if not current_user.can_edit:
            raise HTTPException(status_code=403, detail="View-only Sub-Admin account cannot delete records.")

    db.delete(entry)
    db.commit()
    return {"success": True, "id": log_id, "message": "Log book entry deleted successfully"}

@router.patch("/{log_id}/toggle-lock")
def toggle_log_lock(
    log_id: int,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    if not current_user or current_user.role not in ["ADMIN", "SUB_ADMIN"]:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only Admins and Sub-Admins can lock or unlock vehicle log book records."
        )
    entry = db.query(VehicleLogBook).filter(VehicleLogBook.id == log_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Log book entry not found")
    if current_user.role == "SUB_ADMIN" and entry.team and not is_circle_authorized(current_user, entry.team.circle):
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permissions for this circle.")

    entry.is_locked = not bool(getattr(entry, "is_locked", True))
    db.commit()
    db.refresh(entry)
    state_str = "locked" if entry.is_locked else "unlocked"
    return {
        "success": True,
        "id": entry.id,
        "is_locked": bool(entry.is_locked),
        "message": f"Vehicle Log Book record {state_str} successfully"
    }


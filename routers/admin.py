import io
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from database import get_db
from models import Team, TeamLead, Employee, User, VCRMaster
from auth import get_current_user_optional
from schemas import (
    CreateTeamRequest, UpdateTeamRequest,
    CreateTeamLeadRequest, UpdateTeamLeadRequest, TeamLeadResponse,
    CreateEmployeeRequest, UpdateEmployeeRequest,
    CreateUserRequest, UpdateUserRequest,
    VCRMasterCreate
)

def require_admin_role(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Enforces strict ADMIN role access. Sub-Admins and Users are rejected with 403 Forbidden."""
    if current_user and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Administration is restricted strictly to ADMIN users."
        )
    role_header = request.headers.get("x-user-role")
    if role_header and role_header.strip().upper() != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Administration is restricted strictly to ADMIN users."
        )
    return True

router = APIRouter(dependencies=[Depends(require_admin_role)])

# ==========================================
# 1. TEAMS / SQUADS MANAGEMENT
# ==========================================
@router.post("/teams")
def create_team(req: CreateTeamRequest, db: Session = Depends(get_db)):
    existing = db.query(Team).filter(Team.name == req.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Team '{req.name}' already exists")
    
    assigned_tl = req.assigned_team_lead.strip() if req.assigned_team_lead else None
    if req.default_tl_id and req.default_tl_id > 0 and not assigned_tl:
        tl = db.query(TeamLead).filter(TeamLead.id == req.default_tl_id).first()
        if tl:
            assigned_tl = tl.name

    is_office = bool(req.is_office_team or (req.has_vehicle is False))
    has_veh = False if is_office else (req.has_vehicle if req.has_vehicle is not None else True)

    t = Team(
        name=req.name.strip(),
        circle=req.circle.strip().upper(),
        supervisor_name=req.supervisor_name.strip() if req.supervisor_name else None,
        default_tl_id=req.default_tl_id if req.default_tl_id and req.default_tl_id > 0 else None,
        assigned_team_lead=assigned_tl,
        has_vehicle=has_veh,
        is_office_team=is_office,
        is_active=True
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "success": True,
        "id": t.id,
        "message": f"Team '{t.name}' created successfully",
        "team": {
            "id": t.id,
            "name": t.name,
            "circle": t.circle,
            "supervisor_name": t.supervisor_name or "",
            "default_tl_id": t.default_tl_id,
            "assigned_team_lead": t.assigned_team_lead or "",
            "has_vehicle": t.has_vehicle,
            "is_office_team": t.is_office_team,
            "is_active": t.is_active
        }
    }

@router.get("/teams/all")
@router.get("/teams")
def list_teams(circle: Optional[str] = None, active_only: bool = False, db: Session = Depends(get_db)):
    """Returns all teams (both active and inactive unless active_only=True specified)."""
    q = db.query(Team)
    if active_only:
        q = q.filter(Team.is_active == True)
    if circle:
        q = q.filter(Team.circle == circle.strip().upper())
    teams = q.order_by(Team.circle, Team.name).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "circle": t.circle,
            "supervisor_name": t.supervisor_name or "",
            "default_tl_id": t.default_tl_id,
            "default_tl_name": t.default_tl.name if t.default_tl else (t.assigned_team_lead or ""),
            "default_tl_code": t.default_tl.tl_code if t.default_tl else "",
            "assigned_team_lead": (t.default_tl.name if t.default_tl else t.assigned_team_lead) or "",
            "has_vehicle": bool(t.has_vehicle),
            "is_office_team": bool(t.is_office_team or not t.has_vehicle),
            "is_active": bool(t.is_active)
        }
        for t in teams
    ]

@router.put("/teams/{team_id}")
def update_team(team_id: int, req: UpdateTeamRequest, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if req.name is not None and req.name.strip():
        team.name = req.name.strip()
    if req.circle is not None and req.circle.strip():
        team.circle = req.circle.strip().upper()
    if req.supervisor_name is not None:
        team.supervisor_name = req.supervisor_name.strip()
    if req.default_tl_id is not None:
        team.default_tl_id = req.default_tl_id if req.default_tl_id > 0 else None
        if team.default_tl_id:
            tl = db.query(TeamLead).filter(TeamLead.id == team.default_tl_id).first()
            if tl:
                team.assigned_team_lead = tl.name
    if req.assigned_team_lead is not None:
        team.assigned_team_lead = req.assigned_team_lead.strip()
    if req.is_office_team is not None or req.has_vehicle is not None:
        is_office = team.is_office_team if req.is_office_team is None else req.is_office_team
        if req.has_vehicle is False:
            is_office = True
        team.is_office_team = is_office
        team.has_vehicle = False if is_office else (req.has_vehicle if req.has_vehicle is not None else team.has_vehicle)
    if req.is_active is not None:
        team.is_active = req.is_active
    db.commit()
    db.refresh(team)
    return {
        "success": True,
        "message": f"Team '{team.name}' updated successfully",
        "team": {
            "id": team.id,
            "name": team.name,
            "circle": team.circle,
            "supervisor_name": team.supervisor_name or "",
            "default_tl_id": team.default_tl_id,
            "assigned_team_lead": team.assigned_team_lead or "",
            "has_vehicle": team.has_vehicle,
            "is_office_team": team.is_office_team,
            "is_active": bool(team.is_active)
        }
    }

@router.patch("/teams/{team_id}/toggle-status")
def toggle_team_status(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.is_active = not bool(team.is_active)
    db.commit()
    db.refresh(team)
    state_str = "activated" if team.is_active else "deactivated"
    return {
        "success": True,
        "id": team.id,
        "is_active": bool(team.is_active),
        "message": f"Team '{team.name}' {state_str} successfully"
    }


# ==========================================
# 2. TPSODL TEAM LEADERS (REGULAR OFFICERS)
# ==========================================
@router.post("/team-leads")
def create_team_lead(req: CreateTeamLeadRequest, db: Session = Depends(get_db)):
    existing = db.query(TeamLead).filter(TeamLead.tl_code == req.tl_code.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Team Leader Code '{req.tl_code}' already exists")
    tl = TeamLead(
        tl_code=req.tl_code.strip(),
        name=req.name.strip(),
        designation=req.designation.strip() if req.designation else None,
        circle=req.circle.strip().upper(),
        contact_no=req.contact_no.strip() if req.contact_no else None,
        is_active=True
    )
    db.add(tl)
    db.commit()
    db.refresh(tl)
    return {
        "success": True,
        "id": tl.id,
        "message": f"TPSODL Officer '{tl.name}' ({tl.tl_code}) registered successfully",
        "team_lead": {
            "id": tl.id,
            "tl_code": tl.tl_code,
            "name": tl.name,
            "designation": tl.designation or "",
            "circle": tl.circle,
            "contact_no": tl.contact_no or "",
            "is_active": tl.is_active
        }
    }

@router.get("/team-leads/all")
@router.get("/team-leads")
def list_team_leads(circle: Optional[str] = None, active_only: bool = False, db: Session = Depends(get_db)):
    """Returns all TPSODL regular officers designated as Team Leaders."""
    q = db.query(TeamLead)
    if active_only:
        q = q.filter(TeamLead.is_active == True)
    if circle:
        q = q.filter(TeamLead.circle == circle.strip().upper())
    tls = q.order_by(TeamLead.circle, TeamLead.name).all()
    return [
        {
            "id": tl.id,
            "tl_code": tl.tl_code,
            "name": tl.name,
            "designation": tl.designation or "",
            "circle": tl.circle,
            "contact_no": tl.contact_no or "",
            "is_active": bool(tl.is_active)
        }
        for tl in tls
    ]

@router.put("/team-leads/{tl_id}")
def update_team_lead(tl_id: int, req: UpdateTeamLeadRequest, db: Session = Depends(get_db)):
    tl = db.query(TeamLead).filter(TeamLead.id == tl_id).first()
    if not tl:
        raise HTTPException(status_code=404, detail="Team Leader not found")
    if req.tl_code is not None and req.tl_code.strip():
        dup = db.query(TeamLead).filter(TeamLead.tl_code == req.tl_code.strip(), TeamLead.id != tl_id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Team Leader code '{req.tl_code}' already exists")
        tl.tl_code = req.tl_code.strip()
    if req.name is not None and req.name.strip():
        tl.name = req.name.strip()
    if req.designation is not None:
        tl.designation = req.designation.strip()
    if req.circle is not None and req.circle.strip():
        tl.circle = req.circle.strip().upper()
    if req.contact_no is not None:
        tl.contact_no = req.contact_no.strip()
    if req.is_active is not None:
        tl.is_active = req.is_active
    db.commit()
    db.refresh(tl)
    return {
        "success": True,
        "message": f"Team Leader '{tl.name}' updated successfully",
        "team_lead": {
            "id": tl.id,
            "tl_code": tl.tl_code,
            "name": tl.name,
            "designation": tl.designation or "",
            "circle": tl.circle,
            "contact_no": tl.contact_no or "",
            "is_active": bool(tl.is_active)
        }
    }

@router.patch("/team-leads/{tl_id}/toggle-status")
def toggle_team_lead_status(tl_id: int, db: Session = Depends(get_db)):
    tl = db.query(TeamLead).filter(TeamLead.id == tl_id).first()
    if not tl:
        raise HTTPException(status_code=404, detail="Team Leader not found")
    tl.is_active = not bool(tl.is_active)
    db.commit()
    db.refresh(tl)
    state_str = "activated" if tl.is_active else "deactivated"
    return {
        "success": True,
        "id": tl.id,
        "is_active": bool(tl.is_active),
        "message": f"Team Leader '{tl.name}' {state_str} successfully"
    }


# ==========================================
# 3. BA CONTRACTOR EMPLOYEES DIRECTORY
# ==========================================
@router.post("/employees")
def create_employee(req: CreateEmployeeRequest, db: Session = Depends(get_db)):
    existing = db.query(Employee).filter(Employee.emp_code == req.emp_code.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Employee code '{req.emp_code}' already exists")
    emp = Employee(
        emp_code=req.emp_code.strip(),
        name=req.name.strip(),
        designation=req.designation.strip() if req.designation else None,
        circle=req.circle.strip().upper(),
        team_id=req.team_id if req.team_id and req.team_id > 0 else None,
        is_active=True
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return {
        "success": True,
        "id": emp.id,
        "message": f"BA Personnel '{emp.name}' created successfully",
        "employee": {
            "id": emp.id,
            "emp_code": emp.emp_code,
            "name": emp.name,
            "designation": emp.designation or "",
            "circle": emp.circle,
            "team_id": emp.team_id,
            "team_name": emp.team.name if emp.team else "Unassigned",
            "is_active": emp.is_active
        }
    }

@router.get("/employees/all")
@router.get("/employees")
def list_employees(circle: Optional[str] = None, team_id: Optional[int] = None, active_only: bool = False, db: Session = Depends(get_db)):
    """Returns all BA contractor personnel with assigned squad name and circle."""
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.is_active == True)
    if circle:
        q = q.filter(Employee.circle == circle.strip().upper())
    if team_id:
        q = q.filter(Employee.team_id == team_id)
    emps = q.order_by(Employee.circle, Employee.name).all()
    return [
        {
            "id": e.id,
            "emp_code": e.emp_code,
            "name": e.name,
            "designation": e.designation or "",
            "circle": e.circle,
            "team_id": e.team_id,
            "team_name": e.team.name if e.team else "Unassigned",
            "is_active": bool(e.is_active)
        }
        for e in emps
    ]

@router.put("/employees/{emp_id}")
def update_employee(emp_id: int, req: UpdateEmployeeRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if req.emp_code is not None and req.emp_code.strip():
        dup = db.query(Employee).filter(Employee.emp_code == req.emp_code.strip(), Employee.id != emp_id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Employee code '{req.emp_code}' is already used by another employee")
        emp.emp_code = req.emp_code.strip()
    if req.name is not None and req.name.strip():
        emp.name = req.name.strip()
    if req.designation is not None:
        emp.designation = req.designation.strip()
    if req.circle is not None and req.circle.strip():
        emp.circle = req.circle.strip().upper()
    if req.team_id is not None:
        emp.team_id = req.team_id if req.team_id > 0 else None
    if req.is_active is not None:
        emp.is_active = req.is_active
    db.commit()
    db.refresh(emp)
    return {
        "success": True,
        "message": f"Personnel '{emp.name}' updated successfully",
        "employee": {
            "id": emp.id,
            "emp_code": emp.emp_code,
            "name": emp.name,
            "designation": emp.designation or "",
            "circle": emp.circle,
            "team_id": emp.team_id,
            "team_name": emp.team.name if emp.team else "Unassigned",
            "is_active": bool(emp.is_active)
        }
    }

@router.patch("/employees/{emp_id}/toggle-status")
def toggle_employee_status(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = not bool(emp.is_active)
    db.commit()
    db.refresh(emp)
    state_str = "activated" if emp.is_active else "deactivated"
    return {
        "success": True,
        "id": emp.id,
        "is_active": bool(emp.is_active),
        "message": f"Personnel '{emp.name}' {state_str} successfully"
    }


# ==========================================
# 4. PORTAL USERS & RBAC MANAGEMENT
# ==========================================
@router.post("/users")
def create_user(req: CreateUserRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username.strip()).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=req.username.strip(),
        password=req.password.strip(),
        role=req.role.strip().upper(),
        circle=req.circle.strip().upper() if req.circle and req.circle.strip() else None,
        can_edit=req.can_edit,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "id": user.id,
        "message": f"User '{user.username}' created successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "circle": user.circle or "ALL",
            "can_edit": user.can_edit,
            "is_active": user.is_active
        }
    }

@router.get("/users/all")
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    """Returns all portal accounts excluding sensitive passwords."""
    users = db.query(User).order_by(User.role, User.username).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "circle": u.circle or "ALL",
            "can_edit": bool(u.can_edit),
            "is_active": bool(u.is_active)
        }
        for u in users
    ]

@router.put("/users/{user_id}")
def update_user(user_id: int, req: UpdateUserRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.password is not None and req.password.strip():
        user.password = req.password.strip()
    if req.role is not None and req.role.strip():
        user.role = req.role.strip().upper()
    if req.circle is not None:
        c_val = req.circle.strip().upper()
        user.circle = c_val if c_val and c_val != "ALL" else None
    if req.can_edit is not None:
        user.can_edit = req.can_edit
    if req.is_active is not None:
        user.is_active = req.is_active
    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "message": f"User '{user.username}' updated successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "circle": user.circle or "ALL",
            "can_edit": bool(user.can_edit),
            "is_active": bool(user.is_active)
        }
    }

@router.patch("/users/{user_id}/toggle-status")
def toggle_user_status(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not bool(user.is_active)
    db.commit()
    db.refresh(user)
    state_str = "activated" if user.is_active else "deactivated"
    return {
        "success": True,
        "id": user.id,
        "is_active": bool(user.is_active),
        "message": f"User '{user.username}' {state_str} successfully"
    }


# ==========================================
# 5. VCR MASTERS & FORWARDERS
# ==========================================
@router.post("/vcr")
def create_vcr(req: VCRMasterCreate, db: Session = Depends(get_db)):
    existing = db.query(VCRMaster).filter(VCRMaster.vcr_number == req.vcr_number.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="VCR Number already exists")
    vcr = VCRMaster(
        vcr_number=req.vcr_number.strip(),
        booking_id=req.booking_id,
        consumer_name=req.consumer_name.strip(),
        consumer_address=req.consumer_address.strip() if req.consumer_address else None,
        circle=req.circle.strip().upper(),
        division=req.division.strip() if req.division else None,
        section=req.section.strip() if req.section else None,
        provisional_bill_date=req.provisional_bill_date
    )
    db.add(vcr)
    db.commit()
    db.refresh(vcr)
    return {"success": True, "id": vcr.id, "message": f"VCR '{vcr.vcr_number}' registered"}

@router.get("/vcr")
def list_vcrs(circle: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(VCRMaster)
    if circle:
        q = q.filter(VCRMaster.circle == circle.strip().upper())
    return q.order_by(VCRMaster.id.desc()).limit(limit).all()

from routers.vcr import download_vcr_template as _dl_template, bulk_upload_vcr_excel as _bulk_upload
router.add_api_route("/vcr/template", _dl_template, methods=["GET"])
router.add_api_route("/vcr/bulk-upload", _bulk_upload, methods=["POST"])

from datetime import date
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from database import get_db
from models import LoadBooking, DailyTeamOperation, TeamLead, Employee, Team, VCRMaster, User, get_assigned_circles, is_circle_authorized
from schemas import LoadBookingRequest
from auth import get_current_actor, verify_write_permission

router = APIRouter()

# Official Hierarchical Electrical Network Structure for TPSODL:
# Circle -> Division -> Subdivision -> Sections
TPSODL_HIERARCHY: Dict[str, dict] = {
    "ASKA": {
        "AED ASKA-I": {
            "ASKA": ["ESO ASKA-1", "ESO BALISIRA", "ESO DHARAKOTE"],
            "NUAGAON": ["ESO NUAGAM-I", "ESO NUAGAM-II"]
        },
        "AED ASKA-II": {
            "BUGUDA": ["ESO BALIPADAR", "ESO BUGUDA"],
            "K S NAGAR": ["ESO BUDHAAMBA", "ESO K S NAGAR"]
        },
        "GSED DIGAPAHANDI": {
            "CHIKITI": ["ESO CHIKITI", "ESO NUAPADA", "ESO PATRAPUR", "ESO SURANGI"],
            "DIGAPAHANDI": ["ESO BOMAKEI", "ESO DIGAPAHANDI", "ESO PUDAMARI"]
        }
    },
    "BERHAMPUR": {
        "GANJAM NORTH": {
            "CHATRAPUR": ["ESO CHATRAPUR-I", "ESO CHATRAPUR-II"],
            "KHALLIKOTE": ["ESO KESHPUR", "ESO KHALLIKOTE"],
            "RAMBHA": ["ESO GANJAM", "ESO MALUD", "ESO RAMBHA"]
        },
        "HED HINJILICUT": {
            "HINJILICUT": ["ESO HINJILICUT", "ESO KANCHURU", "ESO PITALA"],
            "SHERAGADA": ["ESO KONKARADA", "ESO PATTAPUR", "ESO SHERAGADA"]
        },
        "PSED PURUSOTTAMPUR": {
            "KODALA": ["ESO BEGUNIAPADA", "ESO KODALA"],
            "P S PUR": ["ESO P S PUR", "ESO TARATARINI"],
            "POLASARA": ["ESO CHIRIKIPADA", "ESO POLOSARA"]
        }
    },
    "BERHAMPUR CITY": {
        "BERHAMPUR-I": {
            "BIJIPUR": ["ESO BIJIPUR", "ESO LANJIPALLI"],
            "GOPALPUR": ["ESO GOPALPUR", "ESO HEAD QUARTER", "ESO UNIVERSITY"],
            "SUB.DIV.NO-2": ["ESO AMBAPUA", "ESO MEDICAL"]
        },
        "BERHAMPUR-II": {
            "SUB.DIVISION NO-1": ["ESO E.S.O.NO.1", "ESO E.S.O.NO.2", "ESO E.S.O.NO.3"],
            "SUB.DIVISION NO-3": ["ESO G.NUAGAM-2", "ESO GANDHINAGAR"]
        },
        "BERHAMPUR-III": {
            "KANISI": ["ESO GOLANTHARA", "ESO JAGAPUR", "ESO KANISI"],
            "SUB.DIVISION NO-4": ["ESO KUKUDAKHANDI", "ESO LATHI", "ESO LUCHAPADA"]
        }
    },
    "BHANJANAGAR": {
        "BNED BHANJANAGAR": {
            "BELAGUNTHA": ["ESO BELAGUNTHA", "ESO J N PRASAD"],
            "BHANJANAGAR-I": ["ESO BHEJIPUT", "ESO E S O-I", "ESO TILISINGI"],
            "BHANJANAGAR-II": ["ESO E S O-II", "ESO K B PUR", "ESO KANTEIPALLY"],
            "SORODA": ["ESO BADAGADA", "ESO SORODA"]
        },
        "BoED BOUDH": {
            "BOUDH": ["ESO BOUDH", "ESO PURUNAKATAK"],
            "MANAMUNDA": ["ESO BAUNSUNI", "ESO MANAMUNDA"]
        },
        "PED PHULBANI": {
            "BALLIGUDA": ["ESO BALLIGUDA", "ESO DARINGIBADI", "ESO TUMUDIBANDHA"],
            "G.UDAYAGIRI": ["ESO G.UDAYAGIRI", "ESO RAIKIA", "ESO TIKABALI"],
            "PHULBANI": ["ESO KHAJURIPADA", "ESO PHIRINGAI", "ESO PHULBANI"]
        }
    },
    "JEYPORE": {
        "JED JEYPORE": {
            "BORIGUMA": ["ESO B.SINGIPUR", "ESO BORIGUMA", "ESO KOTPAD"],
            "JEYPORE SDO-I": ["ESO BAIPARIGUDA", "ESO JYP NO.2", "ESO JYP NO.3"],
            "JEYPORE SDO-II": ["ESO JYP NO.1", "ESO KUNDRA", "ESO RANDHAPALLI"]
        },
        "KED KORAPUT": {
            "KORAPUT": ["ESO KORAPUT SEC-I", "ESO KORAPUT SEC-II"],
            "LAXMIPUR": ["ESO BANDHUGAON", "ESO KAKIRIGUMA", "ESO LAXMIPUR"],
            "SUNABEDA": ["ESO NANDAPUR", "ESO PATTANGI", "ESO SIMILIGUDA", "ESO SUNABEDA"]
        },
        "MED MALKANAGIRI": {
            "BALIMELA": ["ESO BALIMELA", "ESO MATHILI"],
            "MALKANGIRI": ["ESO KALIMELA", "ESO MALKANGIRI"]
        },
        "NED NABARANGAPUR": {
            "NAWARANGPUR": ["ESO NABARANGAPUR", "ESO NABARANGPUR RURAL", "ESO T KHUNTI"],
            "PAPADAHANDI": ["ESO DABUGAON", "ESO KOSAGUMUDA", "ESO PAPADAHANDI"],
            "UMARKOT": ["ESO CHANDAHANDI", "ESO JHARIGAM", "ESO RAIGHAR", "ESO UMERKOTE"]
        }
    },
    "RAYAGADA": {
        "GED GUNUPUR": {
            "GUMUDA": ["ESO GUDARI", "ESO GUMUDA", "ESO PADMAPUR", "ESO RAMNAGUDA"],
            "GUNUPUR": ["ESO GUNUPUR", "ESO GUNUPUR RURAL"]
        },
        "PKED PARLAKHEMUNDI": {
            "KASINAGAR": ["ESO GUMMA", "ESO KASINAGAR"],
            "MOHANA": ["ESO ADABA", "ESO CHANDRAGIRI", "ESO MOHANA"],
            "PARLAKHEMUNDI": ["ESO PARLAKHEMUNDI", "ESO PARLAKHEMUNDI RURAL"],
            "R.UDAYGIRI": ["ESO KHAJURIPADA", "ESO KHAJURIPADA-I", "ESO R.UDAYGIRI"],
            "UPPALADA": ["ESO GARABANDHA", "ESO RAIGADA", "ESO UPALADA"]
        },
        "RED RAYAGADA": {
            "BISSAM CUTTACK": ["ESO BISSAM CTC", "ESO MUNIGUDA"],
            "RAYAGADA": ["ESO J.K.PUR", "ESO RAYAGADA RURAL", "ESO RAYAGADA-1", "ESO RAYAGADA-2"],
            "THERUBALLI": ["ESO KASIPUR", "ESO SIKARPAI", "ESO THERUBALI"]
        }
    }
}

def _resolve_circle_key(circle: str) -> Optional[str]:
    c = circle.strip().upper()
    if c in ("CITY", "BERHAMPUR CITY"):
        return "BERHAMPUR CITY"
    return c if c in TPSODL_HIERARCHY else None

@router.get("/hierarchy-tree")
def get_full_hierarchy():
    """Returns the complete TPSODL electrical hierarchy tree."""
    return TPSODL_HIERARCHY

@router.get("/hierarchy/{circle}")
def get_circle_hierarchy(circle: str):
    c = _resolve_circle_key(circle)
    return TPSODL_HIERARCHY.get(c, {}) if c else {}

@router.get("/divisions/{circle}")
def get_divisions(circle: str):
    c = _resolve_circle_key(circle)
    return list(TPSODL_HIERARCHY.get(c, {}).keys()) if c else []

@router.get("/subdivisions")
def get_subdivisions(circle: str, division: str):
    c = _resolve_circle_key(circle)
    d = division.strip()
    return list(TPSODL_HIERARCHY.get(c, {}).get(d, {}).keys()) if c else []

@router.get("/sections")
def get_sections(circle: str, division: str, subdivision: str):
    c = _resolve_circle_key(circle)
    d = division.strip()
    s = subdivision.strip()
    return TPSODL_HIERARCHY.get(c, {}).get(d, {}).get(s, []) if c else []

@router.get("/verify-tl")
@router.get("/verify-employee")
def verify_employee(
    emp_code: str = Query(...),
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    """Resolves TPSODL Team Leader details and assigned Circle."""
    code = emp_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Team Leader Code cannot be empty")

    # 1. Primary Lookup: TeamLead (TPSODL regular officers)
    tl = db.query(TeamLead).filter(func.lower(TeamLead.tl_code) == code.lower()).first()
    if not tl:
        tl = db.query(TeamLead).filter(func.lower(TeamLead.name).like(f"%{code.lower()}%")).first()

    circle = None
    officer_name = None
    resolved_code = code

    if tl:
        officer_name = tl.name
        circle = tl.circle
        resolved_code = tl.tl_code
    else:
        # Fallback 2: Check Team assigned_team_lead or team name
        tm = db.query(Team).filter(
            or_(
                func.lower(Team.assigned_team_lead) == code.lower(),
                func.lower(Team.assigned_team_lead).like(f"%{code.lower()}%"),
                func.lower(Team.name) == code.lower(),
                func.lower(Team.name).like(f"%{code.lower().replace('_', ' ')}%")
            )
        ).first()
        if tm:
            officer_name = tm.assigned_team_lead or tm.name
            circle = tm.circle
        else:
            # Fallback 3: Employee lookup
            emp = db.query(Employee).filter(func.lower(Employee.emp_code) == code.lower()).first()
            if not emp:
                emp = db.query(Employee).filter(func.lower(Employee.name).like(f"%{code.lower()}%")).first()
            if emp:
                officer_name = emp.name
                circle = emp.circle
                resolved_code = emp.emp_code

    if not circle:
        raise HTTPException(status_code=404, detail=f"Team Leader / Officer Code '{code}' not found")

    circle_clean = _resolve_circle_key(circle) or circle.upper()

    if current_user and current_user.role == "SUB_ADMIN":
        if not is_circle_authorized(current_user, circle_clean):
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized: Officer belongs to circle '{circle_clean}', but you are authorized only for: {', '.join(get_assigned_circles(current_user))}"
            )

    return {
        "success": True,
        "tl_code": resolved_code,
        "emp_code": resolved_code,
        "name": officer_name or code,
        "circle": circle_clean
    }

@router.post("/save")
def punch_load_booking(
    req: LoadBookingRequest,
    current_user: Optional[User] = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    book_number = (req.book_number or "").strip()
    if not book_number:
        raise HTTPException(status_code=400, detail="Book Number is required")

    page_no = (req.page_number or req.page_no or "").strip()
    if not page_no:
        raise HTTPException(status_code=400, detail="Page number is required")

    if req.booked_load <= 0 or req.booked_load > 100:
        raise HTTPException(status_code=400, detail="Booked load must be between 0.001 and 100 kW")
    booked_load = round(float(req.booked_load), 3)

    circle_clean = req.circle.strip().upper()
    if circle_clean == "CITY":
        circle_clean = "BERHAMPUR CITY"

    if current_user:
        verify_write_permission(current_user, circle_clean)

    # Enforce duplicate check: (circle, book_number, page_no)
    existing_page = db.query(LoadBooking).filter(
        LoadBooking.circle == circle_clean,
        LoadBooking.book_number == book_number,
        LoadBooking.page_no == page_no
    ).first()

    if existing_page:
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate Page Number! Page '{page_no}' in Book '{book_number}' has already been booked in Circle '{circle_clean}'."
        )

    booking_date = req.booking_date or date.today()
    tl_code = (req.tl_code or req.punch_emp_code or "").strip()

    # DYNAMIC SQUAD PERFORMANCE ATTRIBUTION:
    # 1. Lookup TeamLead by tl_code
    tl = db.query(TeamLead).filter(func.lower(TeamLead.tl_code) == tl_code.lower()).first()
    if not tl:
        tl = db.query(TeamLead).filter(func.lower(TeamLead.name).like(f"%{tl_code.lower()}%")).first()

    assigned_team_id = None
    if tl:
        # Check Daily Operations on that date: which squad did this TL actively lead?
        daily_op = db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == booking_date,
            DailyTeamOperation.daily_tl_id == tl.id,
            DailyTeamOperation.is_team_active == True
        ).first()

        if daily_op and daily_op.team_id:
            assigned_team_id = daily_op.team_id
        else:
            # Fallback to team where this officer is default_tl
            def_team = db.query(Team).filter(Team.default_tl_id == tl.id, Team.is_active == True).first()
            if def_team:
                assigned_team_id = def_team.id
    
    if not assigned_team_id and req.team_id:
        assigned_team_id = req.team_id

    if not assigned_team_id:
        # Fallback to match Team by name or assigned_team_lead
        tm = db.query(Team).filter(
            or_(
                func.lower(Team.assigned_team_lead) == tl_code.lower(),
                func.lower(Team.name) == tl_code.lower()
            )
        ).first()
        if tm:
            assigned_team_id = tm.id

    if assigned_team_id:
        tm = db.query(Team).filter(Team.id == assigned_team_id).first()
        if tm and (tm.is_office_team or not tm.has_vehicle):
            raise HTTPException(
                status_code=400,
                detail=f"Operation not permitted: Squad '{tm.name}' is designated as an Office Team (Without Vehicle). Office Teams do not execute field enforcement operations."
            )

    booking = LoadBooking(
        booking_date=booking_date,
        book_number=book_number,
        page_no=page_no,
        tl_code=tl.tl_code if tl else tl_code,
        punch_emp_id=None,
        team_id=assigned_team_id,
        circle=circle_clean,
        division=req.division.strip(),
        subdivision=req.subdivision.strip(),
        section=req.section.strip(),
        pincode=None,
        theft_type=req.theft_type.strip(),
        booked_load=booked_load,
        status="PENDING"
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    team_name = "Unassigned"
    if assigned_team_id:
        tm = db.query(Team).filter(Team.id == assigned_team_id).first()
        if tm:
            team_name = tm.name

    return {
        "success": True,
        "booking_id": booking.id,
        "book_number": booking.book_number,
        "page_no": booking.page_no,
        "tl_code": booking.tl_code,
        "attributed_team_id": assigned_team_id,
        "attributed_team_name": team_name,
        "message": f"Load Booking of {booked_load} kW ({req.theft_type}) on Book '{book_number}', Page '{page_no}' saved and dynamically attributed to {team_name}!"
    }

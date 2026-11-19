import re
from datetime import date, datetime
from io import BytesIO
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case, or_
from database import get_db
from models import (
    LoadBooking, Collection, DisconnectionRecord, VCRMaster,
    Team, Employee, DailyTeamOperation, VehicleLogBook, Attendance
)

router = APIRouter()

def normalize_circle(circle: Optional[str]) -> Optional[str]:
    """
    Normalizes circle query parameter:
    Empty string, 'ALL', 'ALL CIRCLES', or None will return None,
    which signals querying across all circles unrestricted.
    """
    if not circle:
        return None
    val = circle.strip().upper()
    if val in ("", "ALL", "ALL CIRCLES", "ALL_CIRCLES", "NONE", "NULL"):
        return None
    return val

def strip_emp_code(name: Optional[str]) -> Optional[str]:
    """'Sanjay Behera (TL101)' -> 'Sanjay Behera'. Employee codes are not shown in reports."""
    if not name:
        return name
    return re.sub(r"\s*[\(\[][^()\[\]]*[\)\]]\s*$", "", str(name)).strip() or str(name)


def apply_circle_filter(query, column, circle: Optional[str]):
    """
    Applies circle filter to query if a specific circle is requested.
    Seamlessly handles 'CITY' and 'BERHAMPUR CITY' synonyms.
    """
    c = normalize_circle(circle)
    if not c:
        return query
    if c in ("CITY", "BERHAMPUR CITY"):
        return query.filter(or_(column == "CITY", column == "BERHAMPUR CITY"))
    return query.filter(column == c)

@router.get("/kpis")
def get_kpis(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    ZERO IN-MEMORY PYTHON COMPUTATIONS:
    All sums, counts, and averages are computed purely on the database side using SQLAlchemy expressions.
    Public and unrestricted for all viewers; circle=None or empty returns metrics across all circles.
    Excludes Office Teams (Without Vehicle) from field performance attribution.
    """
    c_upper = normalize_circle(circle)

    # 1 & 4. Load Bookings (kW & Theft Count) - exclude Office Teams
    lb_q = db.query(
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load"),
        func.count(LoadBooking.id).label("total_theft_cases")
    ).outerjoin(Team, LoadBooking.team_id == Team.id)\
     .filter(
        LoadBooking.booking_date.between(from_date, to_date),
        or_(LoadBooking.team_id == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    lb_q = apply_circle_filter(lb_q, LoadBooking.circle, c_upper)
    lb_res = lb_q.one()

    # 2 & 3. Collections (Amount & MR Count) - exclude Office Teams
    coll_q = db.query(
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("total_collection"),
        func.count(Collection.id).label("total_mrs")
    ).outerjoin(Team, Collection.team_name == Team.name)\
     .filter(
        Collection.payment_date.between(from_date, to_date),
        or_(Collection.team_name == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    coll_q = apply_circle_filter(coll_q, Collection.circle, c_upper)
    coll_res = coll_q.one()

    # 5 & 6. Disconnections (Count & Amount Pending) - exclude Office Teams
    dc_q = db.query(
        func.count(DisconnectionRecord.id).label("total_dc"),
        func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0).label("total_dc_amount")
    ).outerjoin(Team, DisconnectionRecord.team_id == Team.id)\
     .filter(
        DisconnectionRecord.dc_date.between(from_date, to_date),
        or_(DisconnectionRecord.team_id == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    if c_upper:
        dc_q = dc_q.join(VCRMaster, DisconnectionRecord.vcr_number == VCRMaster.vcr_number)
        dc_q = apply_circle_filter(dc_q, VCRMaster.circle, c_upper)
    dc_res = dc_q.one()

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "total_load_kw": round(float(lb_res.total_load), 2),
        "total_theft_cases": int(lb_res.total_theft_cases),
        "total_collection_amount": round(float(coll_res.total_collection), 2),
        "total_mr_count": int(coll_res.total_mrs),
        "total_dc_count": int(dc_res.total_dc),
        "total_dc_amount": round(float(dc_res.total_dc_amount), 2)
    }

@router.get("/charts/load-booking-hierarchy")
def get_charts_load_booking_hierarchy(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    level: str = Query("circle"),
    circle: Optional[str] = None,
    division: Optional[str] = None,
    subdivision: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Hierarchical Load Booking drill-down:
    Circle -> Division -> Subdivision -> Section
    Returns breakdown of theft types, total load kW, and theft case counts.
    Excludes Office Squads (Without Vehicle).
    """
    c_upper = normalize_circle(circle)
    lvl = (level or "circle").strip().lower()

    if lvl == "division":
        group_col = LoadBooking.division
    elif lvl == "subdivision":
        group_col = LoadBooking.subdivision
    elif lvl == "section":
        group_col = LoadBooking.section
    else:
        lvl = "circle"
        group_col = LoadBooking.circle

    q = db.query(
        group_col.label("label"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Hooking", LoadBooking.booked_load), else_=0.0)), 0.0).label("hooking"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Meter Tamper", LoadBooking.booked_load), else_=0.0)), 0.0).label("meter_tamper"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Bypass", LoadBooking.booked_load), else_=0.0)), 0.0).label("bypass"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Misuse", LoadBooking.booked_load), else_=0.0)), 0.0).label("misuse"),
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load"),
        func.count(LoadBooking.id).label("total_cases")
    ).outerjoin(Team, LoadBooking.team_id == Team.id)\
     .filter(
        LoadBooking.booking_date.between(from_date, to_date),
        or_(LoadBooking.team_id == None, (Team.has_vehicle == True) & (Team.is_office_team == False)),
        group_col != None,
        group_col != ""
    )

    if c_upper:
        q = apply_circle_filter(q, LoadBooking.circle, c_upper)
    if division and division.strip():
        q = q.filter(LoadBooking.division == division.strip())
    if subdivision and subdivision.strip():
        q = q.filter(LoadBooking.subdivision == subdivision.strip())

    rows = q.group_by(group_col).order_by(func.sum(LoadBooking.booked_load).desc()).all()

    # Also compute squad-wise breakdown for parallel view mode
    tm_load_q = db.query(
        Team.name,
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Hooking", LoadBooking.booked_load), else_=0.0)), 0.0).label("hooking"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Meter Tamper", LoadBooking.booked_load), else_=0.0)), 0.0).label("meter_tamper"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Bypass", LoadBooking.booked_load), else_=0.0)), 0.0).label("bypass"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Misuse", LoadBooking.booked_load), else_=0.0)), 0.0).label("misuse"),
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load"),
        func.count(LoadBooking.id).label("total_cases")
    ).join(LoadBooking, Team.id == LoadBooking.team_id)\
     .filter(
        LoadBooking.booking_date.between(from_date, to_date),
        Team.has_vehicle == True,
        Team.is_office_team == False
    )
    if c_upper:
        tm_load_q = apply_circle_filter(tm_load_q, Team.circle, c_upper)
    tm_load_rows = tm_load_q.group_by(Team.id, Team.name).order_by(func.sum(LoadBooking.booked_load).desc()).limit(20).all()

    return {
        "level": lvl,
        "selected_circle": c_upper,
        "selected_division": division,
        "selected_subdivision": subdivision,
        "labels": [r[0] for r in rows],
        "hooking": [round(float(r[1]), 2) for r in rows],
        "meter_tamper": [round(float(r[2]), 2) for r in rows],
        "bypass": [round(float(r[3]), 2) for r in rows],
        "misuse": [round(float(r[4]), 2) for r in rows],
        "totals": [round(float(r[5]), 2) for r in rows],
        "cases": [int(r[6]) for r in rows],
        "team_load": {
            "labels": [r[0] for r in tm_load_rows],
            "hooking": [round(float(r[1]), 2) for r in tm_load_rows],
            "meter_tamper": [round(float(r[2]), 2) for r in tm_load_rows],
            "bypass": [round(float(r[3]), 2) for r in tm_load_rows],
            "misuse": [round(float(r[4]), 2) for r in tm_load_rows],
            "totals": [round(float(r[5]), 2) for r in tm_load_rows],
            "cases": [int(r[6]) for r in tm_load_rows]
        }
    }

@router.get("/charts/load-booking")
def get_charts_load_booking(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Circle-wise & Team-wise Load Booking breakdown by theft type (Hooking, Meter Tamper, Bypass, Misuse).
    Database-side aggregated via func.sum and case expressions. Excludes Office Teams.
    """
    c_upper = normalize_circle(circle)

    # Circle-wise Load Booking with theft type breakdown (excluding Office Teams)
    c_load_q = db.query(
        LoadBooking.circle,
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Hooking", LoadBooking.booked_load), else_=0.0)), 0.0).label("hooking"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Meter Tamper", LoadBooking.booked_load), else_=0.0)), 0.0).label("meter_tamper"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Bypass", LoadBooking.booked_load), else_=0.0)), 0.0).label("bypass"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Misuse", LoadBooking.booked_load), else_=0.0)), 0.0).label("misuse"),
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load")
    ).outerjoin(Team, LoadBooking.team_id == Team.id)\
     .filter(
        LoadBooking.booking_date.between(from_date, to_date),
        or_(LoadBooking.team_id == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    c_load_q = apply_circle_filter(c_load_q, LoadBooking.circle, c_upper)
    c_load_rows = c_load_q.group_by(LoadBooking.circle).order_by(func.sum(LoadBooking.booked_load).desc()).all()

    # Team-wise Load Booking with theft type breakdown (Field squads only)
    tm_load_q = db.query(
        Team.name,
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Hooking", LoadBooking.booked_load), else_=0.0)), 0.0).label("hooking"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Meter Tamper", LoadBooking.booked_load), else_=0.0)), 0.0).label("meter_tamper"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Bypass", LoadBooking.booked_load), else_=0.0)), 0.0).label("bypass"),
        func.coalesce(func.sum(case((LoadBooking.theft_type == "Misuse", LoadBooking.booked_load), else_=0.0)), 0.0).label("misuse"),
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load")
    ).join(LoadBooking, Team.id == LoadBooking.team_id)\
     .filter(
        LoadBooking.booking_date.between(from_date, to_date),
        Team.has_vehicle == True,
        Team.is_office_team == False
    )
    tm_load_q = apply_circle_filter(tm_load_q, Team.circle, c_upper)
    tm_load_rows = tm_load_q.group_by(Team.id, Team.name).order_by(func.sum(LoadBooking.booked_load).desc()).limit(15).all()

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "circle_load": {
            "labels": [r[0] for r in c_load_rows],
            "hooking": [round(float(r[1]), 2) for r in c_load_rows],
            "meter_tamper": [round(float(r[2]), 2) for r in c_load_rows],
            "bypass": [round(float(r[3]), 2) for r in c_load_rows],
            "misuse": [round(float(r[4]), 2) for r in c_load_rows],
            "totals": [round(float(r[5]), 2) for r in c_load_rows]
        },
        "team_load": {
            "labels": [r[0] for r in tm_load_rows],
            "hooking": [round(float(r[1]), 2) for r in tm_load_rows],
            "meter_tamper": [round(float(r[2]), 2) for r in tm_load_rows],
            "bypass": [round(float(r[3]), 2) for r in tm_load_rows],
            "misuse": [round(float(r[4]), 2) for r in tm_load_rows],
            "totals": [round(float(r[5]), 2) for r in tm_load_rows]
        }
    }

@router.get("/charts/collections")
def get_charts_collections(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Circle-wise & Team-wise Collections (INR).
    Database-side aggregated via func.sum. Excludes Office Teams.
    """
    c_upper = normalize_circle(circle)

    # Circle-wise Collection (INR) - excluding Office Teams
    c_coll_q = db.query(
        Collection.circle,
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("amount")
    ).outerjoin(Team, Collection.team_name == Team.name)\
     .filter(
        Collection.payment_date.between(from_date, to_date),
        or_(Collection.team_name == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    c_coll_q = apply_circle_filter(c_coll_q, Collection.circle, c_upper)
    c_coll_rows = c_coll_q.group_by(Collection.circle).order_by(func.sum(Collection.amount_paid).desc()).all()

    # Team-wise Collection (INR) - Field squads only
    tm_coll_q = db.query(
        Team.name,
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("amount")
    ).join(Collection, Collection.team_name == Team.name)\
     .filter(
        Collection.payment_date.between(from_date, to_date),
        Team.has_vehicle == True,
        Team.is_office_team == False
    )
    tm_coll_q = apply_circle_filter(tm_coll_q, Team.circle, c_upper)
    tm_coll_rows = tm_coll_q.group_by(Team.id, Team.name).order_by(func.sum(Collection.amount_paid).desc()).limit(15).all()

    # Collector / Officer Realization (Top 20 and All)
    coll_officer_q = db.query(
        Collection.collected_by_name,
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("amount"),
        func.count(Collection.id).label("mr_count")
    ).filter(
        Collection.payment_date.between(from_date, to_date),
        Collection.collected_by_name != None,
        Collection.collected_by_name != ""
    )
    if c_upper:
        coll_officer_q = apply_circle_filter(coll_officer_q, Collection.circle, c_upper)
    officer_rows_all = coll_officer_q.group_by(Collection.collected_by_name).order_by(func.sum(Collection.amount_paid).desc()).all()
    officer_rows_top20 = officer_rows_all[:20]

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "circle_collection": {
            "labels": [r[0] for r in c_coll_rows],
            "amounts": [round(float(r[1]), 2) for r in c_coll_rows]
        },
        "collector_collection_top20": {
            "labels": [r[0] for r in officer_rows_top20],
            "amounts": [round(float(r[1]), 2) for r in officer_rows_top20],
            "mr_counts": [int(r[2]) for r in officer_rows_top20]
        },
        "collector_collection_all": {
            "labels": [r[0] for r in officer_rows_all],
            "amounts": [round(float(r[1]), 2) for r in officer_rows_all],
            "mr_counts": [int(r[2]) for r in officer_rows_all]
        },
        "team_collection": {
            "labels": [r[0] for r in tm_coll_rows],
            "amounts": [round(float(r[1]), 2) for r in tm_coll_rows]
        }
    }

@router.get("/charts/collectors")
def get_charts_collectors(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    limit: Optional[int] = 20,
    db: Session = Depends(get_db)
):
    """
    Returns Collecting Officers / Collectors realization performance.
    Default limit is 20 for Top Performers; limit=0 or None returns all officers.
    """
    c_upper = normalize_circle(circle)
    q = db.query(
        Collection.collected_by_name,
        func.coalesce(func.sum(Collection.amount_paid), 0.0).label("amount"),
        func.count(Collection.id).label("mr_count")
    ).filter(
        Collection.payment_date.between(from_date, to_date),
        Collection.collected_by_name != None,
        Collection.collected_by_name != ""
    )
    if c_upper:
        q = apply_circle_filter(q, Collection.circle, c_upper)
    q = q.group_by(Collection.collected_by_name).order_by(func.sum(Collection.amount_paid).desc())
    if limit and limit > 0:
        q = q.limit(limit)
    rows = q.all()
    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "labels": [r[0] for r in rows],
        "amounts": [round(float(r[1]), 2) for r in rows],
        "mr_counts": [int(r[2]) for r in rows]
    }

@router.get("/charts/disconnections")
def get_charts_disconnections(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Circle-wise & Team-wise Disconnections Count and Amounts (INR).
    Database-side aggregated via func.count and func.sum. Excludes Office Teams.
    """
    c_upper = normalize_circle(circle)

    # Circle-wise DC (excluding Office Teams)
    c_dc_q = db.query(
        VCRMaster.circle,
        func.count(DisconnectionRecord.id).label("count"),
        func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0).label("amount")
    ).join(DisconnectionRecord, VCRMaster.vcr_number == DisconnectionRecord.vcr_number)\
     .outerjoin(Team, DisconnectionRecord.team_id == Team.id)\
     .filter(
        DisconnectionRecord.dc_date.between(from_date, to_date),
        or_(DisconnectionRecord.team_id == None, (Team.has_vehicle == True) & (Team.is_office_team == False))
    )
    c_dc_q = apply_circle_filter(c_dc_q, VCRMaster.circle, c_upper)
    c_dc_rows = c_dc_q.group_by(VCRMaster.circle).all()

    # Team-wise DC (Field squads only)
    tm_dc_q = db.query(
        Team.name,
        func.count(DisconnectionRecord.id).label("count"),
        func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0).label("amount")
    ).join(DisconnectionRecord, Team.id == DisconnectionRecord.team_id)\
     .filter(
        DisconnectionRecord.dc_date.between(from_date, to_date),
        Team.has_vehicle == True,
        Team.is_office_team == False
    )
    tm_dc_q = apply_circle_filter(tm_dc_q, Team.circle, c_upper)
    tm_dc_rows = tm_dc_q.group_by(Team.id, Team.name).limit(15).all()

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "circle_dc": {
            "labels": [r[0] for r in c_dc_rows],
            "counts": [int(r[1]) for r in c_dc_rows],
            "amounts": [round(float(r[2]), 2) for r in c_dc_rows]
        },
        "team_dc": {
            "labels": [r[0] for r in tm_dc_rows],
            "counts": [int(r[1]) for r in tm_dc_rows],
            "amounts": [round(float(r[2]), 2) for r in tm_dc_rows]
        }
    }


@router.get("/charts")
def get_charts(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Composite charts endpoint combining load booking, collection, and disconnection charts.
    """
    c_upper = normalize_circle(circle)

    lb = get_charts_load_booking(from_date=from_date, to_date=to_date, circle=c_upper, db=db)
    coll = get_charts_collections(from_date=from_date, to_date=to_date, circle=c_upper, db=db)
    dc = get_charts_disconnections(from_date=from_date, to_date=to_date, circle=c_upper, db=db)

    return {
        "circle_load": lb["circle_load"],
        "team_load": lb["team_load"],
        "circle_collection": coll["circle_collection"],
        "team_collection": coll["team_collection"],
        "circle_dc": dc["circle_dc"],
        "team_dc": dc["team_dc"]
    }

@router.get("/team-operations-status")
@router.get("/daily-operations-status")
def get_team_operations_status(
    op_date: Optional[date] = None,
    date: Optional[date] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns daily operational status table for each active squad on target date.
    Public and unrestricted for all viewers.
    Includes mini status summary counters for badges:
    - Active with TL
    - Collection without TL
    - Merged
    - Non-Operational
    """
    from datetime import date as date_type
    target_date = op_date or date or to_date or from_date or date_type.today()
    c_upper = normalize_circle(circle)

    t_q = db.query(Team).filter(Team.is_active == True)
    t_q = apply_circle_filter(t_q, Team.circle, c_upper)
    teams = t_q.options(joinedload(Team.default_tl)).order_by(Team.circle, Team.name).all()

    counts = {
        "INDEPENDENT_WITH_TL": 0,
        "INDEPENDENT_WITHOUT_TL_COLLECTION": 0,
        "MERGED": 0,
        "OFFICE_DUTY_NO_VEHICLE": 0,
        "NON_OPERATIONAL": 0,
        "UNREPORTED": 0
    }

    rows = []
    for idx, t in enumerate(teams, start=1):
        op = db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == target_date,
            DailyTeamOperation.team_id == t.id
        ).first()

        is_office = bool(t.is_office_team or not t.has_vehicle)
        if op:
            mode = op.operation_mode
        elif is_office:
            mode = "OFFICE_DUTY_NO_VEHICLE"
        else:
            mode = "UNREPORTED"
            
        counts[mode] = counts.get(mode, 0) + 1

        tl_name = strip_emp_code(t.assigned_team_lead) or "N/A"
        if op and op.daily_tl:
            tl_name = op.daily_tl.name
        elif op and op.tl_name:
            tl_name = strip_emp_code(op.tl_name)
        elif t.default_tl:
            tl_name = t.default_tl.name

        merged_target = "-"
        if op and op.merged_with_team:
            merged_target = op.merged_with_team.name

        if op and op.remarks:
            remarks = op.remarks
        elif is_office:
            remarks = "Office / Administrative Duty Only (No Vehicle Assigned)"
        else:
            remarks = "-"

        rows.append({
            "sl_no": idx,
            "team_id": t.id,
            "team_name": t.name,
            "circle": t.circle,
            "operated_by_tl": tl_name,
            "mode": mode,
            "merged_with_team": merged_target,
            "remarks": remarks,
            "has_vehicle": t.has_vehicle,
            "is_office_team": t.is_office_team,
            "is_office": is_office
        })

    return {
        "date": str(target_date),
        "circle": c_upper or "ALL CIRCLES",
        "counts": counts,
        "rows": rows
    }

def build_squad_performance(from_date: date, to_date: date, circle: Optional[str], db: Session) -> dict:
    """
    Squad Performance Summary Table computed directly inside the database:
    - Assigned Load Booked (kW)
    - Amount Collected (₹)
    - No. of DC Done
    - Amount Involving in DC (₹)
    - KM Run (Period)
    - Merged Squad status handling
    - Office Squads (Without Vehicle) strictly excluded from field credit (set to 0.0)
    """
    c_upper = normalize_circle(circle)
    t_q = db.query(Team).filter(Team.is_active == True)
    t_q = apply_circle_filter(t_q, Team.circle, c_upper)
    teams = t_q.options(joinedload(Team.default_tl)).order_by(Team.circle, Team.name).all()

    # 1. Load booking per team
    lb_agg = dict(db.query(
        LoadBooking.team_id,
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0)
    ).filter(LoadBooking.booking_date.between(from_date, to_date))
     .group_by(LoadBooking.team_id).all())

    # 2. Collection per team_name (matched directly from collections table)
    coll_agg = dict(db.query(
        Collection.team_name,
        func.coalesce(func.sum(Collection.amount_paid), 0.0)
    ).filter(Collection.payment_date.between(from_date, to_date))
     .group_by(Collection.team_name).all())

    # 3. DC per team
    dc_agg = db.query(
        DisconnectionRecord.team_id,
        func.count(DisconnectionRecord.id).label("count"),
        func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0).label("amount")
    ).filter(DisconnectionRecord.dc_date.between(from_date, to_date))\
     .group_by(DisconnectionRecord.team_id).all()
    dc_map = {r[0]: (r[1], float(r[2])) for r in dc_agg}

    # 4. KM Run per team
    km_agg = dict(db.query(
        VehicleLogBook.team_id,
        func.coalesce(func.sum(VehicleLogBook.run_km), 0)
    ).filter(VehicleLogBook.date.between(from_date, to_date))
     .group_by(VehicleLogBook.team_id).all())

    lb_cases_agg = dict(db.query(
        LoadBooking.team_id,
        func.count(LoadBooking.id)
    ).filter(LoadBooking.booking_date.between(from_date, to_date))
     .group_by(LoadBooking.team_id).all())

    emp_counts = dict(db.query(
        Employee.team_id,
        func.count(Employee.id)
    ).filter(Employee.is_active == True).group_by(Employee.team_id).all())

    # Mini counters
    counts = {
        "INDEPENDENT_WITH_TL": 0,
        "INDEPENDENT_WITHOUT_TL_COLLECTION": 0,
        "MERGED": 0,
        "OFFICE_DUTY_NO_VEHICLE": 0,
        "NON_OPERATIONAL": 0,
        "UNREPORTED": 0
    }

    # Batch query daily operations and attendance on to_date
    team_ids = [t.id for t in teams]
    ops = (
        db.query(DailyTeamOperation)
        .options(
            joinedload(DailyTeamOperation.daily_tl),
            joinedload(DailyTeamOperation.merged_with_team)
        )
        .filter(
            DailyTeamOperation.operation_date == to_date,
            DailyTeamOperation.team_id.in_(team_ids)
        )
        .all()
    ) if team_ids else []
    op_map = {op.team_id: op for op in ops}

    op_ids = [op.id for op in ops]
    att_present_map = {}
    att_wo_map = {}
    if op_ids:
        att_counts = (
            db.query(Attendance.operation_id, Attendance.status, func.count(Attendance.id))
            .filter(Attendance.operation_id.in_(op_ids))
            .group_by(Attendance.operation_id, Attendance.status)
            .all()
        )
        for op_id, status, count in att_counts:
            if status == "P":
                att_present_map[op_id] = count
            elif status == "WO":
                att_wo_map[op_id] = count
    rows = []
    for idx, t in enumerate(teams, start=1):
        latest_op = op_map.get(t.id)

        is_office = bool(t.is_office_team or not t.has_vehicle)
        if latest_op:
            mode = latest_op.operation_mode
        elif is_office:
            mode = "OFFICE_DUTY_NO_VEHICLE"
        else:
            mode = "UNREPORTED"
        counts[mode] = counts.get(mode, 0) + 1

        # Operated by TL (Active designated TL)
        operated_by_tl = "Unassigned"
        if latest_op and latest_op.daily_tl:
            operated_by_tl = latest_op.daily_tl.name
        elif latest_op and latest_op.tl_name:
            operated_by_tl = strip_emp_code(latest_op.tl_name)
        elif t.default_tl:
            operated_by_tl = t.default_tl.name
        elif t.assigned_team_lead:
            operated_by_tl = strip_emp_code(t.assigned_team_lead)

        # Form D Attendance (Accounting for P and WO counts)
        total_ba = emp_counts.get(t.id, 0)
        present_ba = att_present_map.get(latest_op.id, 0) if latest_op else 0
        wo_ba = att_wo_map.get(latest_op.id, 0) if latest_op else 0
        if total_ba > 0:
            if wo_ba == total_ba:
                form_d_display = f"0 / {total_ba} (All WO)"
            elif wo_ba > 0:
                form_d_display = f"{present_ba} / {total_ba} (WO: {wo_ba})"
            else:
                form_d_display = f"{present_ba} / {total_ba}"
        else:
            form_d_display = "- / -"

        merged_info = ""
        if mode == "MERGED" and latest_op and latest_op.merged_with_team:
            merged_info = f"Merged with {latest_op.merged_with_team.name}"

        if is_office:
            load_kw = 0.0
            load_cases = 0
            coll_inr = 0.0
            dc_count = 0
            dc_amount = 0.0
            run_km = 0
            load_display = "-"
            coll_display = "-"
            dc_display = "-"
            km_display = "-"
            remarks = latest_op.remarks if (latest_op and latest_op.remarks) else "Office / Administrative Duty Only"
        else:
            load_cases = lb_cases_agg.get(t.id, 0)
            load_kw = round(float(lb_agg.get(t.id, 0.0)), 2)
            coll_inr = round(float(coll_agg.get(t.name, 0.0)), 2)
            dc_count, dc_amount = dc_map.get(t.id, (0, 0.0))
            run_km = int(km_agg.get(t.id, 0))
            load_display = f"{load_cases} cases / {load_kw:.2f} kW" if (load_cases > 0 or load_kw > 0) else "0 cases / 0.0 kW"
            coll_display = f"₹ {coll_inr:,.2f}"
            dc_display = f"{dc_count} / ₹ {dc_amount:,.2f}"
            km_display = f"{run_km} KM"
            remarks = latest_op.remarks if (latest_op and latest_op.remarks) else "-"

        rows.append({
            "sl_no": idx,
            "team_id": t.id,
            "team_name": t.name,
            "circle": t.circle,
            "operated_by_tl": operated_by_tl,
            "permanent_tl": strip_emp_code(t.assigned_team_lead) or "N/A",
            "operation_mode": mode,
            "merged_status": merged_info,
            "form_d_attendance": form_d_display,
            "form_d_present": present_ba,
            "form_d_wo": wo_ba,
            "total_ba": total_ba,
            "theft_cases": load_cases,
            "load_booked_kw": load_kw,
            "load_display": load_display,
            "amount_collected": coll_inr,
            "coll_display": coll_display,
            "dc_count": dc_count,
            "dc_amount": round(dc_amount, 2),
            "dc_display": dc_display,
            "km_run": run_km,
            "km_display": km_display,
            "remarks": remarks,
            "has_vehicle": t.has_vehicle,
            "is_office_team": t.is_office_team,
            "is_office": is_office
        })

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "counts": counts,
        "rows": rows
    }


@router.get("/squad-performance")
def get_squad_performance(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return build_squad_performance(from_date, to_date, circle, db)


# =====================================================================
# UNIFIED BREAKDOWN API  (Load Booking / DC / Collection)
# Levels: circle -> division -> subdivision -> section, plus team & collector
# Sized for 6 circles / 19 divisions / 60 subdivisions / 150 sections /
# 60 teams / 200 collectors: everything aggregated in SQL, all rows returned.
# =====================================================================
HIERARCHY_LEVELS = ("circle", "division", "subdivision", "section")
PARENT_LEVEL = {"division": "circle", "subdivision": "division", "section": "subdivision"}
THEFT_KEYS = (("hooking", "Hooking"), ("meter_tamper", "Meter Tamper"), ("bypass", "Bypass"), ("misuse", "Misuse"))


def _resolve_col(models, name):
    """First model in `models` that has a mapped column `name` (None if none has it)."""
    for m in models:
        col = getattr(m, name, None)
        if col is not None and hasattr(col, "property"):
            return col
    return None


def _field_squad_only(team_fk_col):
    """Rows without a team, or rows of field squads (vehicle, not office)."""
    return or_(team_fk_col == None, (Team.has_vehicle == True) & (Team.is_office_team == False))


@router.get("/charts/breakdown")
def get_charts_breakdown(
    metric: str = Query("load", description="load | dc | collection"),
    level: str = Query("circle", description="circle | division | subdivision | section | team | collector"),
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    division: Optional[str] = None,
    subdivision: Optional[str] = None,
    db: Session = Depends(get_db)
):
    metric = (metric or "load").strip().lower()
    lvl = (level or "circle").strip().lower()
    c_upper = normalize_circle(circle)

    # ---- metric definitions -------------------------------------------------
    if metric == "load":
        hier_models = (LoadBooking,)
        values = [
            func.coalesce(func.sum(case((LoadBooking.theft_type == lbl, LoadBooking.booked_load), else_=0.0)), 0.0).label(key)
            for key, lbl in THEFT_KEYS
        ] + [
            func.coalesce(func.sum(LoadBooking.booked_load), 0.0).label("total_load"),
            func.count(LoadBooking.id).label("cases"),
        ]
        order_expr = func.coalesce(func.sum(LoadBooking.booked_load), 0.0).desc()

        def base(cols):
            return db.query(*cols).select_from(LoadBooking)\
                .outerjoin(Team, LoadBooking.team_id == Team.id)\
                .filter(LoadBooking.booking_date.between(from_date, to_date),
                        _field_squad_only(LoadBooking.team_id))
    elif metric == "dc":
        hier_models = (DisconnectionRecord, VCRMaster)
        values = [
            func.count(DisconnectionRecord.id).label("dc_count"),
            func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0).label("dc_amount"),
        ]
        order_expr = func.count(DisconnectionRecord.id).desc()

        def base(cols):
            return db.query(*cols).select_from(DisconnectionRecord)\
                .outerjoin(Team, DisconnectionRecord.team_id == Team.id)\
                .outerjoin(VCRMaster, DisconnectionRecord.vcr_number == VCRMaster.vcr_number)\
                .filter(DisconnectionRecord.dc_date.between(from_date, to_date),
                        _field_squad_only(DisconnectionRecord.team_id))
    elif metric == "collection":
        hier_models = (Collection,)
        values = [
            func.coalesce(func.sum(Collection.amount_paid), 0.0).label("amount"),
            func.count(Collection.id).label("mr_count"),
        ]
        order_expr = func.coalesce(func.sum(Collection.amount_paid), 0.0).desc()

        def base(cols, field_only=True):
            q = db.query(*cols).select_from(Collection)\
                .outerjoin(Team, Collection.team_name == Team.name)\
                .filter(Collection.payment_date.between(from_date, to_date))
            if field_only:
                q = q.filter(_field_squad_only(Collection.team_name))
            return q
    else:
        raise HTTPException(status_code=400, detail="metric must be load, dc or collection")

    available = [l for l in HIERARCHY_LEVELS if _resolve_col(hier_models, l) is not None] + ["team"]
    if metric == "collection":
        available.append("collector")
    if lvl not in available:
        raise HTTPException(status_code=400, detail=f"level '{lvl}' not available for {metric}; available: {available}")

    # ---- grouping columns ----------------------------------------------------
    if lvl == "team":
        group_col, parent_col = Team.name, Team.circle
    elif lvl == "collector":
        group_col, parent_col = Collection.collected_by_name, (_resolve_col(hier_models, "team_name") or Collection.circle)
    else:
        group_col = _resolve_col(hier_models, lvl)
        parent_col = _resolve_col(hier_models, PARENT_LEVEL[lvl]) if lvl in PARENT_LEVEL else None

    cols = [group_col.label("label")]
    if parent_col is not None:
        cols.append(parent_col.label("parent"))
    cols += values

    # Collector view keeps original semantics (all collectors incl. office counters)
    q = base(cols, field_only=False) if lvl == "collector" else base(cols)
    q = q.filter(group_col != None, group_col != "")

    circle_col = _resolve_col(hier_models, "circle")
    if c_upper and circle_col is not None:
        q = apply_circle_filter(q, circle_col, c_upper)
    div_col = _resolve_col(hier_models, "division")
    if division and division.strip() and div_col is not None:
        q = q.filter(div_col == division.strip())
    sub_col = _resolve_col(hier_models, "subdivision")
    if subdivision and subdivision.strip() and sub_col is not None:
        q = q.filter(sub_col == subdivision.strip())

    group_by = [group_col] + ([parent_col] if parent_col is not None else [])
    result = q.group_by(*group_by).order_by(order_expr).all()

    rows, totals = [], {}
    for r in result:
        m = r._mapping
        row = {"label": str(m["label"]), "parent": (str(m["parent"]) if parent_col is not None and m["parent"] is not None else None)}
        if metric == "load":
            for key, _ in THEFT_KEYS:
                row[key] = round(float(m[key] or 0), 2)
            row["total_load"] = round(float(m["total_load"] or 0), 2)
            row["others"] = round(max(0.0, row["total_load"] - sum(row[k] for k, _ in THEFT_KEYS)), 2)
            row["cases"] = int(m["cases"] or 0)
        elif metric == "dc":
            row["dc_count"] = int(m["dc_count"] or 0)
            row["dc_amount"] = round(float(m["dc_amount"] or 0), 2)
        else:
            row["amount"] = round(float(m["amount"] or 0), 2)
            row["mr_count"] = int(m["mr_count"] or 0)
        rows.append(row)
        for k, v in row.items():
            if k not in ("label", "parent"):
                totals[k] = round(totals.get(k, 0) + v, 2)

    return {
        "metric": metric,
        "level": lvl,
        "available_levels": available,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "division": division,
        "subdivision": subdivision,
        "count": len(rows),
        "totals": totals,
        "rows": rows,
    }


# =====================================================================
# EXCEL: Daily Squad Operations & Performance Summary
# =====================================================================
MODE_LABELS = {
    "INDEPENDENT_WITH_TL": ("Active with TL", "E8F5E9", "1B5E20"),
    "INDEPENDENT_WITHOUT_TL_COLLECTION": ("Collection Only", "E3F2FD", "0D47A1"),
    "MERGED": ("Merged", "FFF8E1", "8D6E00"),
    "OFFICE_DUTY_NO_VEHICLE": ("Office Duty (No Vehicle)", "ECEFF1", "37474F"),
    "NON_OPERATIONAL": ("Non-Operational", "FFEBEE", "B71C1C"),
    "UNREPORTED": ("Unreported", "FFFFFF", "757575"),
}


@router.get("/squad-performance/export")
def export_squad_performance(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    data = build_squad_performance(from_date, to_date, circle, db)
    rows = data["rows"]
    period = str(from_date) if from_date == to_date else f"{from_date} to {to_date}"
    circle_txt = data["circle"]

    INR = '[>=10000000]"₹ "##\\,##\\,##\\,##0;[>=100000]"₹ "##\\,##\\,##0;"₹ "#,##0'
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="0B2545")
    total_fill = PatternFill("solid", fgColor="DCE6F2")
    white_bold = Font(bold=True, color="FFFFFF", size=11)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Squad Summary"

    headers = [
        ("Sl", 6, None), ("Squad Name", 24, None), ("Circle", 16, None), ("Operated By (TL)", 28, None),
        ("Permanent TL", 22, None), ("Operational Mode", 22, None), ("Merged Status", 22, None),
        ("Form D Attendance", 13, None), ("Vehicle Run (KM)", 11, "0"), ("Theft Cases", 10, "0"),
        ("Load Booked (kW)", 13, "#,##0.00"), ("DC Count", 9, "0"), ("DC Arrears (₹)", 16, INR),
        ("Collection (₹)", 16, INR), ("Remarks", 40, None),
    ]
    ncol = len(headers)
    last_col = get_column_letter(ncol)

    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = "TPSODL ENFORCEMENT — DAILY SQUAD OPERATIONS & PERFORMANCE SUMMARY"
    ws["A1"].font = Font(bold=True, size=15, color="FFFFFF")
    ws["A1"].fill = head_fill
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"] = f"Period: {period}     |     Circle: {circle_txt}     |     Generated: {datetime.now():%d-%b-%Y %H:%M}"
    ws["A2"].font = Font(bold=True, size=11, color="0B2545")

    c = data["counts"]
    ws.merge_cells(f"A3:{last_col}3")
    ws["A3"] = ("Active with TL: {a}   •   Collection Only: {b}   •   Merged: {m}   •   Office (No Vehicle): {o}"
                "   •   Non-Operational: {n}   •   Unreported: {u}").format(
        a=c.get("INDEPENDENT_WITH_TL", 0), b=c.get("INDEPENDENT_WITHOUT_TL_COLLECTION", 0), m=c.get("MERGED", 0),
        o=c.get("OFFICE_DUTY_NO_VEHICLE", 0), n=c.get("NON_OPERATIONAL", 0), u=c.get("UNREPORTED", 0))
    ws["A3"].font = Font(size=10, color="374151")

    HR = 5
    for i, (title, width, _) in enumerate(headers, start=1):
        cell = ws.cell(row=HR, column=i, value=title)
        cell.font, cell.fill, cell.alignment, cell.border = white_bold, head_fill, center, border
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[HR].height = 32

    first = HR + 1
    for idx, r in enumerate(rows):
        rr = first + idx
        office = r.get("is_office")
        mode_label, bg, fg = MODE_LABELS.get(r["operation_mode"], (r["operation_mode"], "FFFFFF", "000000"))
        vals = [
            idx + 1, r["team_name"], r["circle"], r["operated_by_tl"], r.get("permanent_tl"), mode_label,
            r.get("merged_status") or "", r.get("form_d_attendance"),
            None if office else r["km_run"], None if office else r["theft_cases"],
            None if office else r["load_booked_kw"], None if office else r["dc_count"],
            None if office else r["dc_amount"], None if office else r["amount_collected"], r.get("remarks") or "",
        ]
        for ci, v in enumerate(vals, start=1):
            cell = ws.cell(row=rr, column=ci, value=v)
            cell.border = border
            fmt = headers[ci - 1][2]
            if fmt:
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif ci in (1, 8):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(vertical="center", wrap_text=(ci == ncol))
            if idx % 2 == 1:
                cell.fill = PatternFill("solid", fgColor="F8FAFC")
        mode_cell = ws.cell(row=rr, column=6)
        mode_cell.fill = PatternFill("solid", fgColor=bg)
        mode_cell.font = Font(bold=True, color=fg)
        ws.cell(row=rr, column=2).font = Font(bold=True)

    last = first + len(rows) - 1
    tr = last + 1
    ws.cell(row=tr, column=2, value=f"TOTAL ({len(rows)} squads)")
    for ci in range(1, ncol + 1):
        cell = ws.cell(row=tr, column=ci)
        cell.fill, cell.border = total_fill, border
        cell.font = Font(bold=True, color="0B2545")
        fmt = headers[ci - 1][2]
        if fmt and rows:
            col = get_column_letter(ci)
            cell.value = f"=SUM({col}{first}:{col}{last})"
            cell.number_format = fmt
            cell.alignment = Alignment(horizontal="right")

    ws.freeze_panes = ws.cell(row=first, column=3)
    if rows:
        ws.auto_filter.ref = f"A{HR}:{last_col}{last}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HR}:{HR}"

    # ---- Sheet 2: circle-wise roll-up (live formulas over sheet 1) ----
    cs = wb.create_sheet("Circle Summary")
    cs["A1"] = f"CIRCLE-WISE SQUAD SUMMARY — {period} ({circle_txt})"
    cs["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    cs["A1"].fill = head_fill
    cs.row_dimensions[1].height = 28
    sheads = ["Circle", "Squads", "Active with TL", "Collection Only", "Merged", "Non-Op", "Unreported",
              "KM Run", "Theft Cases", "Load (kW)", "DC Count", "DC Arrears (₹)", "Collection (₹)"]
    sfmt = [None, "0", "0", "0", "0", "0", "0", "0", "0", "#,##0.00", "0", INR, INR]
    cs.merge_cells("A1:M1")
    for i, h in enumerate(sheads, start=1):
        cell = cs.cell(row=3, column=i, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = white_bold, head_fill, center, border
        cs.column_dimensions[get_column_letter(i)].width = 18 if i == 1 else 14
    cs.row_dimensions[3].height = 30

    circles = sorted({r["circle"] for r in rows if r.get("circle")})
    S = "'Squad Summary'!"
    rng = lambda col: f"{S}${col}${first}:${col}${max(last, first)}"
    for k, circ in enumerate(circles):
        rr = 4 + k
        crit = f"{rng('C')},$A{rr}"
        formulas = [
            circ,
            f"=COUNTIF({crit})",
            f'=COUNTIFS({crit},{rng("F")},"Active with TL")',
            f'=COUNTIFS({crit},{rng("F")},"Collection Only")',
            f'=COUNTIFS({crit},{rng("F")},"Merged")',
            f'=COUNTIFS({crit},{rng("F")},"Non-Operational")',
            f'=COUNTIFS({crit},{rng("F")},"Unreported")',
            f"=SUMIF({crit},{rng('I')})", f"=SUMIF({crit},{rng('J')})", f"=SUMIF({crit},{rng('K')})",
            f"=SUMIF({crit},{rng('L')})", f"=SUMIF({crit},{rng('M')})", f"=SUMIF({crit},{rng('N')})",
        ]
        for ci, v in enumerate(formulas, start=1):
            cell = cs.cell(row=rr, column=ci, value=v)
            cell.border = border
            if sfmt[ci - 1]:
                cell.number_format = sfmt[ci - 1]
        cs.cell(row=rr, column=1).font = Font(bold=True)
    trow = 4 + len(circles)
    cs.cell(row=trow, column=1, value="TOTAL")
    for ci in range(1, len(sheads) + 1):
        cell = cs.cell(row=trow, column=ci)
        cell.fill, cell.border, cell.font = total_fill, border, Font(bold=True, color="0B2545")
        if ci > 1 and circles:
            col = get_column_letter(ci)
            cell.value = f"=SUM({col}4:{col}{trow - 1})"
            cell.number_format = sfmt[ci - 1]
    cs.freeze_panes = "B4"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"TPSODL_Squad_Performance_{period.replace(' ', '_')}_{circle_txt.replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
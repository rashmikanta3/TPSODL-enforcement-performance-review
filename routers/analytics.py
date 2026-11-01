from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
from database import get_db
from models import (
    LoadBooking, Collection, DisconnectionRecord, VCRMaster,
    Team, Employee, DailyTeamOperation, VehicleLogBook
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

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "circle_collection": {
            "labels": [r[0] for r in c_coll_rows],
            "amounts": [round(float(r[1]), 2) for r in c_coll_rows]
        },
        "team_collection": {
            "labels": [r[0] for r in tm_coll_rows],
            "amounts": [round(float(r[1]), 2) for r in tm_coll_rows]
        }
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
    teams = t_q.order_by(Team.circle, Team.name).all()

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

        tl_name = t.assigned_team_lead or "N/A"
        if op and op.daily_tl:
            tl_name = f"{op.daily_tl.name} ({op.daily_tl.tl_code})"
        elif op and op.tl_name:
            tl_name = op.tl_name
        elif t.default_tl:
            tl_name = f"{t.default_tl.name} ({t.default_tl.tl_code})"

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

@router.get("/squad-performance")
def get_squad_performance(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    circle: Optional[str] = None,
    db: Session = Depends(get_db)
):
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
    teams = t_q.order_by(Team.circle, Team.name).all()

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

    # 5. Check daily operation on to_date (or latest) for mode / merge
    rows = []
    for t in teams:
        latest_op = db.query(DailyTeamOperation).filter(
            DailyTeamOperation.operation_date == to_date,
            DailyTeamOperation.team_id == t.id
        ).first()

        is_office = bool(t.is_office_team or not t.has_vehicle)
        if is_office:
            mode = "OFFICE_DUTY_NO_VEHICLE"
            merged_info = ""
            load_kw = 0.0
            coll_inr = 0.0
            dc_count = 0
            dc_amount = 0.0
            run_km = 0
            remarks = latest_op.remarks if (latest_op and latest_op.remarks) else "Office / Administrative Duty Only"
        else:
            mode = latest_op.operation_mode if latest_op else "INDEPENDENT_WITH_TL"
            merged_info = ""
            if mode == "MERGED" and latest_op and latest_op.merged_with_team:
                merged_info = f"Merged with {latest_op.merged_with_team.name}"

            dc_count, dc_amount = dc_map.get(t.id, (0, 0.0))
            load_kw = round(float(lb_agg.get(t.id, 0.0)), 2)
            coll_inr = round(float(coll_agg.get(t.name, 0.0)), 2)
            run_km = int(km_agg.get(t.id, 0))
            remarks = latest_op.remarks if (latest_op and latest_op.remarks) else "-"

        rows.append({
            "team_id": t.id,
            "team_name": t.name,
            "circle": t.circle,
            "permanent_tl": t.assigned_team_lead or "N/A",
            "operation_mode": mode,
            "merged_status": merged_info,
            "load_booked_kw": load_kw,
            "amount_collected": coll_inr,
            "dc_count": dc_count,
            "dc_amount": round(dc_amount, 2),
            "km_run": run_km,
            "remarks": remarks,
            "has_vehicle": t.has_vehicle,
            "is_office_team": t.is_office_team,
            "is_office": is_office
        })

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "circle": c_upper or "ALL CIRCLES",
        "rows": rows
    }

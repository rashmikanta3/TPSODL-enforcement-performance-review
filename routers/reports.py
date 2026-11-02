import calendar
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from database import get_db
from models import (
    Employee, TeamLead, DailyTeamOperation, Attendance, Team,
    VehicleLogBook, LoadBooking, DisconnectionRecord, Collection
)
import reports_excel
import reports_pdf

router = APIRouter()

# =========================================================================
# HELPERS
# =========================================================================
def _month_range(year: int, month: int):
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


# =========================================================================
# 1. FORM D ATTENDANCE REGISTER  (employees listed team-wise, sorted)
# =========================================================================
@router.get("/form-d")
def export_form_d(
    circle_name: str,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    format: str = Query("excel", description="excel or pdf"),
    team_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    circle_up = circle_name.strip().upper()
    emp_q = db.query(Employee, Team.name.label("team_name"))\
        .outerjoin(Team, Employee.team_id == Team.id)\
        .filter(Employee.circle == circle_up, Employee.is_active == True)
    team_name = None
    team_lead = None
    if team_id:
        emp_q = emp_q.filter(Employee.team_id == team_id)
        t = db.query(Team).filter(Team.id == team_id).first()
        if t:
            team_name = t.name
            team_lead = t.assigned_team_lead

    # Team-wise order: all members of a team together, teams A-Z (unassigned last), names A-Z inside a team
    employees_db = emp_q.order_by(Team.name.is_(None), Team.name, Employee.name).all()
    if not employees_db:
        raise HTTPException(status_code=404, detail="No employees found for this circle/squad")

    emp_list = [
        {
            "id": e.id,
            "emp_code": e.emp_code,
            "name": e.name,
            "designation": e.designation or "Squad Member",
            "team_name": tm_name or "UNASSIGNED",
        }
        for e, tm_name in employees_db
    ]
    emp_ids = [e["id"] for e in emp_list]

    # Attendance for this month, keyed as (employee_id, "YYYY-MM-DD") which the PDF/Excel builders read
    month_start, month_end = _month_range(year, month)
    att_records = db.query(Attendance.employee_id, Attendance.status, DailyTeamOperation.operation_date)\
        .join(DailyTeamOperation, Attendance.operation_id == DailyTeamOperation.id)\
        .filter(
            Attendance.employee_id.in_(emp_ids),
            DailyTeamOperation.operation_date >= month_start,
            DailyTeamOperation.operation_date <= month_end,
        ).all()

    attendance_map = {}
    for emp_id, status, op_date in att_records:
        if status:
            attendance_map[(emp_id, op_date.strftime("%Y-%m-%d"))] = status

    # Populate Sundays as WO by default if missing
    _, num_days = calendar.monthrange(year, month)
    for day in range(1, num_days + 1):
        d_obj = date(year, month, day)
        if d_obj.weekday() == 6:  # Sunday
            key_date = d_obj.strftime("%Y-%m-%d")
            for emp_id in emp_ids:
                attendance_map.setdefault((emp_id, key_date), "WO")

    if format.lower() == "pdf":
        file_bytes = reports_pdf.build_form_d_pdf(
            circle_name=circle_up,
            year=year,
            month=month,
            employees=emp_list,
            attendance_map=attendance_map,
            team_lead=team_lead,
            team_name=team_name
        )
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Form_D_{circle_up}_{month}_{year}.pdf"}
        )
    else:
        file_bytes = reports_excel.build_form_d_excel(
            circle_name=circle_up,
            year=year,
            month=month,
            employees=emp_list,
            attendance_map=attendance_map,
            team_lead=team_lead,
            team_name=team_name
        )
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Form_D_{circle_up}_{month}_{year}.xlsx"}
        )


# =========================================================================
# 2. VEHICLE LOG SUMMARY
# =========================================================================
@router.get("/vehicle-log")
def export_vehicle_log(
    circle_name: str,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    format: str = Query("excel", description="excel or pdf"),
    team_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    circle_up = circle_name.strip().upper()

    if team_id:
        t = db.query(Team).filter(Team.id == team_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Team not found")
        
        logs = db.query(VehicleLogBook).filter(
            VehicleLogBook.team_id == team_id,
            extract('year', VehicleLogBook.date) == year,
            extract('month', VehicleLogBook.date) == month
        ).order_by(VehicleLogBook.date).all()

        daily_logs = [
            {
                "date": log.date,
                "vehicle_no": log.vehicle_no,
                "supervisor_name": log.supervisor_name or "",
                "start_km": log.start_km,
                "end_km": log.end_km,
                "run_km": log.run_km,
                "start_time": log.start_time or "",
                "end_time": log.end_time or "",
                "area_movement": log.area_movement or ""
            }
            for log in logs
        ]

        if format.lower() == "pdf":
            file_bytes = reports_pdf.build_team_log_pdf(
                team_name=t.name,
                circle=circle_up,
                team_lead=t.assigned_team_lead or "N/A",
                year=year,
                month=month,
                daily_logs=daily_logs
            )
            return Response(content=file_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Vehicle_Log_{t.name}_{month}_{year}.pdf"})
        else:
            file_bytes = reports_excel.build_team_log_excel(
                team_name=t.name,
                circle=circle_up,
                team_lead=t.assigned_team_lead or "N/A",
                year=year,
                month=month,
                daily_logs=daily_logs
            )
            return Response(content=file_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=Vehicle_Log_{t.name}_{month}_{year}.xlsx"})

    # Circle-wide vehicle log summary
    teams = db.query(Team).filter(Team.circle == circle_up, Team.is_active == True).all()
    rows = []
    grand_total_km = 0

    for idx, t in enumerate(teams, start=1):
        km_sum = db.query(func.coalesce(func.sum(VehicleLogBook.run_km), 0)).filter(
            VehicleLogBook.team_id == t.id,
            extract('year', VehicleLogBook.date) == year,
            extract('month', VehicleLogBook.date) == month
        ).scalar()

        latest_log = db.query(VehicleLogBook).filter(
            VehicleLogBook.team_id == t.id,
            extract('year', VehicleLogBook.date) == year,
            extract('month', VehicleLogBook.date) == month
        ).order_by(VehicleLogBook.date.desc()).first()

        veh_no = latest_log.vehicle_no if latest_log else "-"
        sup_name = latest_log.supervisor_name if latest_log else (t.supervisor_name or "-")

        rows.append({
            "sl_no": idx,
            "team_name": t.name,
            "vehicle_no": veh_no,
            "supervisor_name": sup_name,
            "assigned_team_lead": t.assigned_team_lead or "N/A",
            "total_km": int(km_sum)
        })
        grand_total_km += int(km_sum)

    if format.lower() == "pdf":
        file_bytes = reports_pdf.build_circle_log_pdf(
            circle_name=circle_up,
            year=year,
            month=month,
            rows=rows,
            total_km=grand_total_km
        )
        return Response(content=file_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Circle_Vehicle_Summary_{circle_up}_{month}_{year}.pdf"})
    else:
        file_bytes = reports_excel.build_circle_log_excel(
            circle_name=circle_up,
            year=year,
            month=month,
            rows=rows,
            total_km=grand_total_km
        )
        return Response(content=file_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=Circle_Vehicle_Summary_{circle_up}_{month}_{year}.xlsx"})

# =========================================================================
# 3. SQUAD PERFORMANCE REGISTER  (one row per team for the month, no date column)
# =========================================================================
@router.get("/squad-performance")
def export_squad_performance(
    circle_name: str,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    format: str = Query("excel", description="excel or pdf"),
    db: Session = Depends(get_db)
):
    circle_up = circle_name.strip().upper()
    teams = db.query(Team).filter(Team.circle == circle_up, Team.is_active == True).order_by(Team.name).all()

    # Load Bookings by team
    lb_map = dict(db.query(
        LoadBooking.team_id,
        func.coalesce(func.sum(LoadBooking.booked_load), 0.0)
    ).filter(
        LoadBooking.circle == circle_up,
        extract('year', LoadBooking.booking_date) == year,
        extract('month', LoadBooking.booking_date) == month
    ).group_by(LoadBooking.team_id).all())

    # Collections by team_name
    coll_map = dict(db.query(
        Collection.team_name,
        func.coalesce(func.sum(Collection.amount_paid), 0.0)
    ).filter(
        Collection.circle == circle_up,
        extract('year', Collection.payment_date) == year,
        extract('month', Collection.payment_date) == month
    ).group_by(Collection.team_name).all())

    # DC by team
    dc_map = {
        r[0]: (r[1], float(r[2]))
        for r in db.query(
            DisconnectionRecord.team_id,
            func.count(DisconnectionRecord.id),
            func.coalesce(func.sum(DisconnectionRecord.amount_pending), 0.0)
        ).filter(
            extract('year', DisconnectionRecord.dc_date) == year,
            extract('month', DisconnectionRecord.dc_date) == month
        ).group_by(DisconnectionRecord.team_id).all()
    }

    # KM Run
    km_map = dict(db.query(
        VehicleLogBook.team_id,
        func.coalesce(func.sum(VehicleLogBook.run_km), 0)
    ).filter(
        extract('year', VehicleLogBook.date) == year,
        extract('month', VehicleLogBook.date) == month
    ).group_by(VehicleLogBook.team_id).all())

    # Employee present man-days by team (count of 'P' marks in the month)
    present_map = dict(db.query(
        Employee.team_id,
        func.count(Attendance.employee_id)
    ).join(Employee, Attendance.employee_id == Employee.id)
     .join(DailyTeamOperation, Attendance.operation_id == DailyTeamOperation.id)
     .filter(
        Employee.circle == circle_up,
        Attendance.status == "P",
        extract('year', DailyTeamOperation.operation_date) == year,
        extract('month', DailyTeamOperation.operation_date) == month
    ).group_by(Employee.team_id).all())

    performance_rows = []
    for idx, t in enumerate(teams, start=1):
        dc_count, dc_amt = dc_map.get(t.id, (0, 0.0))
        performance_rows.append({
            "sl_no": idx,
            "team_name": t.name,
            "assigned_team_lead": t.assigned_team_lead or "N/A",
            "supervisor_name": t.supervisor_name or "N/A",
            "load_booked_kw": round(float(lb_map.get(t.id, 0.0) or 0.0), 2),
            "amount_collected": round(float(coll_map.get(t.name, 0.0) or 0.0), 2),
            "dc_count": int(dc_count or 0),
            "dc_amount": round(dc_amt, 2),
            "km_run": int(km_map.get(t.id, 0) or 0),
            "emp_present_count": int(present_map.get(t.id, 0) or 0),
        })

    if format.lower() == "pdf":
        file_bytes = reports_pdf.build_team_performance_pdf(
            circle_name=circle_up,
            year=year,
            month=month,
            performance_rows=performance_rows
        )
        return Response(content=file_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Squad_Performance_{circle_up}_{month}_{year}.pdf"})
    else:
        file_bytes = reports_excel.build_team_performance_excel(
            circle_name=circle_up,
            year=year,
            month=month,
            performance_rows=performance_rows
        )
        return Response(content=file_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=Squad_Performance_{circle_up}_{month}_{year}.xlsx"})

# =========================================================================
# 4. MR COLLECTION REGISTER  (every MR entry of the month)
# =========================================================================
@router.get("/collection")
def export_collection(
    circle_name: str,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    format: str = Query("excel", description="excel or pdf"),
    db: Session = Depends(get_db)
):
    circle_up = circle_name.strip().upper()
    collections = db.query(Collection).filter(
        Collection.circle == circle_up,
        extract('year', Collection.payment_date) == year,
        extract('month', Collection.payment_date) == month
    ).order_by(Collection.payment_date, Collection.id).all()

    records = [
        {
            "vcr_number": c.vcr_number or "-",
            "mr_number": c.mr_number or "-",
            "payment_date": c.payment_date,
            "division": c.division or "-",
            "subdivision": c.subdivision or "-",
            "section": c.section or "-",
            "amount_paid": float(c.amount_paid or 0.0),
        }
        for c in collections
    ]

    if format.lower() == "pdf":
        file_bytes = reports_pdf.build_collection_pdf(
            circle_name=circle_up,
            year=year,
            month=month,
            records=records
        )
        return Response(content=file_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=MR_Collection_{circle_up}_{month}_{year}.pdf"})
    else:
        file_bytes = reports_excel.build_collection_excel(
            circle_name=circle_up,
            year=year,
            month=month,
            records=records
        )
        return Response(content=file_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=MR_Collection_{circle_up}_{month}_{year}.xlsx"})


# =========================================================================
# 6. LOAD BOOKING REGISTER (EXCEL & PDF) - every booking entry of the month
#    Pass year & month (defaults to current month). from_date / to_date, if
#    given, override the month and export that exact range instead.
# =========================================================================
def _load_booking_entries(db: Session, circle, year, month, from_date, to_date):
    q = db.query(
        LoadBooking,
        TeamLead.name.label("tl_name"),
        Team.name.label("team_name")
    )\
    .outerjoin(TeamLead, LoadBooking.tl_code == TeamLead.tl_code)\
    .outerjoin(Team, LoadBooking.team_id == Team.id)

    if circle and circle.strip().upper() not in ("ALL", ""):
        c_clean = circle.strip().upper()
        if c_clean == "CITY":
            c_clean = "BERHAMPUR CITY"
        q = q.filter(LoadBooking.circle == c_clean)

    if from_date or to_date:
        if from_date:
            q = q.filter(LoadBooking.booking_date >= from_date)
        if to_date:
            q = q.filter(LoadBooking.booking_date <= to_date)
        period_label = None
    else:
        year = year or date.today().year
        month = month or date.today().month
        m_start, m_end = _month_range(year, month)
        q = q.filter(LoadBooking.booking_date >= m_start, LoadBooking.booking_date <= m_end)
        period_label = f"{calendar.month_name[month].upper()} {year}"

    records_db = q.order_by(LoadBooking.booking_date.asc(), LoadBooking.id.asc()).all()

    bookings = [
        {
            "id": b.id,
            "booking_date": b.booking_date,
            "page_no": b.page_no or "-",
            "punch_emp": tl_name or b.tl_code or "N/A",
            "team_name": team_name or "Unassigned",
            "circle": b.circle,
            "division": b.division or "-",
            "subdivision": b.subdivision or "-",
            "section": b.section or "-",
            "pincode": b.pincode or "-",
            "theft_type": b.theft_type,
            "booked_load": b.booked_load,
            "status": b.status
        }
        for b, tl_name, team_name in records_db
    ]
    return bookings, period_label


def _lb_filename(circle, period_label, ext):
    tag = (period_label or str(date.today())).replace(" ", "_")
    return f"Load_Bookings_{(circle or 'ALL').upper()}_{tag}.{ext}"


@router.get("/load-bookings/excel")
def export_load_bookings_excel(
    circle: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Exports every load booking entry of the month to a protected Excel (.xlsx) register."""
    bookings, period_label = _load_booking_entries(db, circle, year, month, from_date, to_date)
    file_bytes = reports_excel.build_load_booking_excel(
        bookings=bookings,
        circle=circle,
        from_date=from_date,
        to_date=to_date,
        period_label=period_label
    )
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={_lb_filename(circle, period_label, 'xlsx')}"}
    )


@router.get("/load-bookings/pdf")
def export_load_bookings_pdf(
    circle: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Exports every load booking entry of the month to an A4 landscape PDF register."""
    bookings, period_label = _load_booking_entries(db, circle, year, month, from_date, to_date)
    file_bytes = reports_pdf.build_load_booking_pdf(
        bookings=bookings,
        circle=circle,
        from_date=from_date,
        to_date=to_date,
        period_label=period_label
    )
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={_lb_filename(circle, period_label, 'pdf')}"}
    )
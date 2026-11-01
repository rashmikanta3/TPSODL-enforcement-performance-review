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
# 1. FORM D ATTENDANCE REGISTER
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
    emp_q = db.query(Employee).filter(Employee.circle == circle_up, Employee.is_active == True)
    team_name = None
    team_lead = None
    if team_id:
        emp_q = emp_q.filter(Employee.team_id == team_id)
        t = db.query(Team).filter(Team.id == team_id).first()
        if t:
            team_name = t.name
            team_lead = t.assigned_team_lead

    employees_db = emp_q.order_by(Employee.name).all()
    if not employees_db:
        raise HTTPException(status_code=404, detail="No employees found for this circle/squad")

    emp_list = [
        {"id": e.id, "emp_code": e.emp_code, "name": e.name, "designation": e.designation or "Squad Member"}
        for e in employees_db
    ]
    emp_id_to_code = {e["id"]: e["emp_code"] for e in emp_list}

    # Fetch daily operations & attendance for this month
    ops = db.query(DailyTeamOperation).filter(
        extract('year', DailyTeamOperation.operation_date) == year,
        extract('month', DailyTeamOperation.operation_date) == month
    ).all()
    op_ids = [op.id for op in ops]

    attendance_map = {e["emp_code"]: {} for e in emp_list}
    if op_ids:
        att_records = db.query(Attendance, DailyTeamOperation.operation_date)\
            .join(DailyTeamOperation, Attendance.operation_id == DailyTeamOperation.id)\
            .filter(Attendance.operation_id.in_(op_ids)).all()

        for att, op_date in att_records:
            emp_code = emp_id_to_code.get(att.employee_id)
            if emp_code and emp_code in attendance_map:
                attendance_map[emp_code][op_date.day] = att.status

    # Populate Sundays as WO by default if missing
    _, num_days = calendar.monthrange(year, month)
    for day in range(1, num_days + 1):
        d_obj = date(year, month, day)
        if d_obj.weekday() == 6:  # Sunday
            for emp_code in attendance_map:
                if day not in attendance_map[emp_code]:
                    attendance_map[emp_code][day] = "WO"

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
# 3. SQUAD PERFORMANCE REGISTER
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
    teams = db.query(Team).filter(Team.circle == circle_up, Team.is_active == True).all()

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

    performance_rows = []
    for idx, t in enumerate(teams, start=1):
        load_kw = round(float(lb_map.get(t.id, 0.0)), 2)
        coll_inr = round(float(coll_map.get(t.name, 0.0)), 2)
        dc_count, dc_amt = dc_map.get(t.id, (0, 0.0))
        km_run = int(km_map.get(t.id, 0))

        performance_rows.append({
            "sl_no": idx,
            "team_name": t.name,
            "assigned_team_lead": t.assigned_team_lead or "N/A",
            "supervisor_name": t.supervisor_name or "N/A",
            "load_booked_kw": load_kw,
            "amount_collected": coll_inr,
            "dc_count": dc_count,
            "dc_amount": round(dc_amt, 2),
            "km_run": km_run,
            "remarks": ""
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
# 4. FIELD COLLECTION REGISTER
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
    ).order_by(Collection.payment_date, Collection.mr_number).all()

    records = [
        {
            "payment_date": c.payment_date,
            "mr_number": c.mr_number,
            "vcr_number": c.vcr_number or "-",
            "amount_paid": c.amount_paid,
            "collected_by": getattr(c, "collected_by_name", None) or getattr(c, "collected_by_emp_id", None) or "-",
            "team_name": c.team_name,
            "circle": c.circle,
            "division": c.division or "-",
            "subdivision": c.subdivision or "-",
            "section": c.section or "-"
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
        return Response(content=file_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Collections_{circle_up}_{month}_{year}.pdf"})
    else:
        file_bytes = reports_excel.build_collection_excel(
            circle_name=circle_up,
            year=year,
            month=month,
            records=records
        )
        return Response(content=file_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=Collections_{circle_up}_{month}_{year}.xlsx"})



# =========================================================================
# 6. ALL LOAD BOOKINGS REGISTER (EXCEL & PDF)
# =========================================================================
@router.get("/load-bookings/excel")
def export_load_bookings_excel(
    circle: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Exports all unauthorized load bookings to a formatted, tamper-proof, password-protected Excel (.xlsx) file.
    Includes =SUM() formula for Booked Load (kW).
    """
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

    if from_date:
        q = q.filter(LoadBooking.booking_date >= from_date)
    if to_date:
        q = q.filter(LoadBooking.booking_date <= to_date)

    records_db = q.order_by(LoadBooking.booking_date.desc(), LoadBooking.id.desc()).all()

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

    file_bytes = reports_excel.build_load_booking_excel(
        bookings=bookings,
        circle=circle,
        from_date=from_date,
        to_date=to_date
    )

    filename = f"Load_Bookings_{(circle or 'ALL').upper()}_{date.today()}.xlsx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/load-bookings/pdf")
def export_load_bookings_pdf(
    circle: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Exports all unauthorized load bookings to an official A4 landscape ReportLab PDF.
    """
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

    if from_date:
        q = q.filter(LoadBooking.booking_date >= from_date)
    if to_date:
        q = q.filter(LoadBooking.booking_date <= to_date)

    records_db = q.order_by(LoadBooking.booking_date.desc(), LoadBooking.id.desc()).all()

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

    file_bytes = reports_pdf.build_load_booking_pdf(
        bookings=bookings,
        circle=circle,
        from_date=from_date,
        to_date=to_date
    )

    filename = f"Load_Bookings_{(circle or 'ALL').upper()}_{date.today()}.pdf"
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, synonym
from database import Base

ALL_TPSODL_CIRCLES = ["JEYPORE", "RAYAGADA", "BHANJANAGAR", "ASKA", "BERHAMPUR", "BERHAMPUR CITY"]

def get_assigned_circles(user) -> list[str]:
    """
    Returns list of authorized circles for a user.
    Admins have access to all circles.
    Sub-Admins and Users have access to their comma-separated assigned circles.
    """
    if not user:
        return []
    if getattr(user, "role", "") == "ADMIN":
        return list(ALL_TPSODL_CIRCLES)
    raw = getattr(user, "circle", "") or ""
    if not raw:
        return []
    circles = []
    for c in raw.split(","):
        cleaned = c.strip().upper()
        if cleaned and cleaned not in circles:
            circles.append(cleaned)
    return circles

def is_circle_authorized(user, circle: str) -> bool:
    """
    Checks if a circle is authorized for the given user,
    handling CITY and BERHAMPUR CITY synonyms.
    """
    if not user or not circle:
        return False
    if getattr(user, "role", "") == "ADMIN":
        return True
    allowed = get_assigned_circles(user)
    target = circle.strip().upper()
    if target in allowed:
        return True
    if target in ("CITY", "BERHAMPUR CITY"):
        return "CITY" in allowed or "BERHAMPUR CITY" in allowed
    return False

# =========================================================================
# 1. USERS & ACCESS CONTROL
# =========================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), default="USER", nullable=False)       # ADMIN, SUB_ADMIN, USER
    circle = Column(String(255), nullable=True)                     # Comma-separated assigned circles or null
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    can_edit = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    team = relationship("Team", foreign_keys=[team_id])

    def get_assigned_circles(self) -> list[str]:
        return get_assigned_circles(self)

    def is_circle_authorized(self, circle: str) -> bool:
        return is_circle_authorized(self, circle)


# =========================================================================
# 2. TPSODL REGULAR OFFICERS (TEAM LEADERS)
# Permanent TPSODL employees (NOT BA staff). Lead squads and authorize raids.
# =========================================================================
class TeamLead(Base):
    __tablename__ = "team_leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tl_code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    designation = Column(String(100), nullable=True)
    circle = Column(String(50), index=True, nullable=False)
    contact_no = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    teams = relationship("Team", back_populates="default_tl", foreign_keys="Team.default_tl_id")
    daily_operations = relationship("DailyTeamOperation", back_populates="daily_tl", foreign_keys="DailyTeamOperation.daily_tl_id")


# =========================================================================
# 3. ENFORCEMENT SQUADS (TEAMS)
# =========================================================================
class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    circle = Column(String(50), index=True, nullable=False)
    supervisor_name = Column(String(100), nullable=True)
    default_tl_id = Column(Integer, ForeignKey("team_leads.id", ondelete="SET NULL"), nullable=True)
    assigned_team_lead = Column(String(100), nullable=True)  # Display name / legacy fallback
    has_vehicle = Column(Boolean, default=True, nullable=False)
    is_office_team = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    @property
    def is_office(self) -> bool:
        return bool(self.is_office_team or not self.has_vehicle)

    default_tl = relationship("TeamLead", back_populates="teams", foreign_keys=[default_tl_id])
    employees = relationship("Employee", back_populates="team", foreign_keys="Employee.team_id")
    daily_operations = relationship("DailyTeamOperation", back_populates="team", foreign_keys="DailyTeamOperation.team_id")
    logbooks = relationship("VehicleLogBook", back_populates="team")
    load_bookings = relationship("LoadBooking", back_populates="team")
    disconnections = relationship("DisconnectionRecord", back_populates="team")


# =========================================================================
# 4. BA CONTRACTOR EMPLOYEES (MANPOWER)
# Agency contractor personnel (Form D register attendance marked ONLY here).
# =========================================================================
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emp_code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    designation = Column(String(100), nullable=True)
    circle = Column(String(50), index=True, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    team = relationship("Team", back_populates="employees", foreign_keys=[team_id])
    attendances = relationship("Attendance", back_populates="employee")


# =========================================================================
# 5. DAILY TEAM OPERATIONS & ARRANGEMENTS
# Maps squads to their active designated TPSODL Team Leader for each date.
# =========================================================================
class DailyTeamOperation(Base):
    __tablename__ = "daily_team_operations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    operation_date = Column(Date, index=True, nullable=False, default=date.today)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    daily_tl_id = Column(Integer, ForeignKey("team_leads.id", ondelete="SET NULL"), nullable=True)
    tl_name = Column(String(100), nullable=True)
    is_team_active = Column(Boolean, default=True, nullable=False)
    operating_with_tl = Column(Boolean, default=True, nullable=False)
    operation_mode = Column(String(50), default="INDEPENDENT_WITH_TL", nullable=False)
    # Modes: "INDEPENDENT_WITH_TL", "INDEPENDENT_WITHOUT_TL_COLLECTION", "MERGED", "NON_OPERATIONAL"
    merged_with_team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    remarks = Column(Text, nullable=True)
    is_locked = Column(Boolean, default=True, nullable=False)

    # Legacy attribute alias for daily_tl_id
    daily_team_lead_id = synonym("daily_tl_id")

    team = relationship("Team", foreign_keys=[team_id], back_populates="daily_operations")
    merged_with_team = relationship("Team", foreign_keys=[merged_with_team_id])
    daily_tl = relationship("TeamLead", foreign_keys=[daily_tl_id], back_populates="daily_operations")
    # Legacy alias relationship for daily_team_lead
    daily_team_lead = relationship("TeamLead", foreign_keys=[daily_tl_id], overlaps="daily_operations,daily_tl")
    attendances = relationship("Attendance", back_populates="operation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_dto_date_team", "operation_date", "team_id"),
        Index("idx_dto_date_tl", "operation_date", "daily_tl_id"),
    )


# =========================================================================
# 6. ATTENDANCE (FORM D REGISTER - BA CONTRACT PERSONNEL ONLY)
# =========================================================================
class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    operation_id = Column(Integer, ForeignKey("daily_team_operations.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(5), default="P", nullable=False)  # P, A, L, WO
    is_locked = Column(Boolean, default=True, nullable=False)

    operation = relationship("DailyTeamOperation", back_populates="attendances")
    employee = relationship("Employee", back_populates="attendances")


# =========================================================================
# 7. VEHICLE LOG BOOKS
# =========================================================================
class VehicleLogBook(Base):
    __tablename__ = "vehicle_log_books"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, index=True, nullable=False, default=date.today)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    vehicle_no = Column(String(30), nullable=False)
    supervisor_name = Column(String(100), nullable=True)
    assigned_team_lead = Column(String(100), nullable=True)
    start_km = Column(Integer, nullable=False)
    end_km = Column(Integer, nullable=False)
    run_km = Column(Integer, nullable=False)
    start_time = Column(String(20), nullable=True)
    end_time = Column(String(20), nullable=True)
    area_movement = Column(Text, nullable=True)
    is_locked = Column(Boolean, default=True, nullable=False)

    # Legacy alias synonym
    permanent_team_lead = synonym("assigned_team_lead")

    team = relationship("Team", back_populates="logbooks")


# =========================================================================
# 8. LOAD BOOKINGS
# Dynamic attribution: TL code maps to active squad via daily_team_operations.
# =========================================================================
class LoadBooking(Base):
    __tablename__ = "load_bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    booking_date = Column(Date, index=True, nullable=False, default=date.today)
    book_number = Column(String(50), index=True, nullable=True)
    page_no = Column(String(50), index=True, nullable=True)
    vcr_number = Column(String(50), index=True, nullable=True)
    tl_code = Column(String(50), index=True, nullable=True)  # TPSODL TL Code
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True)
    circle = Column(String(50), index=True, nullable=False)
    division = Column(String(50), nullable=True)
    subdivision = Column(String(50), nullable=True)
    section = Column(String(50), nullable=True)
    pincode = Column(String(10), nullable=True)
    theft_type = Column(String(50), nullable=False)
    booked_load = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False)
    is_locked = Column(Boolean, default=True, nullable=False)

    # Legacy alias / compatibility column
    punch_emp_id = Column(Integer, nullable=True)

    team = relationship("Team", back_populates="load_bookings", foreign_keys=[team_id])
    vcr_records = relationship("VCRMaster", back_populates="booking")

    __table_args__ = (
        Index("idx_lb_book_page_circle", "circle", "book_number", "page_no", unique=True),
        Index("idx_lb_date_circle", "booking_date", "circle"),
        Index("idx_lb_theft_date", "theft_type", "booking_date"),
        Index("idx_lb_tl_date", "tl_code", "booking_date"),
    )


# =========================================================================
# 9. VCR MASTER
# =========================================================================
class VCRMaster(Base):
    __tablename__ = "vcr_masters"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    vcr_number = Column(String(50), unique=True, index=True, nullable=False)
    booking_id = Column(Integer, ForeignKey("load_bookings.id", ondelete="SET NULL"), nullable=True)
    consumer_name = Column(String(150), nullable=True)
    consumer_address = Column(Text, nullable=True)
    circle = Column(String(50), index=True, nullable=False)
    division = Column(String(50), nullable=True)
    subdivision = Column(String(50), nullable=True)
    section = Column(String(50), nullable=True)
    inspection_date = Column(Date, nullable=True)

    # Backward-compatibility synonyms
    provisional_bill_date = synonym("inspection_date")
    date_of_provisional = synonym("inspection_date")

    booking = relationship("LoadBooking", back_populates="vcr_records")
    disconnections = relationship("DisconnectionRecord", back_populates="vcr")

    __table_args__ = (
        Index("idx_vcr_circle", "vcr_number", "circle"),
    )


# =========================================================================
# 10. DISCONNECTION RECORDS
# Dynamic attribution: dc_authority_tl_code maps to active squad.
# =========================================================================
class DisconnectionRecord(Base):
    __tablename__ = "disconnection_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    dc_date = Column(Date, index=True, nullable=False, default=date.today)
    vcr_number = Column(String(50), ForeignKey("vcr_masters.vcr_number"), index=True, nullable=False)
    dc_authority_tl_code = Column(String(50), index=True, nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True)
    amount_pending = Column(Float, default=0.0, nullable=False)
    remarks = Column(Text, nullable=True)
    is_locked = Column(Boolean, default=True, nullable=False)

    # Legacy compatibility column
    dc_authority_emp_id = Column(Integer, nullable=True)

    vcr = relationship("VCRMaster", back_populates="disconnections", foreign_keys=[vcr_number])
    team = relationship("Team", back_populates="disconnections", foreign_keys=[team_id])

    __table_args__ = (
        Index("idx_dc_date_team", "dc_date", "team_id"),
        Index("idx_dc_vcr_date", "vcr_number", "dc_date"),
        Index("idx_dc_tl_date", "dc_authority_tl_code", "dc_date"),
    )


# =========================================================================
# 11. COLLECTIONS (STANDALONE REGISTER - NO FK TO LOAD BOOKING OR DC)
# =========================================================================
class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    payment_date = Column(Date, index=True, nullable=False)
    mr_number = Column(String(50), unique=True, index=True, nullable=False)
    vcr_number = Column(String(50), index=True, nullable=True)
    amount_paid = Column(Float, default=0.0, nullable=False)
    team_name = Column(String(100), index=True, nullable=True)
    collected_by_name = Column(String(100), nullable=True)
    circle = Column(String(50), index=True, nullable=False)
    division = Column(String(50), nullable=True)
    subdivision = Column(String(50), nullable=True)
    section = Column(String(50), nullable=True)

    # Legacy alias synonym
    collected_by_emp_id = synonym("collected_by_name")

    __table_args__ = (
        Index("idx_coll_date_team", "payment_date", "team_name"),
        Index("idx_coll_date_circle", "payment_date", "circle"),
    )


# =========================================================================
# 12. PVR (PHYSICAL VERIFICATION REPORT) UPLOADS - PDFs STORED IN GOOGLE DRIVE
# =========================================================================
class PVRUpload(Base):
    __tablename__ = "pvr_uploads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pvr_date = Column(Date, index=True, nullable=False)
    circle = Column(String(50), index=True, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    team_lead_id = Column(Integer, ForeignKey("team_leads.id", ondelete="RESTRICT"), nullable=False)
    team_name = Column(String(100), nullable=True)       # snapshot at upload time
    tl_name = Column(String(100), nullable=True)         # snapshot at upload time
    drive_file_id = Column(String(128), nullable=True, unique=True)   # NULL until the worker uploads it
    drive_folder_id = Column(String(128), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)            # bytes stored in Drive (after compression)
    original_size = Column(Integer, nullable=True)        # bytes as uploaded by the user
    page_count = Column(Integer, nullable=True)
    storage_status = Column(String(10), nullable=False, default="PENDING")  # PENDING / UPLOADED / FAILED
    storage_error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    team = relationship("Team", foreign_keys=[team_id])
    team_lead = relationship("TeamLead", foreign_keys=[team_lead_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        # One PVR per team leader per day: final guard against duplicates / races
        UniqueConstraint("pvr_date", "team_lead_id", name="uq_pvr_date_team_lead"),
        Index("idx_pvr_date_circle", "pvr_date", "circle"),
    )


class PVRDriveFolder(Base):
    """Cache of Drive folder ids by logical path (Drive allows duplicate folder names)."""
    __tablename__ = "pvr_drive_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String(500), unique=True, nullable=False)   # e.g. "TPSODL_PVR/2026/11-November"
    folder_id = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PVRAuditLog(Base):
    __tablename__ = "pvr_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pvr_id = Column(Integer, index=True, nullable=True)       # no FK: rows survive PVR deletion
    action = Column(String(20), nullable=False)               # UPLOAD / REUPLOAD / EDIT / DELETE
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)                     # JSON text
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

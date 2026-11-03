from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

# --- Auth Schemas ---
class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    circle: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    can_edit: bool = False
    is_active: bool = True

    class Config:
        from_attributes = True

# --- Team Leads (TPSODL Regular Officers) Schemas ---
class CreateTeamLeadRequest(BaseModel):
    tl_code: str
    name: str
    designation: Optional[str] = None
    circle: str
    contact_no: Optional[str] = None

class UpdateTeamLeadRequest(BaseModel):
    tl_code: Optional[str] = None
    name: Optional[str] = None
    designation: Optional[str] = None
    circle: Optional[str] = None
    contact_no: Optional[str] = None
    is_active: Optional[bool] = None

class TeamLeadResponse(BaseModel):
    id: int
    tl_code: str
    name: str
    designation: Optional[str] = None
    circle: str
    contact_no: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True

# --- Team / Squad Schemas ---
class CreateTeamRequest(BaseModel):
    name: str
    circle: str
    supervisor_name: Optional[str] = None
    default_tl_id: Optional[int] = None
    assigned_team_lead: Optional[str] = None  # Legacy or direct text name
    has_vehicle: Optional[bool] = True
    is_office_team: Optional[bool] = False

class UpdateTeamRequest(BaseModel):
    name: Optional[str] = None
    circle: Optional[str] = None
    supervisor_name: Optional[str] = None
    default_tl_id: Optional[int] = None
    assigned_team_lead: Optional[str] = None
    has_vehicle: Optional[bool] = None
    is_office_team: Optional[bool] = None
    is_active: Optional[bool] = None

# --- BA Contractor Employees Schemas ---
class CreateEmployeeRequest(BaseModel):
    emp_code: str
    name: str
    designation: Optional[str] = None
    circle: str
    team_id: Optional[int] = None

class UpdateEmployeeRequest(BaseModel):
    emp_code: Optional[str] = None
    name: Optional[str] = None
    designation: Optional[str] = None
    circle: Optional[str] = None
    team_id: Optional[int] = None
    is_active: Optional[bool] = None

# --- User Management Schemas ---
class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    circle: Optional[str] = None
    team_id: Optional[int] = None
    can_edit: bool = False

class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    circle: Optional[str] = None
    team_id: Optional[int] = None
    can_edit: Optional[bool] = None
    is_active: Optional[bool] = None

# --- VCR Master Schemas ---
class VCRMasterCreate(BaseModel):
    vcr_number: str
    booking_id: Optional[int] = None
    consumer_name: str
    consumer_address: Optional[str] = None
    circle: str
    division: Optional[str] = None
    subdivision: Optional[str] = None
    section: Optional[str] = None
    inspection_date: Optional[date] = None
    provisional_bill_date: Optional[date] = None
    date_of_provisional: Optional[date] = None

# --- Attendance Schemas (Form D Register - BA Staff Only) ---
class EmpAttendanceItem(BaseModel):
    employee_id: int
    status: str = Field("P", description="P, A, L, WO")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        if not v:
            return "P"
        v_clean = str(v).strip().upper()
        if v_clean == "-":
            return "WO"
        if v_clean not in ("P", "A", "L", "WO"):
            raise ValueError(f"Invalid attendance status '{v}'. Allowed options are P (Present), A (Absent), L (Leave), WO (Weekly Off).")
        return v_clean

class SaveOperationRequest(BaseModel):
    operation_date: date
    team_id: int
    circle: Optional[str] = None
    daily_tl_id: Optional[int] = None
    daily_team_lead_id: Optional[int] = None  # Legacy alias
    tl_name: Optional[str] = None
    is_team_active: bool = True
    operating_with_tl: bool = True
    operation_mode: str = "INDEPENDENT_WITH_TL"
    merged_with_team_id: Optional[int] = None
    remarks: Optional[str] = None
    attendance: List[EmpAttendanceItem] = []

# --- Vehicle Log Book Schemas ---
class LogBookEntry(BaseModel):
    date: date
    team_id: int
    vehicle_no: str
    supervisor_name: Optional[str] = None
    start_km: int
    end_km: int
    start_time: str
    end_time: str
    area_movement: Optional[str] = None

# --- Load Booking Schemas ---
class LoadBookingRequest(BaseModel):
    booking_date: Optional[date] = None
    book_number: str = Field(..., description="Book Number (e.g. B-102)")
    page_no: Optional[str] = None
    page_number: Optional[str] = None
    tl_code: Optional[str] = None  # TPSODL Officer Code
    punch_emp_code: Optional[str] = None  # Legacy alias
    team_id: Optional[int] = None
    circle: str
    division: str
    subdivision: str
    section: str
    pincode: Optional[str] = None
    theft_type: str = Field(..., description="Hooking, Meter Tamper, Bypass, Misuse")
    booked_load: float = Field(..., gt=0.0, le=100.0)
    status: Optional[str] = "PENDING"
    vcr_number: Optional[str] = None
    allow_duplicate: Optional[bool] = False

# --- Disconnection Schemas ---
class DCPunchRequest(BaseModel):
    vcr_number: str
    dc_date: date
    amount_pending: float
    dc_authority_tl_code: Optional[str] = None  # TPSODL Officer Code
    dc_authority_emp_id: Optional[str] = None  # Legacy alias
    team_id: Optional[int] = None
    remarks: Optional[str] = None
    allow_duplicate: Optional[bool] = False

# --- Collection Schemas (Standalone Register) ---
class CollectionRow(BaseModel):
    payment_date: date
    mr_number: str
    vcr_number: Optional[str] = None
    amount_paid: float
    team_name: Optional[str] = None
    collected_by_name: Optional[str] = None
    collected_by_emp_id: Optional[str] = None  # Legacy alias
    circle: str
    division: Optional[str] = None
    subdivision: Optional[str] = None
    section: Optional[str] = None

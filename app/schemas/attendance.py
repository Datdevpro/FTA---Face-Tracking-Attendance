"""
Attendance schemas for API request/response validation.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    department_name: Optional[str] = None
    attendance_date: date
    check_in_time: Optional[datetime]
    check_out_time: Optional[datetime]
    check_in_confidence: Optional[float]
    check_out_confidence: Optional[float]
    status: str
    source: str
    note: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AttendanceManualCreate(BaseModel):
    employee_id: int
    attendance_date: date
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    status: str = "PRESENT"
    note: Optional[str] = None


class AttendanceListResponse(BaseModel):
    items: List[AttendanceResponse]
    total: int
    page: int
    page_size: int


class AttendanceSummary(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_name: Optional[str]
    total_days: int
    present_days: int
    late_days: int
    absent_days: int
    half_days: int


class DashboardStats(BaseModel):
    total_employees: int
    active_employees: int
    checked_in_today: int
    late_today: int
    absent_today: int
    on_time_today: int
    registered_faces: int
    recent_activities: List[dict]

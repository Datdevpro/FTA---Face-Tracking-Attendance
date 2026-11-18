"""
Employee schemas for API request/response validation.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date, datetime


class EmployeeCreate(BaseModel):
    welcome_template: Optional[str] = Field(default=None, min_length=1, max_length=300)
    welcome_voice: Optional[str] = Field(default=None, min_length=1, max_length=80)
    employee_code: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    position: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    joined_date: Optional[date] = None


class EmployeeUpdate(BaseModel):
    welcome_template: Optional[str] = Field(default=None, min_length=1, max_length=300)
    welcome_voice: Optional[str] = Field(default=None, min_length=1, max_length=80)
    employee_code: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    position: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    joined_date: Optional[date] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    welcome_template: str = ""
    welcome_voice: str = ""
    welcome_text: str = ""
    welcome_status: str = "pending"
    welcome_error: Optional[str] = None
    welcome_audio_key: Optional[str] = None
    id: int
    employee_code: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    department_id: Optional[int]
    department_name: Optional[str] = None
    position: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    joined_date: Optional[date]
    is_active: bool
    has_face_registered: bool = False
    face_count: int = 0
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class EmployeeListResponse(BaseModel):
    items: List[EmployeeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

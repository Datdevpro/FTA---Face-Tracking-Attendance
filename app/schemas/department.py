"""
Department schemas for API request/response validation.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    employee_count: Optional[int] = 0

    model_config = {"from_attributes": True}

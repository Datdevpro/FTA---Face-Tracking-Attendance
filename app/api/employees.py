"""
Employee management API endpoints.
"""

import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
)

router = APIRouter(prefix="/api/employees", tags=["Employees"])


def _employee_to_response(employee: Employee, db: Session) -> EmployeeResponse:
    """Convert Employee model to response schema."""
    face_count = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee.id)
        .count()
    )
    dept_name = employee.department.name if employee.department else None

    return EmployeeResponse(
        id=employee.id,
        employee_code=employee.employee_code,
        full_name=employee.full_name,
        email=employee.email,
        phone=employee.phone,
        department_id=employee.department_id,
        department_name=dept_name,
        position=employee.position,
        date_of_birth=employee.date_of_birth,
        gender=employee.gender,
        joined_date=employee.joined_date,
        is_active=employee.is_active,
        has_face_registered=face_count > 0,
        face_count=face_count,
        created_at=employee.created_at,
        updated_at=employee.updated_at,
    )


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List employees with pagination, search, and filtering.
    """
    query = db.query(Employee).options(joinedload(Employee.department))

    # Filters
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Employee.full_name.ilike(search_term))
            | (Employee.employee_code.ilike(search_term))
            | (Employee.email.ilike(search_term))
        )
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)

    # Count total
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    # Paginate
    employees = (
        query.order_by(Employee.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_employee_to_response(emp, db) for emp in employees]

    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new employee."""
    # Check unique employee_code
    existing = (
        db.query(Employee)
        .filter(Employee.employee_code == data.employee_code)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee code '{data.employee_code}' already exists",
        )

    # Check unique email if provided
    if data.email:
        email_exists = (
            db.query(Employee).filter(Employee.email == data.email).first()
        )
        if email_exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{data.email}' already registered",
            )

    employee = Employee(**data.model_dump())
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return _employee_to_response(employee, db)


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get employee by ID."""
    employee = (
        db.query(Employee)
        .options(joinedload(Employee.department))
        .filter(Employee.id == employee_id)
        .first()
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return _employee_to_response(employee, db)


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update employee information."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    if "employee_code" in update_data and update_data["employee_code"] != employee.employee_code:
        existing = (
            db.query(Employee)
            .filter(
                Employee.employee_code == update_data["employee_code"],
                Employee.id != employee_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Employee code '{update_data['employee_code']}' already exists",
            )

    for key, value in update_data.items():
        setattr(employee, key, value)

    db.commit()
    db.refresh(employee)

    return _employee_to_response(employee, db)


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Soft delete an employee."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    employee.is_active = False
    db.commit()

    return {"message": f"Employee '{employee.full_name}' deactivated"}

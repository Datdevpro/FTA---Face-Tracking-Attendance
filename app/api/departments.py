"""
Department management API endpoints.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
)

router = APIRouter(prefix="/api/departments", tags=["Departments"])


@router.get("", response_model=List[DepartmentResponse])
def list_departments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all departments."""
    departments = db.query(Department).order_by(Department.name).all()

    results = []
    for dept in departments:
        emp_count = (
            db.query(Employee)
            .filter(
                Employee.department_id == dept.id,
                Employee.is_active == True,
            )
            .count()
        )
        resp = DepartmentResponse(
            id=dept.id,
            name=dept.name,
            description=dept.description,
            is_active=dept.is_active,
            created_at=dept.created_at,
            employee_count=emp_count,
        )
        results.append(resp)

    return results


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new department."""
    existing = db.query(Department).filter(Department.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Department '{data.name}' already exists",
        )

    dept = Department(name=data.name, description=data.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)

    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        description=dept.description,
        is_active=dept.is_active,
        created_at=dept.created_at,
        employee_count=0,
    )


@router.put("/{dept_id}", response_model=DepartmentResponse)
def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a department."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    if data.name is not None:
        dept.name = data.name
    if data.description is not None:
        dept.description = data.description
    if data.is_active is not None:
        dept.is_active = data.is_active

    db.commit()
    db.refresh(dept)

    emp_count = (
        db.query(Employee)
        .filter(Employee.department_id == dept.id, Employee.is_active == True)
        .count()
    )

    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        description=dept.description,
        is_active=dept.is_active,
        created_at=dept.created_at,
        employee_count=emp_count,
    )


@router.delete("/{dept_id}")
def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a department (soft delete by setting is_active=False)."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    dept.is_active = False
    db.commit()

    return {"message": f"Department '{dept.name}' deactivated"}

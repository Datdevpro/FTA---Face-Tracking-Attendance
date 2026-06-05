"""
Attendance management API endpoints.
"""

from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import AttendanceRecord
from app.models.employee import Employee
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceManualCreate,
    AttendanceListResponse,
)

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


def _record_to_response(record: AttendanceRecord, db: Session) -> AttendanceResponse:
    """Convert AttendanceRecord model to response schema."""
    employee = db.query(Employee).filter(Employee.id == record.employee_id).first()
    dept_name = None
    if employee and employee.department:
        dept_name = employee.department.name

    return AttendanceResponse(
        id=record.id,
        employee_id=record.employee_id,
        employee_code=employee.employee_code if employee else None,
        employee_name=employee.full_name if employee else None,
        department_name=dept_name,
        attendance_date=record.attendance_date,
        check_in_time=record.check_in_time,
        check_out_time=record.check_out_time,
        check_in_confidence=record.check_in_confidence,
        check_out_confidence=record.check_out_confidence,
        status=record.status,
        source=record.source,
        note=record.note,
        created_at=record.created_at,
    )


@router.get("", response_model=AttendanceListResponse)
def list_attendance(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    attendance_date: Optional[date] = None,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List attendance records with filtering and pagination."""
    query = db.query(AttendanceRecord)

    if attendance_date:
        query = query.filter(AttendanceRecord.attendance_date == attendance_date)
    if employee_id:
        query = query.filter(AttendanceRecord.employee_id == employee_id)
    if department_id:
        query = query.join(Employee).filter(Employee.department_id == department_id)
    if status_filter:
        query = query.filter(AttendanceRecord.status == status_filter)

    total = query.count()

    records = (
        query.order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.check_in_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_record_to_response(r, db) for r in records]

    return AttendanceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/today", response_model=List[AttendanceResponse])
def get_today_attendance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all attendance records for today."""
    today = date.today()
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.attendance_date == today)
        .order_by(AttendanceRecord.check_in_time.desc())
        .all()
    )
    return [_record_to_response(r, db) for r in records]


@router.post("/manual", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
def create_manual_attendance(
    data: AttendanceManualCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a manual attendance record."""
    # Validate employee
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Check if record already exists for this date
    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == data.employee_id,
            AttendanceRecord.attendance_date == data.attendance_date,
        )
        .first()
    )

    if existing:
        # Update existing record
        if data.check_in_time:
            existing.check_in_time = data.check_in_time
        if data.check_out_time:
            existing.check_out_time = data.check_out_time
        existing.status = data.status
        existing.source = "MANUAL"
        if data.note:
            existing.note = data.note
        db.commit()
        db.refresh(existing)
        return _record_to_response(existing, db)

    # Create new record
    record = AttendanceRecord(
        employee_id=data.employee_id,
        attendance_date=data.attendance_date,
        check_in_time=data.check_in_time,
        check_out_time=data.check_out_time,
        status=data.status,
        source="MANUAL",
        note=data.note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return _record_to_response(record, db)


@router.get("/summary")
def get_attendance_summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get monthly attendance summary for all employees."""
    from app.services.report_service import ReportService

    report_service = ReportService()
    return report_service.get_monthly_summary(db, year, month)

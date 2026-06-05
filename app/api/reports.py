"""
Report API endpoints for attendance reports and exports.
"""

from datetime import date
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/daily")
def get_daily_report(
    report_date: date = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get daily attendance report."""
    if report_date is None:
        report_date = date.today()

    service = ReportService()
    return {
        "date": report_date.isoformat(),
        "data": service.get_daily_report(db, report_date),
    }


@router.get("/monthly")
def get_monthly_report(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get monthly attendance summary report."""
    service = ReportService()
    return {
        "year": year,
        "month": month,
        "data": service.get_monthly_summary(db, year, month),
    }


@router.get("/export/excel")
def export_excel(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export monthly attendance report as Excel file."""
    service = ReportService()
    excel_bytes = service.export_to_excel(db, year, month)

    filename = f"attendance_report_{year}_{month:02d}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/dashboard-stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get real-time dashboard statistics."""
    service = ReportService()
    return service.get_dashboard_stats(db)

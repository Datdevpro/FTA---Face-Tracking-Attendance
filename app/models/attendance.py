"""
Attendance record database model.
"""

# pyrefly: ignore [missing-import]
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    Float,
    String,
    Date,
    DateTime,
    Text,
    ForeignKey,
    func,
    UniqueConstraint,
)
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship

from app.core.database import Base


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attendance_date = Column(Date, nullable=False, index=True)
    check_in_time = Column(DateTime(timezone=True), nullable=True)
    check_out_time = Column(DateTime(timezone=True), nullable=True)
    check_in_image = Column(String(500), nullable=True)
    check_out_image = Column(String(500), nullable=True)
    check_in_confidence = Column(Float, nullable=True)
    check_out_confidence = Column(Float, nullable=True)
    # PRESENT, LATE, ABSENT, HALF_DAY
    status = Column(String(20), default="PRESENT", nullable=False)
    # CAMERA_AUTO, MANUAL
    source = Column(String(20), default="CAMERA_AUTO", nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee = relationship("Employee", back_populates="attendance_records")

    # Constraints: one record per employee per day
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "attendance_date",
            name="uq_employee_attendance_date",
        ),
    )

    def __repr__(self):
        return (
            f"<AttendanceRecord(id={self.id}, employee_id={self.employee_id}, "
            f"date={self.attendance_date}, status='{self.status}')>"
        )


class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    start_time = Column(String(5), nullable=False)  # "HH:MM"
    end_time = Column(String(5), nullable=False)  # "HH:MM"
    late_threshold_minutes = Column(Integer, default=15)
    is_default = Column(Boolean, default=False)

    def __repr__(self):
        return f"<WorkSchedule(id={self.id}, name='{self.name}', {self.start_time}-{self.end_time})>"

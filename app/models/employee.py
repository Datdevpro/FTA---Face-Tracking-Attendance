"""
Employee database model.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    phone = Column(String(20), nullable=True)
    department_id = Column(
        Integer, ForeignKey("departments.id"), nullable=True
    )
    position = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)  # MALE, FEMALE, OTHER
    joined_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    department = relationship("Department", back_populates="employees")
    face_encodings = relationship(
        "FaceEncoding", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Employee(id={self.id}, code='{self.employee_code}', name='{self.full_name}')>"

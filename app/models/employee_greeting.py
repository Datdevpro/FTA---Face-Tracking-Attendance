"""Per-employee greeting configuration and generation state."""
from sqlalchemy import Column, ForeignKey, Integer, String
from app.core.database import Base


class EmployeeGreeting(Base):
    __tablename__ = "employee_greetings"
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    template = Column(String(300), nullable=False)
    voice = Column(String(80), nullable=False)
    audio_key = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    error = Column(String(200), nullable=True)

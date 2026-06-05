"""
Admin user database model for system authentication.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, func

from app.core.database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=False)
    # ADMIN, MANAGER, VIEWER
    role = Column(String(20), default="VIEWER", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username='{self.username}', role='{self.role}')>"


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(
        String(50), nullable=False, index=True
    )  # RECOGNITION, ERROR, LOGIN, ATTENDANCE
    description = Column(String(1000), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self):
        return f"<SystemLog(id={self.id}, type='{self.event_type}')>"

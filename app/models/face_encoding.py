"""
Face encoding database model.
Stores 512-dimensional ArcFace embeddings for face recognition.
"""

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Boolean,
    LargeBinary,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 512-dimensional ArcFace embedding stored as binary (numpy bytes)
    encoding = Column(LargeBinary, nullable=False)
    image_path = Column(String(500), nullable=True)
    quality_score = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee = relationship("Employee", back_populates="face_encodings")

    def __repr__(self):
        return f"<FaceEncoding(id={self.id}, employee_id={self.employee_id}, quality={self.quality_score:.2f})>"

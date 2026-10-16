"""Evidence ORM model."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship

from ..database import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(
        Integer, ForeignKey("incidents.id"), nullable=False, index=True
    )
    source = Column(String(20), nullable=False, index=True)
    service = Column(String(100), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="info")
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident = relationship("Incident", back_populates="evidence")

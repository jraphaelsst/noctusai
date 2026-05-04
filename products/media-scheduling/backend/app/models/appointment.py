"""ORM model for media_scheduling.appointments."""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, func

from app.models import Base, SCHEMA


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    appointment_request_id = Column(BigInteger, nullable=True)
    google_calendar_event_id = Column(String(255), nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    property_id = Column(BigInteger, nullable=False)
    condominium_id = Column(
        BigInteger, ForeignKey(f"{SCHEMA}.condominiums.id"), nullable=False
    )
    route_group_id = Column(BigInteger, nullable=True)
    status = Column(String(40), nullable=False, default="scheduled")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

"""ORM model for media_scheduling.condominiums."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, String, Text, func

from app.models import Base, SCHEMA


class Condominium(Base):
    __tablename__ = "condominiums"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    name = Column(String(160), nullable=False, unique=True)
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

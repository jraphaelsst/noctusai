"""ORM model for media_scheduling.authorized_users.

WhatsApp-authorized phone numbers + optional captured Linked-Identity
chat IDs. NOT platform SSO users — separate concept (see PROJECT.md §5).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, func

from app.models import Base, SCHEMA


class AuthorizedUser(Base):
    __tablename__ = "authorized_users"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    name = Column(String(120), nullable=False)
    role = Column(String(40), nullable=False)
    phone_number = Column(String(32), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    linked_identity = Column(String(128), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

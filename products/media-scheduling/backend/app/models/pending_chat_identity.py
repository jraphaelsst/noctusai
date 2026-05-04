"""ORM model for media_scheduling.pending_chat_identities.

Park unknown WhatsApp `@lid_*` chats so an admin can resolve them. See
`app.services.lid_auth.capture_pending_lid` for the capture path.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String, func

from app.models import Base, SCHEMA


class PendingChatIdentity(Base):
    __tablename__ = "pending_chat_identities"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    chat_id = Column(String(128), nullable=False, unique=True)
    push_name = Column(String(120), nullable=True)
    phone_hint = Column(String(32), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_to_user_id = Column(BigInteger, nullable=True)

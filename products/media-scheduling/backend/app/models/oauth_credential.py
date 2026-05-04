"""ORM model for media_scheduling.oauth_credentials."""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String, Text, UniqueConstraint, func

from app.models import Base, SCHEMA


class OAuthCredential(Base):
    __tablename__ = "oauth_credentials"
    __table_args__ = (
        UniqueConstraint("provider", "account_email", name="uq_oauth_credentials_provider_email"),
        {"schema": SCHEMA},
    )

    id = Column(BigInteger, primary_key=True)
    provider = Column(String(40), nullable=False)
    account_email = Column(String(255), nullable=False)
    refresh_token = Column(Text, nullable=False)
    access_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

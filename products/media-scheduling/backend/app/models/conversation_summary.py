"""ORM model for media_scheduling.conversation_summaries.

Idle-sweep persisted summaries from `noctusai_lib.domain.chatbot.summarize_conversation`.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base, SCHEMA


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=True)
    conversation_id = Column(String(64), nullable=False)
    summary_text = Column(Text, nullable=False)
    label = Column(JSONB, nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    model_used = Column(String(80), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

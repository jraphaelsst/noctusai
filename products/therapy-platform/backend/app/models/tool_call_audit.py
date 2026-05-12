"""ORM model for therapy.tool_call_audits.

Bound to `noctusai_lib.domain.ai.tool_audit.AuditRecord` via the
`make_audit_writer(db, ToolCallAudit)` factory — see
`app.services.audit_hook` for the wiring and
`KB § PATTERNS/llm-tool-audit.md` for the canonical pattern.

Column shape mirrors `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`
verbatim; arguments / result are JSONB so `AuditRecord.to_row_kwargs()`
plays straight through.

**LGPD note.** Therapy is HIGH-risk (Art. 11 sensitive data — patient
session transcripts, audio, images, observations). The `arguments` and
`result` JSONB columns MUST be redacted before construction of the
`AuditRecord` — see `app.services.audit_hook.redact_for_feature` for
the per-feature redaction lambdas wired to the dispatch sites.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base, SCHEMA


class ToolCallAudit(Base):
    __tablename__ = "tool_call_audits"
    __table_args__ = {"schema": SCHEMA}

    id = Column(BigInteger, primary_key=True)
    correlation_id = Column(String(64), nullable=True)
    gpt_call_id = Column(String(64), nullable=True)
    tool_call_id = Column(String(64), nullable=True)
    conversation_id = Column(String(64), nullable=True)
    user_id = Column(BigInteger, nullable=True)
    tool_name = Column(String(80), nullable=False)
    status = Column(String(16), nullable=False)
    arguments = Column(JSONB, nullable=True)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

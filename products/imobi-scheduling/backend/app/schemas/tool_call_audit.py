"""Pydantic models for ``imobi_scheduling.tool_call_audits``.

Mirrors the seed template at
``noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template``.
The seed library exposes ``AuditRecord`` / ``make_audit_writer``; this
schema is the read-side projection for product routers + tests.

LGPD: ``arguments`` and ``result`` may carry PII — products MUST redact
before constructing the ``AuditRecord``. See
``KB § PATTERNS/llm-tool-audit.md § LGPD``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ToolCallStatus = Literal["success", "failure", "unknown_tool"]


class ToolCallAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: UUID
    correlation_id: str | None
    gpt_call_id: str | None
    tool_call_id: str | None
    conversation_id: str | None
    user_id: UUID | None
    tool_name: str = Field(..., max_length=80)
    status: ToolCallStatus
    arguments: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    started_at: datetime

"""SQLAlchemy ORM surface for core.

Core's primary data path is the Supabase admin client — services route
through `db.table(...).select(...).execute()` patterns (`KB § PATTERNS/backend.md`).
SQLAlchemy is a SECONDARY surface, used only by the seed
`noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
contract which requires a typed ORM class for `tool_call_audits`. The
shape mirrors the original reference adopter's hybrid layout (retired
`media-scheduling`, consolidated into `social-wiring` 2026-05-16).

Never run `Base.metadata.create_all(...)` against the live DB — the
authoritative schema lives in `migrations/0NN_*.sql`.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by the audit-hook ORM model below.
Base = declarative_base()
SCHEMA = "public"

# SQLAlchemy ORM (audit-writer surface).
from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

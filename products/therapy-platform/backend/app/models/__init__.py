"""SQLAlchemy ORM bases for therapy-platform.

Therapy is Supabase-client-native — routers + admin CRUD touch
`db.table(...)` directly via the Supabase admin client. SQLAlchemy is a
SECONDARY surface, present only because the seed
`noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
contract requires a SQLAlchemy class for the audit-row INSERT path.

The schema lives in `migrations/0NN_*.sql`. Models mirror that DDL but
are NOT the source of truth — never run `Base.metadata.create_all(...)`
against the live DB.

Pattern mirrors the original canonical reference adopter (retired
`media-scheduling`, consolidated into `social-wiring` 2026-05-16;
llm-tool-audit-rollout Phase 1).
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by the ORM-flavored models below.
Base = declarative_base()
SCHEMA = "therapy"

# SQLAlchemy ORM models.
from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

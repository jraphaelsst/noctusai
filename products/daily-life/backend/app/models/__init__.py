"""Domain models for `daily_life`.

The product is Supabase-client-native — routers + services pass row dicts
through directly. **SQLAlchemy ORM is a SECONDARY surface** used only by
the seed `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
contract for the tool-call audit trail. Mirrors the hybrid layout settled
in `products/media-scheduling/backend/app/models/__init__.py`.

The actual schema lives in `migrations/00X_*.sql` (mirrored via Supabase
MCP). The `ToolCallAudit` ORM model mirrors that DDL but is NOT the
source of truth — never run `Base.metadata.create_all(...)` against the
live DB.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by the ORM-flavored models below.
Base = declarative_base()
SCHEMA = "daily_life"

# SQLAlchemy ORM — audit-writer surface.
from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

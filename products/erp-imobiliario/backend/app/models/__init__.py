"""Domain models for erp-imobiliario.

This package was introduced 2026-05-11 (LLM-ERP rollout, Step B) to host
the single SQLAlchemy ORM class the seed
`noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
contract requires.

ERP's primary data path is the Supabase admin client (Pydantic-typed
PostgREST rows handled in `app/services/*.py`); SQLAlchemy is used here
*only* for the `ToolCallAudit` table so the seed audit writer can persist
rows. Mirror of `products/media-scheduling/backend/app/models/__init__.py`
— hybrid Supabase + minimal SQLAlchemy layout.

The actual schema lives in `migrations/030_tool_call_audits.sql` (mirrored
via Supabase MCP). The ORM here mirrors that DDL but is NOT the source of
truth — never run `Base.metadata.create_all(...)` against the live DB.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy base — used only by `ToolCallAudit` below.
Base = declarative_base()
SCHEMA = "erp"

from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

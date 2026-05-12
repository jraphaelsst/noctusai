"""SQLAlchemy ORM models for mailing.

Mailing is Supabase-client-native — `app/services/*` consume Pydantic
DTOs from `app/schemas/*` against `mailing.*` tables via the seed admin
client (per `ProductSettings` + `noctusai_seed.database`).

The ONE exception is `ToolCallAudit`: the seed-shipped audit primitive
`noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
requires a SQLAlchemy ORM class bound to a session. This module exists
only to satisfy that contract — do NOT add other ORM models here without
moving the product onto a SQLAlchemy-first data path.

Coexists harmlessly with the Pydantic value-objects in `app/schemas/`:
the audit hook is the only SQLAlchemy consumer.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by the ORM-flavored models below.
Base = declarative_base()
SCHEMA = "mailing"

from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

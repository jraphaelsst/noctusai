"""SQLAlchemy ORM models for the social-wiring ``email_marketing`` module.

The email-marketing module is Supabase-client-native — its
``services/*`` consume Pydantic DTOs from ``schemas/*`` against
``social_wiring.*`` tables via the seed admin client.

The ONE exception is :class:`ToolCallAudit`: the seed-shipped audit
primitive ``noctusai_lib.domain.ai.tool_audit.make_audit_writer(db,
table_class)`` requires a SQLAlchemy ORM class bound to a session. This
module exists only to satisfy that contract — do NOT add other ORM
models here without moving the module onto a SQLAlchemy-first data path.

Ported from ``products/mailing/backend/app/models`` during the
social-wiring absorption (Wave 2.2). The audit table now lives in the
``social_wiring`` schema (was ``mailing``) — see ``SCHEMA`` below.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# Module-local SQLAlchemy base — isolated from any other module's ORM
# metadata so the email_marketing audit table is the only mapped class.
Base = declarative_base()
SCHEMA = "social_wiring"

from app.modules.email_marketing.models.tool_call_audit import (  # noqa: E402,F401
    ToolCallAudit,
)

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]

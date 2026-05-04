"""SQLAlchemy ORM models for media_scheduling product tables.

These models are minimal — they exist primarily so:
  - The seed `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
    contract has a concrete `ToolCallAudit` class to instantiate per the
    `KB § PATTERNS/llm-tool-audit.md` recipe.
  - Future SQLAlchemy-using surfaces (audit retention sweep, conversation
    summary backfill, etc.) have a typed shape to bind to.

Routers in Phase 3 currently use the Supabase admin client directly per the
PROJECT.md §2 "DB — Supabase, not SQLAlchemy/Alembic" decision; the ORM
models do NOT replace that — they coexist for the seed-pattern surfaces
that require a typed table_class.

The actual schema lives in `migrations/002_initial_schema.sql` (mirrored
via Supabase MCP). These models mirror that DDL but are NOT the source of
truth — never run `Base.metadata.create_all(...)` against the live DB.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# Single Base for all media_scheduling ORM models. The MetaData carries
# `schema="media_scheduling"` so any future Table introspection or test
# fixture knows which Postgres schema the rows land in.
Base = declarative_base()
SCHEMA = "media_scheduling"


from app.models.appointment import Appointment  # noqa: E402,F401
from app.models.authorized_user import AuthorizedUser  # noqa: E402,F401
from app.models.condominium import Condominium  # noqa: E402,F401
from app.models.conversation_summary import ConversationSummary  # noqa: E402,F401
from app.models.oauth_credential import OAuthCredential  # noqa: E402,F401
from app.models.pending_chat_identity import PendingChatIdentity  # noqa: E402,F401
from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Appointment",
    "AuthorizedUser",
    "Base",
    "Condominium",
    "ConversationSummary",
    "OAuthCredential",
    "PendingChatIdentity",
    "SCHEMA",
    "ToolCallAudit",
]

"""Domain models for media_scheduling.

Hybrid layout (settled at the Phase 3 + Phase 4 merge — see §11 in
projects/media-scheduling-port/PROJECT.md):

- **Pydantic** for everything the Supabase-client services touch
  (Engineer D pattern). The product is Supabase-client-native per
  PROJECT.md §2 — these are value-objects that type-narrow row dicts
  returned by Supabase.

- **SQLAlchemy ORM** for `ToolCallAudit` only — the seed
  `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)`
  contract requires a SQLAlchemy class. Engineer C also kept
  `ConversationSummary` + `PendingChatIdentity` as ORM (speculative;
  no current consumer; harmless coexistence with `Base/SCHEMA`).

The actual schema lives in `migrations/00X_*.sql` (mirrored via Supabase
MCP). Models mirror that DDL but are NOT the source of truth — never run
`Base.metadata.create_all(...)` against the live DB.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by the ORM-flavored models below.
Base = declarative_base()
SCHEMA = "media_scheduling"

# Pydantic value objects (Supabase-client services consume these).
from app.models.appointment import Appointment  # noqa: E402,F401
from app.models.authorized_user import AuthorizedUser  # noqa: E402,F401
from app.models.condominium import Condominium  # noqa: E402,F401
from app.models.crew_skill import CrewSkill  # noqa: E402,F401
from app.models.oauth_credential import OAuthCredential  # noqa: E402,F401
from app.models.property import Property  # noqa: E402,F401
from app.models.route_group import RouteGroup  # noqa: E402,F401
from app.models.service_type import ServiceType  # noqa: E402,F401

# SQLAlchemy ORM (audit-writer + speculative future ORM surfaces).
from app.models.conversation_summary import ConversationSummary  # noqa: E402,F401
from app.models.pending_chat_identity import PendingChatIdentity  # noqa: E402,F401
from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Appointment",
    "AuthorizedUser",
    "Base",
    "Condominium",
    "ConversationSummary",
    "CrewSkill",
    "OAuthCredential",
    "PendingChatIdentity",
    "Property",
    "RouteGroup",
    "SCHEMA",
    "ServiceType",
    "ToolCallAudit",
]

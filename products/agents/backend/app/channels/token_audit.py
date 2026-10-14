"""Audit trail of channel-token mint / revoke (Lais contract §10.1 M1: "every
mint and revoke is audit-logged").

Reuses ``agents.api_token_audit`` (migration 007) — the table the seed writes a
row per product-token REQUEST into — with the lifecycle action as ``method``
(``MINT`` / ``REVOKE``) and a path naming the agent and the acting user. One
structured log line is emitted too; neither carries a secret (the token row id
and prefix only).

Seed IO shape: ``TokenAudit`` Protocol + ``FakeTokenAudit`` +
``SupabaseTokenAudit`` + ``get_token_audit(settings)``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from app.stores._util import utcnow, utcnow_iso

logger = logging.getLogger(__name__)

__all__ = [
    "AuditRow",
    "FakeTokenAudit",
    "SupabaseTokenAudit",
    "TokenAudit",
    "get_token_audit",
]

Action = Literal["MINT", "REVOKE"]


@dataclass(frozen=True)
class AuditRow:
    api_token_id: UUID
    org_id: UUID
    method: str
    path: str
    status: int
    at: datetime


class TokenAudit(Protocol):
    def record(
        self, *, api_token_id: UUID, org_id: UUID, action: Action, agent_key: str,
        actor_user_id: UUID | None, status: int,
    ) -> None:
        """Append one audit row. Raises on a write failure: an unaudited
        mint must not look like a success (the caller revokes it)."""
        ...


def _path(agent_key: str, actor_user_id: UUID | None) -> str:
    return f"channel-token:{agent_key}:by:{actor_user_id}"


class FakeTokenAudit:
    def __init__(self) -> None:
        self.rows: list[AuditRow] = []
        self.fail = False

    def record(self, *, api_token_id, org_id, action, agent_key, actor_user_id, status):
        if self.fail:
            raise RuntimeError("fake audit failure")
        self.rows.append(AuditRow(
            api_token_id=api_token_id, org_id=org_id, method=action,
            path=_path(agent_key, actor_user_id), status=status, at=utcnow(),
        ))
        logger.info(
            "agents.channel_token.%s org_id=%s token_id=%s agent=%s",
            action.lower(), org_id, api_token_id, agent_key,
        )


class SupabaseTokenAudit:
    def __init__(self, client: Any) -> None:
        self._client = client

    def record(self, *, api_token_id, org_id, action, agent_key, actor_user_id, status):
        self._client.schema("agents").table("api_token_audit").insert({
            "api_token_id": str(api_token_id), "org_id": str(org_id), "method": action,
            "path": _path(agent_key, actor_user_id), "status": status, "at": utcnow_iso(),
        }).execute()
        logger.info(
            "agents.channel_token.%s org_id=%s token_id=%s agent=%s",
            action.lower(), org_id, api_token_id, agent_key,
        )


def get_token_audit(settings: Any) -> TokenAudit:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeTokenAudit()
    from app.database import get_admin_client

    return SupabaseTokenAudit(get_admin_client())

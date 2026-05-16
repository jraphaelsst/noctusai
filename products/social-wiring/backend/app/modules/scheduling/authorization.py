"""LID-aware inbound authorization for the social-wiring ``scheduling``
module. Absorbed from ``imobi-scheduling`` (Wave 2.3).

Resolves a WhatsApp inbound chat → an authorized scheduling-domain user
(agency staff / media crew) via three paths:

1. **LID path** — ``sched_users.linked_identity = chat_id``.
2. **Phone fallback** — normalized ``sched_users.phone_number``.
3. **Opportunistic LID capture** — attach a freshly-seen LID onto the
   phone-matched user for next time.
4. **Deferred-auth** — park a ``sched_pending_chat_identities`` row when
   both paths fail and the chat is a LID.

Schema is ``social_wiring``; tables are ``sched_*``-prefixed (scheduling
domain). RLS scopes by ``org_id``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"


def normalize_phone_number(phone_number: str | None) -> str:
    """Reduce a raw phone string to ``+<digits>`` shape. Empty string for
    inputs with no digits (callers treat that as "no phone supplied")."""
    if not phone_number:
        return ""
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return ""
    return f"+{digits}"


def looks_like_lid(chat_id: str | None) -> bool:
    """True for WhatsApp Linked-Identifier chat IDs
    (``<digits>@lid_<hex>`` / ``<digits>@lid``)."""
    if not chat_id:
        return False
    return "@lid_" in chat_id or chat_id.endswith("@lid")


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """``authorized=True`` requires ``user_id`` populated.
    ``authorized=False`` may still carry ``lid`` so the caller can park
    a pending-chat-identity row."""

    authorized: bool
    user_id: UUID | None = None
    lid: str | None = None
    role: str | None = None


class AuthorizationService:
    """Per-request LID-aware authorization. Per-request construction from
    a Supabase client (service-role when called from the webhook
    worker). Schema-scoped to ``social_wiring``."""

    SCHEMA = SCHEMA

    def __init__(self, client: Any, *, org_id: UUID | str) -> None:
        self._client = client
        self._org_id = str(org_id)
        self._scoped = client.schema(self.SCHEMA)

    def authorize_inbound(
        self,
        *,
        chat_id: str | None,
        from_phone: str | None = None,
        push_name: str | None = None,
    ) -> AuthorizationResult:
        lid = chat_id if looks_like_lid(chat_id) else None

        if lid:
            user = self._lookup_user_by_lid(lid)
            if user is not None:
                return AuthorizationResult(
                    authorized=True,
                    user_id=UUID(str(user["id"])),
                    lid=lid,
                    role=user.get("role"),
                )

        normalized = normalize_phone_number(from_phone)
        if normalized:
            user = self._lookup_user_by_phone(normalized)
            if user is not None:
                if lid and user.get("linked_identity") != lid:
                    self._attach_lid_to_user(
                        user_id=user["id"], lid=lid, from_phone=normalized
                    )
                return AuthorizationResult(
                    authorized=True,
                    user_id=UUID(str(user["id"])),
                    lid=lid,
                    role=user.get("role"),
                )

        return AuthorizationResult(authorized=False, user_id=None, lid=lid, role=None)

    def park_pending_lid(
        self,
        chat_id: str,
        *,
        push_name: str | None = None,
        phone_hint: str | None = None,
    ) -> dict:
        """Insert (or refresh) a ``sched_pending_chat_identities`` row.
        Idempotent on ``(org_id, chat_id)`` via the DB UNIQUE constraint."""
        payload = {
            "org_id": self._org_id,
            "chat_id": chat_id,
            "push_name": push_name,
            "phone_hint": phone_hint,
            "status": "pending",
        }
        try:
            response = (
                self._scoped
                .table("sched_pending_chat_identities")
                .insert(payload)
                .execute()
            )
            rows = response.data or []
            row = rows[0] if rows else payload
            logger.info(
                "Parked pending LID: chat_id=%s org_id=%s push_name=%s",
                chat_id, self._org_id, push_name or "<unknown>",
            )
            return row
        except Exception as exc:  # noqa: BLE001 — UNIQUE conflict is benign.
            logger.info(
                "Pending LID already parked or insert failed: chat_id=%s err=%s",
                chat_id, exc,
            )
            return payload

    def _lookup_user_by_lid(self, lid: str) -> dict | None:
        response = (
            self._scoped
            .table("sched_users")
            .select("id, role, phone_number, linked_identity, active, org_id")
            .eq("linked_identity", lid)
            .eq("active", True)
            .eq("org_id", self._org_id)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def _lookup_user_by_phone(self, normalized_phone: str) -> dict | None:
        response = (
            self._scoped
            .table("sched_users")
            .select("id, role, phone_number, linked_identity, active, org_id")
            .eq("phone_number", normalized_phone)
            .eq("active", True)
            .eq("org_id", self._org_id)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def _attach_lid_to_user(
        self,
        *,
        user_id: str | UUID,
        lid: str,
        from_phone: str,
    ) -> None:
        try:
            (
                self._scoped
                .table("sched_users")
                .update({"linked_identity": lid})
                .eq("id", str(user_id))
                .eq("org_id", self._org_id)
                .execute()
            )
            logger.info(
                "Captured LID %s for user_id=%s (matched on phone %s)",
                lid, user_id, from_phone,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; auth already decided.
            logger.warning(
                "LID capture failed for user_id=%s lid=%s: %s",
                user_id, lid, exc,
            )


__all__ = [
    "AuthorizationResult",
    "AuthorizationService",
    "looks_like_lid",
    "normalize_phone_number",
]

"""
Authorization service for the WhatsApp scheduling bot — LID-aware inbound resolution.

The bot's webhook receives WhatsApp inbound messages and must decide whether
the chat is from an *authorized* user (agency staff or media crew). Resolution
is two-pathed:

1. **Phone path** — the WAHA payload always carries the sender phone. We
   normalize and look up `imobi_scheduling.users.phone_number`. A match means
   "authorized".

2. **LID path** — WhatsApp's Linked Identifier (`@lid_<hex>` chats) hides the
   underlying phone. We persist a mapping `users.linked_identity = chat_id`
   so subsequent LID inbounds resolve without a phone hint. Opportunistic
   capture: when a phone match succeeds AND the chat_id is a LID we haven't
   seen, attach it for next time.

3. **Deferred-auth** — when neither path resolves and the chat looks like a
   LID, we park a `pending_chat_identities` row (status=pending) so an
   admin can later resolve. If that row is later resolved
   (status=resolved + resolved_to_user_id), subsequent LID inbounds hit
   path 1 via the user's linked_identity which the admin-resolver sets
   on the user row at resolve-time.

Returns are an `AuthorizationResult` value object — `authorized: bool`,
`user_id: UUID | None`, `lid: str | None`, `role: str | None`. Callers
(the webhook handler, the conversation worker) act on `authorized` and
keep `user_id` for downstream attribution.

Pattern: thin service. The router/webhook owns IO orchestration; this
service owns the lookup logic + opportunistic capture. RLS scopes per
the user-bound Supabase client (`org_id`). For inbound webhook handling
the client may be a service-role admin client — single-agency v1 (Phase
0 Q4): all data is one agency, so `org_id` is fixed per deployment.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — pure, no IO
# ---------------------------------------------------------------------------

def normalize_phone_number(phone_number: str | None) -> str:
    """Reduce a raw phone string to `+<digits>` shape.

    WAHA payloads carry phones in `<digits>@c.us` or `+<digits>` form;
    `users.phone_number` is stored as `+<digits>`. This bridges both.

    Returns the empty string for inputs that contain no digits — callers
    treat that as "no phone supplied".
    """
    if not phone_number:
        return ""
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return ""
    return f"+{digits}"


def looks_like_lid(chat_id: str | None) -> bool:
    """True for WhatsApp Linked-Identifier chat IDs.

    Two shapes seen in WAHA payloads: `<digits>@lid_<hex>` and the rarer
    `<digits>@lid`. Both denote that the underlying phone is hidden
    behind WhatsApp's LID system — we treat them as opaque user
    identifiers.
    """
    if not chat_id:
        return False
    return "@lid_" in chat_id or chat_id.endswith("@lid")


# ---------------------------------------------------------------------------
# Result value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Outcome of a webhook authorization attempt.

    `authorized=True` requires `user_id` populated (the user row that
    owns the inbound). `authorized=False` may still carry `lid` so the
    caller can park a `pending_chat_identities` row.
    """

    authorized: bool
    user_id: UUID | None = None
    lid: str | None = None
    role: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AuthorizationService:
    """LID-aware authorization for inbound WhatsApp chats.

    Per-request construction from a Supabase client (RLS-bound to JWT
    when called by an authenticated request; service-role when called
    from the webhook worker). The schema is `imobi_scheduling`; the
    service uses `.schema(...)` to scope queries.
    """

    SCHEMA = "imobi_scheduling"

    def __init__(self, client: Any, *, org_id: UUID | str) -> None:
        self._client = client
        self._org_id = str(org_id)
        # Bind the schema-scoped client once. Supabase's `.schema(name)` returns
        # a fresh client per call; caching here both saves the per-call
        # construction AND lets tests observe writes by reading
        # `client.schema("imobi_scheduling").table("...").inserted_payloads`
        # (caching on the test-side via a single fixture).
        self._scoped = client.schema(self.SCHEMA)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def authorize_inbound(
        self,
        *,
        chat_id: str | None,
        from_phone: str | None = None,
        push_name: str | None = None,
    ) -> AuthorizationResult:
        """Resolve an inbound WhatsApp chat to an authorized user.

        Resolution order:

          1. **LID path** — if `chat_id` looks like a LID, look up
             `users.linked_identity = chat_id`. Match → authorized.
          2. **Phone fallback** — normalize `from_phone`, look up
             `users.phone_number = normalized`. Match → authorized.
          3. **Opportunistic LID capture** — if path 2 succeeded AND
             `chat_id` is a LID we haven't seen on this user yet,
             persist it (`linked_identity = chat_id`) so path 1 hits
             next time. Failure to persist does not flip the result —
             auth is decided before capture.
          4. **Deferred-auth** — if both paths fail AND `chat_id` is a
             LID, the caller is expected to park a
             `pending_chat_identities` row via `park_pending_lid`. We
             return `authorized=False` with `lid=chat_id` so the caller
             knows there's a LID to park.

        Inactive users (`active=False`) are excluded from both paths —
        the bot should not honor a deactivated account.
        """
        lid = chat_id if looks_like_lid(chat_id) else None

        # Path 1: explicit LID lookup.
        if lid:
            user = self._lookup_user_by_lid(lid)
            if user is not None:
                return AuthorizationResult(
                    authorized=True,
                    user_id=UUID(str(user["id"])),
                    lid=lid,
                    role=user.get("role"),
                )

        # Path 2: phone fallback.
        normalized = normalize_phone_number(from_phone)
        if normalized:
            user = self._lookup_user_by_phone(normalized)
            if user is not None:
                # Path 3: opportunistic LID capture.
                if lid and user.get("linked_identity") != lid:
                    self._attach_lid_to_user(user_id=user["id"], lid=lid, from_phone=normalized)
                return AuthorizationResult(
                    authorized=True,
                    user_id=UUID(str(user["id"])),
                    lid=lid,
                    role=user.get("role"),
                )

        # Path 4: unauthorized — surface lid for deferred-auth parking.
        return AuthorizationResult(authorized=False, user_id=None, lid=lid, role=None)

    # ------------------------------------------------------------------
    # Deferred-auth: pending_chat_identities lifecycle
    # ------------------------------------------------------------------

    def park_pending_lid(
        self,
        chat_id: str,
        *,
        push_name: str | None = None,
        phone_hint: str | None = None,
    ) -> dict:
        """Insert (or refresh) a `pending_chat_identities` row.

        Use when `authorize_inbound` returned `authorized=False` with a
        `lid` set. The row carries `status='pending'` until an admin
        resolves it. The row is idempotent on `(org_id, chat_id)` —
        callers may invoke repeatedly without duplicate inserts; the
        UNIQUE constraint enforces it at the DB layer.

        Returns the inserted/updated row as a dict. On race with another
        worker, the DB raises a uniqueness violation; the caller should
        re-fetch.
        """
        payload = {
            "org_id": self._org_id,
            "chat_id": chat_id,
            "push_name": push_name,
            "phone_hint": phone_hint,
            "status": "pending",
        }
        # Insert; rely on the table's UNIQUE (org_id, chat_id) constraint
        # for idempotency. On constraint violation (concurrent worker
        # already parked the same chat) the caller can re-fetch the
        # row — for the inbound webhook path the side effect (pending
        # row exists, awaiting admin) is achieved either way.
        # Admin-side resolve/reject paths live on a dedicated router
        # (filed for Phase 12 admin surface follow-up).
        try:
            response = (
                self._scoped
                .table("pending_chat_identities")
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
            # Surface — do not silently swallow. Caller decides whether to
            # re-fetch the existing row. Common case: another worker beat
            # us to it; the desired side effect (row exists) is already
            # achieved.
            logger.info(
                "Pending LID already parked or insert failed: chat_id=%s err=%s",
                chat_id, exc,
            )
            return payload

    # ------------------------------------------------------------------
    # Internal lookups
    # ------------------------------------------------------------------

    def _lookup_user_by_lid(self, lid: str) -> dict | None:
        """Find an active user whose `linked_identity` matches the LID."""
        response = (
            self._scoped
            .table("users")
            .select("id, role, phone_number, linked_identity, active, org_id")
            .eq("linked_identity", lid)
            .eq("active", True)
            .eq("org_id", self._org_id)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def _lookup_user_by_phone(self, normalized_phone: str) -> dict | None:
        """Find an active user whose `phone_number` matches the normalized phone."""
        response = (
            self._scoped
            .table("users")
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
        """Persist a freshly-captured LID onto the user row.

        Best-effort: if the UPDATE fails (RLS rejects, race with another
        worker), the auth result already passed back via path 2 stays
        valid; the next inbound just re-runs path 2 + retries capture.
        Log + continue.
        """
        try:
            (
                self._scoped
                .table("users")
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
            # Surface but do NOT raise — auth result stays valid.
            logger.warning(
                "LID capture failed for user_id=%s lid=%s: %s",
                user_id, lid, exc,
            )

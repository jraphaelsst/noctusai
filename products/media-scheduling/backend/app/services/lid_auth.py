"""LID-aware first-inbound capture.

WhatsApp delivers two chat-id shapes via WAHA:

  - `<digits>@c.us` — the legacy public-phone shape; safely mapped to
    `authorized_users.phone_number`.
  - `<digits>@lid_<hex>` — the Linked Identifier shape; **opaque per-device
    identifier** that does NOT match the public phone digits exactly. We
    treat these as separate chat addresses and capture them on the user
    row (`authorized_users.linked_identity`) once we've matched via phone
    fallback.

Resolution order (mirror of source `AuthorizationService.authorized_user_for_chat_id`):

  1. If `chat_id` is a `@lid_*` form, look up `authorized_users.linked_identity == chat_id`.
  2. Else (or if path 1 misses), look up by `from_phone` (which the WAHA
     payload always carries — even on LID chats).
  3. If path 2 hit AND `chat_id` is a LID we hadn't seen before, capture
     it on the user row so the next inbound matches via path 1 directly.
  4. If nothing matches AND `chat_id` is a LID, park it in
     `pending_chat_identities` so an admin can resolve it later.

**Accept-with-rationale** (PROJECT.md §2 + §7 Q1): this lives product-side
rather than in the seed because:

  - LID is a WhatsApp-specific identity quirk; the `noctusai_lib.integrations.whatsapp`
    surface stays channel-neutral so swapping to Twilio / Cloud API later
    doesn't drag LID semantics across.
  - Only one product needs LID-aware auth today (this one). When N=2+
    products surface the same shape, the recurrence rule fires and this
    code gets absorbed — see `KB § PATTERNS/accept-with-rationale.md`
    entry "LID-aware first-inbound capture".

Operates on the Supabase admin client (RLS bypass — webhook path runs as
service_role per PROJECT.md §6 Phase 2 `003_rls.sql`).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def normalize_phone_number(phone_number: str | None) -> str:
    """Strip non-digits, prefix `+`. Empty input → empty string."""
    if not phone_number:
        return ""
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return ""
    return f"+{digits}"


def looks_like_lid(chat_id: str | None) -> bool:
    """`@lid_<hex>` chat IDs come from WhatsApp's Linked Identifier system.
    Treat them as opaque per-device identifiers, not phone numbers."""
    if not chat_id:
        return False
    return "@lid_" in chat_id or chat_id.endswith("@lid")


class LidAuthService:
    """Resolve inbound WAHA chat_id → authorized_users row.

    The Supabase admin client is the data path (service_role; RLS bypass).
    The class is intentionally stateless beyond the client + table-prefix
    cache so multiple worker / webhook invocations can share an instance.
    """

    table_users = "authorized_users"
    table_pending = "pending_chat_identities"

    def __init__(self, admin_client: Any):
        self.db = admin_client

    def authorized_user_for_phone(self, phone_number: str) -> dict[str, Any] | None:
        normalized = normalize_phone_number(phone_number)
        if not normalized:
            return None
        result = (
            self.db.table(self.table_users)
            .select("*")
            .eq("phone_number", normalized)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def authorized_user_for_chat_id(
        self,
        chat_id: str | None,
        *,
        from_phone: str | None = None,
        push_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve inbound to a user row, capturing the LID opportunistically.

        Returns the user dict on hit; None on miss. Caller decides what to
        do on miss — webhook handler parks unknown LIDs via `capture_pending_lid`.
        """
        # Path 1: explicit LID lookup
        if looks_like_lid(chat_id):
            result = (
                self.db.table(self.table_users)
                .select("*")
                .eq("linked_identity", chat_id)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows:
                return rows[0]

        # Path 2: phone fallback
        if from_phone:
            user = self.authorized_user_for_phone(from_phone)
            if user is not None:
                # Path 3: opportunistic capture
                if (
                    looks_like_lid(chat_id)
                    and user.get("linked_identity") != chat_id
                ):
                    try:
                        self.db.table(self.table_users).update(
                            {"linked_identity": chat_id}
                        ).eq("id", user["id"]).execute()
                        user["linked_identity"] = chat_id
                        logger.info(
                            "LID captured for authorized_user id=%s chat_id=%s phone=%s",
                            user["id"],
                            chat_id,
                            from_phone,
                        )
                    except Exception:
                        # Capture is best-effort — log but don't fail the inbound.
                        logger.exception(
                            "LID capture failed for user_id=%s chat_id=%s",
                            user["id"],
                            chat_id,
                        )
                # Push-name backfill: keep the user's display name fresh if
                # WAHA carries a more current one.
                if push_name and user.get("name") != push_name:
                    try:
                        self.db.table(self.table_users).update(
                            {"name": push_name}
                        ).eq("id", user["id"]).execute()
                        user["name"] = push_name
                    except Exception:
                        logger.exception(
                            "push_name backfill failed for user_id=%s",
                            user["id"],
                        )
                return user

        return None

    def capture_pending_lid(
        self,
        chat_id: str,
        *,
        push_name: str | None = None,
        phone_hint: str | None = None,
    ) -> dict[str, Any] | None:
        """Park an unknown `@lid_*` chat for admin resolution.

        Idempotent on `chat_id`. Returns the upserted/refreshed row, or
        None if the operation failed (logged at WARNING — webhook should
        keep going so the user still gets a "pending" reply).
        """
        try:
            existing_result = (
                self.db.table(self.table_pending)
                .select("*")
                .eq("chat_id", chat_id)
                .limit(1)
                .execute()
            )
            existing_rows = existing_result.data or []
            now_iso = datetime.now(timezone.utc).isoformat()

            if existing_rows:
                existing = existing_rows[0]
                if existing.get("status") == "pending":
                    update: dict[str, Any] = {"captured_at": now_iso}
                    if push_name and not existing.get("push_name"):
                        update["push_name"] = push_name
                    if phone_hint and not existing.get("phone_hint"):
                        update["phone_hint"] = phone_hint
                    if len(update) > 1:
                        self.db.table(self.table_pending).update(update).eq(
                            "id", existing["id"]
                        ).execute()
                        existing.update(update)
                return existing

            insert_payload = {
                "chat_id": chat_id,
                "push_name": push_name,
                "phone_hint": phone_hint,
                "status": "pending",
                "captured_at": now_iso,
            }
            insert_result = (
                self.db.table(self.table_pending).insert(insert_payload).execute()
            )
            inserted = (insert_result.data or [insert_payload])[0]
            logger.info(
                "Pending chat identity captured: chat_id=%s push_name=%s",
                chat_id,
                push_name or "<unknown>",
            )
            return inserted
        except Exception:
            logger.exception(
                "capture_pending_lid failed for chat_id=%s — proceeding without park",
                chat_id,
            )
            return None

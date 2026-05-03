"""TherapyGcalCredentialResolver — adapts therapy.therapist_profiles
columns to `noctusai_lib.integrations.google_calendar.CalendarCredentialResolver`.

Resolves to `OAuthCalendarCredentials` per the per-therapist GCal
columns added by migration 011. Returns `None` (→ Fake adapter
fallback) when:
  - the therapist has no stored token, OR
  - `gcal_authorization_is_fresh()` returns FALSE (7-day re-auth gate).

Decryption goes through the `therapy.decrypt_gcal_token(bytea)` SQL
helper (SECURITY DEFINER, Vault-keyed) — the resolver never sees the
plaintext key.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.integrations.google_calendar import OAuthCalendarCredentials

logger = logging.getLogger(__name__)


class TherapyGcalCredentialResolver:
    """Per-therapist Google Calendar credential resolver.

    `tenant_id` is the therapist's `user_id` (PK of
    `therapy.therapist_profiles`).
    """

    def __init__(
        self,
        db: Any,
        client_id: str | None,
        client_secret: str | None,
    ) -> None:
        self._db = db
        self._client_id = client_id
        self._client_secret = client_secret

    def get_credentials(self, tenant_id: str | None) -> OAuthCalendarCredentials | None:
        if not tenant_id:
            return None
        if not self._client_id or not self._client_secret:
            logger.debug("GCal OAuth client not configured; falling back to Fake")
            return None

        row_resp = (
            self._db.table("therapist_profiles")
            .select(
                "gcal_refresh_token_encrypted, gcal_calendar_id, gcal_authorized_at"
            )
            .eq("user_id", tenant_id)
            .limit(1)
            .execute()
        )
        rows = getattr(row_resp, "data", None) or []
        if not rows:
            return None
        row = rows[0]
        ciphertext = row.get("gcal_refresh_token_encrypted")
        if ciphertext is None:
            return None

        fresh_resp = self._db.rpc(
            "gcal_authorization_is_fresh",
            {"authorized_at": row.get("gcal_authorized_at")},
        ).execute()
        if not bool(getattr(fresh_resp, "data", False)):
            logger.info(
                "therapist %s GCal authorization stale (>7d); requiring re-OAuth",
                tenant_id,
            )
            return None

        decrypt_resp = self._db.rpc(
            "decrypt_gcal_token",
            {"ciphertext": ciphertext},
        ).execute()
        refresh_token = getattr(decrypt_resp, "data", None)
        if not refresh_token:
            return None

        return OAuthCalendarCredentials(
            refresh_token=refresh_token,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

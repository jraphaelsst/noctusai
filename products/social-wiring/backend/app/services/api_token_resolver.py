"""DB-backed ``ApiTokenResolver`` — looks up ``pk_*`` tokens in
``social_wiring.api_tokens``.

Composes the seed :class:`noctusai_lib.api.auth.session.ApiTokenResolver`
Protocol. Resolution:

  1. Reject anything that doesn't start with ``pk_`` (cheap pre-filter).
  2. ``hash_token(secret)`` → SHA-256 hex digest.
  3. SELECT row by ``token_hash`` from ``social_wiring.api_tokens``,
     filtered to ``revoked_at IS NULL``.
  4. On hit: best-effort ``UPDATE last_used_at = now()`` (log + continue
     on failure — read path must never break on a stats update), return
     ``AuthContext(caller_kind="product", ...)``.
  5. On miss: return ``None`` — the dep translates to 401.

The lookup uses the **admin** supabase client because RLS would block
the SELECT: the caller hasn't authenticated yet — resolving the bearer
IS the authentication step. The user-scoped JWT path doesn't exist for
``pk_*`` callers, so the admin client is the only credential available.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.api.auth.session import (
    ApiTokenResolver,
    AuthContext,
    hash_token,
)

logger = logging.getLogger(__name__)

_TABLE = "api_tokens"
_SCHEMA = "social_wiring"


class SupabaseApiTokenResolver(ApiTokenResolver):
    """Concrete :class:`ApiTokenResolver` over a Supabase admin client.

    Args:
        admin_supabase: A supabase client built with the service-role
            key (i.e. ``DatabaseModule.get_admin_client()`` or the
            equivalent ``get_admin_client()`` helper in
            ``app.dependencies``). RLS would otherwise prevent the
            lookup since the caller is, by definition, not yet
            authenticated.
    """

    def __init__(self, admin_supabase: Any) -> None:
        self._sb = admin_supabase

    async def resolve(self, token_secret: str) -> AuthContext | None:
        # Cheap pre-filter — the dep already gates on this prefix but
        # ``ApiTokenResolver`` is a Protocol callers may invoke directly,
        # so we re-check here for defense in depth.
        if not token_secret.startswith("pk_"):
            return None

        digest = hash_token(token_secret)

        try:
            response = (
                self._sb.schema(_SCHEMA)
                .table(_TABLE)
                .select("id, org_id, scopes, revoked_at")
                .eq("token_hash", digest)
                .is_("revoked_at", None)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "api_token_lookup_failed digest_prefix=%s", digest[:8]
            )
            return None

        rows = response.data or []
        if not rows:
            return None

        row = rows[0]
        try:
            token_id = UUID(str(row["id"]))
            org_id = UUID(str(row["org_id"]))
        except (KeyError, ValueError, TypeError):
            logger.warning(
                "api_token_row_malformed digest_prefix=%s row_keys=%s",
                digest[:8],
                list(row.keys()) if isinstance(row, dict) else type(row).__name__,
            )
            return None

        scopes = list(row.get("scopes") or [])

        # Best-effort last_used_at bump. Failure here must not break
        # the auth path — log and continue. Tests assert this column
        # is touched on every successful resolve.
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            (
                self._sb.schema(_SCHEMA)
                .table(_TABLE)
                .update({"last_used_at": now_iso})
                .eq("id", str(token_id))
                .execute()
            )
        except Exception:
            logger.warning(
                "api_token_last_used_update_failed token_id=%s", token_id
            )

        return AuthContext(
            org_id=org_id,
            caller_kind="product",
            user_id=None,
            scopes=scopes,
            raw_token=str(token_id),
            api_token_id=token_id,
        )


__all__ = ["SupabaseApiTokenResolver"]

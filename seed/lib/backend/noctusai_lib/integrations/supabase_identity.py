"""Supabase Auth identity resolver.

Bulk display-name + email lookup for `auth.users` given a list of user IDs.
Every product whose admin / list endpoints aggregate rows from product
tables (therapist_profiles, patient_profiles, clinics, ERP brokers, etc.)
needs `nome` + `email` from `auth.users` — which lives outside the product
schema. This helper centralizes the lookup so we don't reinvent the
"fetch identity for an arbitrary list of UUIDs" pattern in every service.

**Layer.** `integrations/` per `KB § PATTERNS/seed-lib-layout.md` — wraps
the Supabase auth.admin SDK (an external-service boundary), sibling to
`database.py`, `redis.py`, `email/`, `whatsapp/`, `vista/`,
`google_calendar/`, `google_maps/`, `llm/`.

**Sync vs async.** This function is `def` (sync), not `async def`. The
underlying `supabase-py` admin SDK is sync — wrapping in `async def`
would block the event loop at every `db.auth.admin.get_user_by_id(...)`
call without yielding. Callers that need non-blocking concurrency wrap
with `asyncio.to_thread(fetch_user_identities, db, ids)`. For typical
admin pages (10-100 IDs), a sequential loop completes in well under a
second and is fine on the request path.

**Errors return shape, not exceptions.** Per-user lookup failures
(stale ID, deleted user, transient admin-API error) are caught + logged
at WARNING and the function returns a `UserIdentity` with empty `nome`
/ `email` for that ID. Callers get a deterministic shape for every
requested ID — admin list endpoints don't 500 because of one stale row.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserIdentity:
    """Display-name + email + avatar for a Supabase auth user.

    `nome`: best-effort display name from `user_metadata.nome` or
        `user_metadata.full_name`. Empty string when neither exists.
    `email`: user's auth email; empty string when lookup failed.
    `foto_url`: optional avatar URL from `user_metadata.foto_url` or
        `user_metadata.avatar_url`.

    Use `display_name` for the rendering fallback chain
    (nome → email-local-part → "Usuário"). The fallback chain is
    centralized here so admin pages, therapist directories, patient
    cards, and chat avatars all degrade the same way for users that
    signed up with only an email and no name.
    """

    user_id: str
    nome: str = ""
    email: str = ""
    foto_url: str | None = None

    @property
    def display_name(self) -> str:
        """Fallback chain: nome → email local-part → 'Usuário'."""
        if self.nome:
            return self.nome
        if self.email and "@" in self.email:
            return self.email.split("@")[0]
        return "Usuário"


def fetch_user_identities(
    db: Any,
    user_ids: Iterable[str],
) -> Dict[str, UserIdentity]:
    """Resolve a batch of Supabase auth.users → UserIdentity, keyed by user_id.

    Args:
        db: An admin-scoped Supabase client (must expose
            `db.auth.admin.get_user_by_id(user_id)`).
        user_ids: Iterable of user UUIDs. Duplicates and falsy values
            (None, "") are silently skipped; the result dict naturally
            dedupes.

    Returns:
        Dict mapping every distinct truthy user_id to a UserIdentity.
        Missing users (deleted, not found, lookup error) are still keyed
        but with empty `nome` / `email` — see module docstring on
        deterministic shape.

    Examples:
        >>> ids = ["uuid-a", "uuid-b", "uuid-a"]  # duplicate intentional
        >>> result = fetch_user_identities(admin_client, ids)
        >>> sorted(result.keys())
        ['uuid-a', 'uuid-b']
        >>> result["uuid-a"].display_name
        'Alice'
    """
    result: Dict[str, UserIdentity] = {}
    for uid in set(user_ids):
        if not uid:
            continue
        result[uid] = _fetch_one(db, uid)
    return result


def fetch_user_identity(db: Any, user_id: str) -> UserIdentity:
    """Single-user variant of `fetch_user_identities`.

    Convenience wrapper for callers that already know they only need
    one identity. Returns a `UserIdentity` with empty fields if lookup
    fails or `user_id` is falsy — never raises.
    """
    if not user_id:
        return UserIdentity(user_id=user_id or "")
    return _fetch_one(db, user_id)


def _fetch_one(db: Any, user_id: str) -> UserIdentity:
    """Single get_user_by_id call with error → empty-shape fallback.

    Internal — public callers use `fetch_user_identities` (batch) or
    `fetch_user_identity` (singular).
    """
    try:
        resp = db.auth.admin.get_user_by_id(user_id)
    except Exception as exc:  # noqa: BLE001 — admin SDK may raise on stale IDs
        logger.warning(
            "fetch_user_identities: get_user_by_id failed for user_id=%s (%s); "
            "returning empty UserIdentity",
            user_id, exc,
        )
        return UserIdentity(user_id=user_id)

    user = getattr(resp, "user", None)
    if user is None:
        return UserIdentity(user_id=user_id)

    email = getattr(user, "email", None)
    email = email if isinstance(email, str) else ""

    metadata = getattr(user, "user_metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}

    nome = metadata.get("nome") or metadata.get("full_name") or ""
    if not isinstance(nome, str):
        nome = ""

    foto_url = metadata.get("foto_url") or metadata.get("avatar_url")
    if foto_url is not None and not isinstance(foto_url, str):
        foto_url = None

    return UserIdentity(
        user_id=user_id,
        nome=nome,
        email=email,
        foto_url=foto_url,
    )

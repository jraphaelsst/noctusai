"""The ONE effective-org resolver every trusted auth path routes through.

Round 2 (2026-10-06). "Which org is this request for?" used to be answered
four separate ways (``make_get_current_user_org``, ``ProductDependencies
.get_org_id``, the trusted legacy bridge, ``resolve_org_membership``), each a
raw read of ``public.noctus_users``. With act-as-org a fifth answer exists — a
SUPERADMIN with a LIVE ``public.act_as_sessions`` row acts as the session's
target org — so the answer is now computed here, once, and every path calls it.

Trust model (unchanged, never weakened): everything comes from the trusted
``public.noctus_users`` row (+ ``act_as_sessions``, service-role only);
``user_metadata`` is never consulted. The superadmin flag is
``noctus_users.role == 'admin'`` — the platform owner, a different concept from
the product-side ``platform_admin`` (which means org owner/admin).

Acting ⇒ ``org_id`` = the target org and ``org_role`` = ``"owner"`` (full read +
write inside the acted-as org). ``home_org_id`` always carries the caller's own
org so the UI can show "you are acting as X (home: Y)".

KB § PATTERNS/backend/tenancy-license-and-act-as.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

#: ``noctus_users.role`` of the platform owner. Read ONLY from the trusted row.
SUPERADMIN_ROLE = "admin"

#: The org role an acting superadmin has inside the target org.
ACTING_ORG_ROLE = "owner"


@dataclass(frozen=True)
class EffectiveOrg:
    org_id: Optional[str]
    org_role: Optional[str]
    home_org_id: Optional[str]
    acting_session_id: Optional[str] = None

    @property
    def acting(self) -> bool:
        return self.acting_session_id is not None


def _tbl(client: Any, name: str):
    """``client.table(name)``; ``from_`` for clients that only expose that alias
    (both exist on a real Supabase client — the seed's two historical call styles)."""
    fn = getattr(client, "table", None) or client.from_
    return fn(name)


def live_act_as_session(core_client: Any, user_id: Any) -> Optional[dict]:
    """The LIVE ``act_as_sessions`` row (``ended_at IS NULL``) for a superadmin,
    or ``None``. Raises on a DB error — callers fail closed."""
    result = (
        _tbl(core_client, "act_as_sessions")
        .select("id, target_org_id, entry_product_slug, started_at")
        .eq("superadmin_id", str(user_id))
        .is_("ended_at", "null")
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def resolve_effective_org(core_client: Any, user_id: Any) -> Optional[EffectiveOrg]:
    """The caller's effective org, or ``None`` when no ``noctus_users`` row.

    ``core_client`` MUST be the ``public``-schema service-role client. Raises on
    a DB / transport error (callers fail closed — never a metadata fallback).
    """
    if user_id is None:
        return None
    result = (
        _tbl(core_client, "noctus_users")
        .select("org_id, org_role, role")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    row = rows[0]
    home_org = row.get("org_id")
    if row.get("role") == SUPERADMIN_ROLE:
        session = live_act_as_session(core_client, user_id)
        if session and session.get("target_org_id"):
            return EffectiveOrg(
                org_id=session["target_org_id"],
                org_role=ACTING_ORG_ROLE,
                home_org_id=home_org,
                acting_session_id=session["id"],
            )
    return EffectiveOrg(
        org_id=home_org,
        org_role=row.get("org_role"),
        home_org_id=home_org,
    )


def resolve_effective_org_via(
    get_core_client_fn: Callable[[], Any], user_id: Any
) -> Optional[EffectiveOrg]:
    """:func:`resolve_effective_org` taking the client accessor the seed factories hold."""
    return resolve_effective_org(get_core_client_fn(), user_id)


__all__ = [
    "ACTING_ORG_ROLE",
    "SUPERADMIN_ROLE",
    "EffectiveOrg",
    "live_act_as_session",
    "resolve_effective_org",
    "resolve_effective_org_via",
]

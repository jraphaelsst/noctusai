"""The ONE effective-org resolver every trusted auth path routes through.

"Which org is this request for?" used to be answered four separate ways
(``make_get_current_user_org``, ``ProductDependencies.get_org_id``, the trusted
legacy bridge, ``resolve_org_membership``), each a raw read of
``public.noctus_users``. The answer is computed here, once, and every path
calls it — so the license gate and every org-scoped read agree on the org.

Trust model (never weakened): everything comes from the trusted
``public.noctus_users`` row (``org_id`` + ``org_role``); ``user_metadata`` is
never consulted. There is NO superadmin / staff override: a caller's effective
org is always their own home org (owner decision 2026-10-07 — NoctusAI staff do
not enter customer orgs). The NoctusAI platform org reaches every product
because it holds an active license for every product by construction (core
migration 068), not because of any role check here.

KB § PATTERNS/backend/tenancy-license-gate.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EffectiveOrg:
    org_id: Optional[str]
    org_role: Optional[str]


def _tbl(client: Any, name: str):
    """``client.table(name)``; ``from_`` for clients that only expose that alias
    (both exist on a real Supabase client — the seed's two historical call styles)."""
    fn = getattr(client, "table", None) or client.from_
    return fn(name)


def resolve_effective_org(core_client: Any, user_id: Any) -> Optional[EffectiveOrg]:
    """The caller's effective (= home) org, or ``None`` when no ``noctus_users`` row.

    ``core_client`` MUST be the ``public``-schema service-role client. Raises on
    a DB / transport error (callers fail closed — never a metadata fallback).
    """
    if user_id is None:
        return None
    result = (
        _tbl(core_client, "noctus_users")
        .select("org_id, org_role")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    row = rows[0]
    return EffectiveOrg(org_id=row.get("org_id"), org_role=row.get("org_role"))


def resolve_effective_org_via(
    get_core_client_fn: Callable[[], Any], user_id: Any
) -> Optional[EffectiveOrg]:
    """:func:`resolve_effective_org` taking the client accessor the seed factories hold."""
    return resolve_effective_org(get_core_client_fn(), user_id)


__all__ = [
    "EffectiveOrg",
    "resolve_effective_org",
    "resolve_effective_org_via",
]

"""Which of a user's memberships admits them into a product -- ONE rule for SSO and the dashboard.

Multi-org (S4, owner decision 2026-10-13): a user is admitted when ANY of their ACTIVE memberships
is in an org licensed for the product, they are not BLOCKED from it there (D5), and their role in
that org may reach it (SEC-2 customers). The profile (last-active) org is tried first, then the most
recently updated memberships.

``/api/sso/token`` decides admission with this; ``/api/auth/me`` uses the same rule for each card's
``has_access``. Two definitions drifted once: the dashboard read only the profile org's licenses and
locked a product the user's other org was licensed for, while SSO would have admitted her.
"""

from __future__ import annotations

from typing import Callable, Optional

from noctusai_lib.primitives.roles import customer_may_access_product

from app.services import team_memberships


def ordered_memberships(db, user_id: str, home_org_id: Optional[str]) -> list[dict]:
    """The user's ACTIVE memberships, the profile org first, then most recently updated."""
    memberships = team_memberships.list_user_active_memberships(db, user_id)
    memberships.sort(key=lambda m: 0 if m.get("org_id") == home_org_id else 1)  # stable: keeps recency order
    return memberships


def may_reach(membership: dict, product: dict) -> bool:
    """The membership's role may reach the product at all (SEC-2: customers only where declared)."""
    return customer_may_access_product(membership.get("org_role") or "member", product)


def admitting_membership(
    memberships: list[dict],
    product: dict,
    *,
    is_licensed: Callable[[str], bool],
    is_blocked: Callable[[str], bool],
) -> Optional[dict]:
    """The first membership (in the given order) that admits ``product``, or None.

    ``is_licensed(org_id)`` / ``is_blocked(org_id)`` answer for THIS product, so the caller decides
    how to look them up (one query per org for SSO, a per-org set for the dashboard).
    """
    for m in memberships:
        org_id = m.get("org_id")
        if not org_id or not may_reach(m, product):
            continue
        if is_blocked(str(org_id)):
            continue
        if is_licensed(str(org_id)):
            return m
    return None

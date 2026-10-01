"""`TeamPolicy` — the named seam a product uses to shape the seed `team` router.

Why this exists (2026-10-01): every product mounts the same `/api/team`
router, and every product's org is, today, the ONE shared platform org
("NoctusAI"). Without a seam, each product's Equipe page lists — and lets an
admin invite into — the roster of every OTHER product sharing that org (e.g.
social-wiring's `corretor`s show up on community's Equipe page), and a product
whose staff carries a product-specific role (community's `moderador`) has no
way to invite it short of forking the router.

A product declares its policy once, in `app/main.py`::

    from noctusai_seed import TeamPolicy, create_product_app

    app = create_product_app(
        ...,
        standard_routers=["health", "team"],
        team=TeamPolicy(
            staff_roles=frozenset({"owner", "admin", "moderador", "dev"}),
            invitable_roles=frozenset({"admin", "moderador"}),
            extra_role_labels={"moderador": "Moderador"},
        ),
    )

No policy (the default) keeps the pre-seam behaviour exactly: the list shows
every non-customer member of the org and an invite may grant any `ORG_ROLES`
value. End customers (`CUSTOMER_ORG_ROLES`) are excluded from the list ALWAYS,
policy or not, and can never be declared staff or invitable.

The policy is validated at construction — an incoherent policy raises
`ValueError` at boot, never a silently-wrong roster at request time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from noctusai_lib.primitives.roles import (
    CUSTOMER_ORG_ROLES,
    ORG_ROLE_LABELS,
    ORG_ROLES,
)


def _ordered(roles) -> list[str]:
    """Platform roles in `ORG_ROLES` order first, product extras sorted after —
    a stable order for the `/api/team/policy` contract and for the FE select."""
    known = [r for r in ORG_ROLES if r in roles]
    extras = sorted(r for r in roles if r not in ORG_ROLES)
    return known + extras


@dataclass(frozen=True)
class TeamPolicy:
    """Which org roles a product treats as its staff, and which it may invite.

    Attributes:
        staff_roles: The `noctus_users.org_role` values `GET /api/team` lists.
            `None` ⇒ every non-customer member of the org (the pre-seam
            behaviour; reported by `/api/team/policy` as `ORG_ROLES`).
        invitable_roles: The roles `POST /api/team/invite` may grant. `None` ⇒
            `ORG_ROLES` (narrowed to `staff_roles` when that is declared).
            When declared it MUST be a subset of `staff_roles` (if that is
            declared too) — inviting someone the product then hides from its
            own roster is the incoherence this seam exists to remove.
        extra_role_labels: pt-BR labels for roles OUTSIDE `ORG_ROLES` (e.g.
            `{"moderador": "Moderador"}`). Every extra role named in
            `staff_roles` / `invitable_roles` MUST carry a label here — an
            unlabeled role would render as a raw slug. Extras never join
            `ORG_ROLES`; they are product-scoped.
    """

    staff_roles: Optional[frozenset[str]] = None
    invitable_roles: Optional[frozenset[str]] = None
    extra_role_labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise any iterable to a frozenset so `in` + set algebra are safe.
        if self.staff_roles is not None:
            object.__setattr__(self, "staff_roles", frozenset(self.staff_roles))
        if self.invitable_roles is not None:
            object.__setattr__(self, "invitable_roles", frozenset(self.invitable_roles))
        object.__setattr__(self, "extra_role_labels", dict(self.extra_role_labels or {}))

        for name, roles in (
            ("staff_roles", self.staff_roles),
            ("invitable_roles", self.invitable_roles),
        ):
            if roles is None:
                continue
            if not roles:
                raise ValueError(
                    f"TeamPolicy.{name} is empty — pass None for the default, "
                    "an empty set would list/invite nobody"
                )
            customers = roles & CUSTOMER_ORG_ROLES
            if customers:
                raise ValueError(
                    f"TeamPolicy.{name} names customer role(s) {sorted(customers)} — "
                    "an end customer is never staff and never invitable"
                )
            unlabeled = sorted(
                r for r in roles
                if r not in ORG_ROLES and r not in self.extra_role_labels
            )
            if unlabeled:
                raise ValueError(
                    f"TeamPolicy.{name} names role(s) {unlabeled} outside ORG_ROLES "
                    "without a label in extra_role_labels"
                )

        if self.staff_roles is not None and self.invitable_roles is not None:
            outside = sorted(self.invitable_roles - self.staff_roles)
            if outside:
                raise ValueError(
                    f"TeamPolicy.invitable_roles {outside} not in staff_roles — an "
                    "invited member would be hidden from the product's own roster"
                )

        overridden = sorted(set(self.extra_role_labels) & set(ORG_ROLES))
        if overridden:
            raise ValueError(
                f"TeamPolicy.extra_role_labels relabels platform role(s) {overridden} — "
                "platform labels live in noctusai_lib.primitives.roles.ORG_ROLE_LABELS"
            )

    # ── Resolved views (what the router enforces) ──────────────────────────

    def effective_staff_roles(self) -> list[str]:
        """Roles the roster lists, as reported by `/api/team/policy`."""
        if self.staff_roles is None:
            return list(ORG_ROLES)
        return _ordered(self.staff_roles)

    def effective_invitable_roles(self) -> list[str]:
        """Roles an invite may grant."""
        if self.invitable_roles is not None:
            return _ordered(self.invitable_roles)
        if self.staff_roles is not None:
            return [r for r in ORG_ROLES if r in self.staff_roles]
        return list(ORG_ROLES)

    def labels(self) -> dict[str, str]:
        """pt-BR label for every role this policy can surface (platform + extras)."""
        return {**ORG_ROLE_LABELS, **self.extra_role_labels}

    def label_for(self, role: Optional[str]) -> str:
        """Label for `role`; falls back to the raw slug (never raises)."""
        if role is None:
            return "sem papel"
        return self.labels().get(role, role)

    def lists(self, org_role: Optional[str]) -> bool:
        """Does `GET /api/team` include a member with `org_role`?

        Customers: never. Declared `staff_roles`: only those. Default: every
        other row — including a NULL / product-extra role, exactly as before
        the seam existed, so no product loses a member it showed yesterday.
        """
        if org_role in CUSTOMER_ORG_ROLES:
            return False
        if self.staff_roles is None:
            return True
        return org_role in self.staff_roles

    def as_contract(self) -> dict:
        """The `GET /api/team/policy` body — the FE organ's frozen contract."""
        roles = set(self.effective_staff_roles()) | set(self.effective_invitable_roles())
        labels = self.labels()
        return {
            "staff_roles": self.effective_staff_roles(),
            "invitable_roles": self.effective_invitable_roles(),
            "labels": {r: labels[r] for r in _ordered(roles)},
        }


#: The policy a product gets when it declares none.
DEFAULT_TEAM_POLICY = TeamPolicy()

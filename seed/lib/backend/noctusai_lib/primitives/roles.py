"""
Shared role constants for the NoctusAI platform.

Defines the 8-role org hierarchy used across Core and all products.
Products consume these constants in dependencies.py, routers, and SSO logic.

🔴 THIS FILE AND `seed/lib/frontend/src/roles.ts` ARE ONE SET IN TWO
LANGUAGES. A role added to one and not the other is a split brain: the API
accepts a value the UI renders as a raw slug, or the UI offers a value the API
rejects. Change both, same commit.
"""
from __future__ import annotations

# All valid org_role values (noctus_users.org_role)
# `corretor` is a real business role, not a permission tier: it carries
# EXACTLY member-level rights (it appears in none of the grant tuples below)
# and exists so an agency's brokers are identifiable as brokers on the team
# page and attachable to their listings. The alternative was a product-local
# role set in social-wiring, which is the fork this constant exists to prevent.
ORG_ROLES = ("owner", "admin", "manager", "member", "viewer", "dev", "test", "corretor")

# Roles that grant team/billing management (can invite, remove, change roles)
ADMIN_ROLES = ("owner", "admin")

# Roles that can manage team but NOT billing
MANAGE_TEAM_ROLES = ("owner", "admin", "manager")

# Roles that see "in development" pages (status_pagina.status = 'desenvolvimento')
DEV_ROLES = ("owner", "dev")

# Roles that grant product-level platform_admin via SSO
# (org owner/admin entering a product get full admin access)
PRODUCT_ADMIN_ROLES = ("owner", "admin")

# Org roles that belong to END CUSTOMERS, not to the org's staff (SEC-2,
# 2026-09-28). A customer self-registers into an org (e.g. Ninho Vazio's
# members join the platform's own "NoctusAI" org) and must NEVER inherit
# org-membership access: the whole fleet keys RLS on `public.current_org_id()`
# and the API on `make_get_current_user_org`, both of which would otherwise
# hand a customer every product's back office.
#
# 🔴 ONE DEFINITION, THREE RENDERINGS: this frozenset is the source; the SQL
# array inside `public.current_org_id()` / `public.is_customer()` is RENDERED
# from it (`noctusai_lib.domain.sql_templates.org_identity_functions_sql`)
# and `seed/lib/frontend/src/roles.ts` mirrors it. Keeper
# `check_org_identity_function_parity` fails any migration or TS copy that
# disagrees. Deliberately NOT in ORG_ROLES: those are the staff roles an
# admin may assign on the team page; a customer role is never assignable.
CUSTOMER_ORG_ROLES: frozenset[str] = frozenset({"membro"})


def is_customer_role(org_role: str | None) -> bool:
    """True when ``org_role`` belongs to an end customer (never staff).

    Callers MUST pass the trusted ``public.noctus_users.org_role`` column —
    never ``user_metadata``, which the user can rewrite themselves.
    """
    return org_role in CUSTOMER_ORG_ROLES


def customer_may_access_product(org_role: str | None, product: dict | None) -> bool:
    """May a caller with ``org_role`` enter ``product`` (a ``public.products`` row)?

    Staff: always (licensing is checked separately). A customer: ONLY when
    the product declares ``aceita_clientes = true`` — the catalog DATA says
    which products serve customers, never a slug list in code. A missing
    row / column reads as "does not serve customers" (fail closed).
    """
    if not is_customer_role(org_role):
        return True
    return bool((product or {}).get("aceita_clientes") is True)


# Portuguese labels for UI display
ORG_ROLE_LABELS = {
    "owner": "Proprietário",
    "admin": "Administrador",
    "manager": "Gerente",
    "member": "Membro",
    "viewer": "Visualizador",
    "dev": "Desenvolvedor",
    "test": "Teste",
    "corretor": "Corretor",
}


def is_dev_or_owner(org_role: str | None) -> bool:
    """Check if the user can see in-development pages."""
    return org_role in DEV_ROLES


def can_manage_team(org_role: str | None) -> bool:
    """Check if the user can invite/remove team members."""
    return org_role in MANAGE_TEAM_ROLES


def can_manage_billing(org_role: str | None) -> bool:
    """Check if the user can manage billing/subscription."""
    return org_role in ADMIN_ROLES

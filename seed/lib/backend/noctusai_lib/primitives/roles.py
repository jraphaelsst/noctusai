"""
Shared role constants for the NoctusAI platform.

Defines the 7-role org hierarchy used across Core and all products.
Products consume these constants in dependencies.py, routers, and SSO logic.
"""
from __future__ import annotations

# All valid org_role values (noctus_users.org_role)
ORG_ROLES = ("owner", "admin", "manager", "member", "viewer", "dev", "test")

# Roles that grant team/billing management (can invite, remove, change roles)
ADMIN_ROLES = ("owner", "admin")

# Roles that can manage team but NOT billing
MANAGE_TEAM_ROLES = ("owner", "admin", "manager")

# Roles that see "in development" pages (status_pagina.status = 'desenvolvimento')
DEV_ROLES = ("owner", "dev")

# Roles that grant product-level platform_admin via SSO
# (org owner/admin entering a product get full admin access)
PRODUCT_ADMIN_ROLES = ("owner", "admin")

# Portuguese labels for UI display
ORG_ROLE_LABELS = {
    "owner": "Proprietário",
    "admin": "Administrador",
    "manager": "Gerente",
    "member": "Membro",
    "viewer": "Visualizador",
    "dev": "Desenvolvedor",
    "test": "Teste",
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

"""`/api/settings/api-keys*` -- the org's managed Asaas keys, admin-only.

Thin mount of the seed `create_api_keys_router` over this product's specs. Writes
are admin-gated through the trusted `noctus_users` cascade (`get_user_role`), never
`user_metadata`. Values are never returned (masked hint + source only).
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from noctusai_lib.primitives.roles import ADMIN_ROLES
from noctusai_seed.api_keys_router import create_api_keys_router

from app.api_keys import API_KEY_SPECS, build_store
from app.commerce import CFG
from app.config import settings
from app.dependencies import get_current_user_org, get_user_role
from app.key_testers import make_asaas_key_tester


def _require_admin_gate(user: Any, context: str) -> None:
    if get_user_role(user) not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": f"Apenas administradores da organização podem gerenciar {context}.",
                "code": "admin_obrigatorio",
            },
        )


router = create_api_keys_router(
    deps=None,
    settings=settings,
    specs=API_KEY_SPECS,
    store_factory=build_store,
    get_current_user_org=get_current_user_org,
    # Org-dependent: the probe runs in the CALLER org's chosen Asaas environment.
    org_testers={CFG.asaas_api_key_name: make_asaas_key_tester()},
    require_admin=_require_admin_gate,
)

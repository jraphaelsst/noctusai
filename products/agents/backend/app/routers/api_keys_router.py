"""``/api/settings/api-keys*`` — the org's managed LLM provider keys, admin-only.

Thin mount of the seed ``create_api_keys_router`` over the agents specs
(``openai_api_key`` / ``anthropic_api_key``, ``app/credentials/org_keys.py``).
Writes are admin-gated through the trusted ``noctus_users`` role cascade
(``resolve_org_role``), never ``user_metadata``. Values are never returned
(masked hint + source only). A ``runtime='llm'`` turn resolves ONLY these
per-org keys (B1) — see ``app/credentials/org_keys.py``.

The router's platform-chain tier is bound to ``resolve_org_credential``
(this org's ``org_settings`` row only): the default ``resolve_credential``
would answer ``anthropic_api_key`` from the tier-0 override (Julia-academia's
platform key) and report an org "configured" — and ``POST .../test`` would
probe the PLATFORM key — for a key the org never set. The status screen must
tell the truth the runtime acts on (``resolve_org_llm_key``).
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from noctusai_lib.api.auth.session import resolve_org_role
from noctusai_lib.config.credentials import resolve_org_credential
from noctusai_seed.api_keys_router import create_api_keys_router

from app.config import settings
from app.credentials.api_key_testers import make_llm_key_testers
from app.credentials.org_keys import LLM_API_KEY_SPECS, build_llm_key_store
from app.dependencies import ADMIN_ROLES, get_core_client, get_current_user_org


def _require_admin_gate(user: Any, context: str) -> None:
    # The trusted `noctus_users.org_role` — never `user_metadata`. (Not
    # `get_user_role`: its cascade answers `platform_admin` for owners/admins,
    # which is not a member of `ADMIN_ROLES`.)
    if resolve_org_role(get_core_client(), getattr(user, "id", None)) not in ADMIN_ROLES:
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
    specs=LLM_API_KEY_SPECS,
    store_factory=build_llm_key_store,
    get_current_user_org=get_current_user_org,
    testers=make_llm_key_testers(),
    require_admin=_require_admin_gate,
    resolver=resolve_org_credential,
)

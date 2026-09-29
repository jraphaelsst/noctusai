"""`/api/settings/api-keys*` — org-scoped managed API keys, admin-only.

Thin mount of `noctusai_seed.api_keys_router.create_api_keys_router` over
this product's spec list (`app/services/api_keys_store.API_KEY_SPECS`,
currently just `anthropic_api_key`) + testers
(`app/services/api_keys_testers.make_testers`). No local route logic —
see `noctusai_seed.api_keys_router`'s own docstring for the exact
contract (paths, request/response shapes, status codes).

Write endpoints (`PUT`/`DELETE`) are admin-gated via `require_admin`
using the SAME trusted `public.noctus_users` cascade every other
admin-only IgIg write uses (`app.pipelines.exigir_admin_da_org`'s own
`_exigir_admin` logic) — never `user_metadata`, which any user can
rewrite. Reimplemented here (not imported) because that helper is shaped
as a FastAPI `Depends(...)` dependency reading the whole `auth` tuple,
while this router's `require_admin` seam is a plain `(user, context) ->
None` callable invoked from inside the route body.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from noctusai_lib.primitives.roles import ADMIN_ROLES
from noctusai_seed.api_keys_router import create_api_keys_router

from app.config import settings
from app.dependencies import get_current_user_org, get_user_role, resolve_platform_role
from app.services.api_keys_store import API_KEY_SPECS, build_igig_api_key_store
from app.services.api_keys_testers import make_testers


def _require_admin_gate(user: Any, context: str) -> None:
    if resolve_platform_role(user) == "platform_admin":
        return
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
    store_factory=build_igig_api_key_store,
    get_current_user_org=get_current_user_org,
    testers=make_testers(),
    require_admin=_require_admin_gate,
)

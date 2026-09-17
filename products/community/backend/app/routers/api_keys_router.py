"""`/api/settings/api-keys*` — org-scoped managed API keys, admin-only.

Thin mount of `noctusai_seed.api_keys_router.create_api_keys_router`
(lifted from `social-wiring`'s Slice A) over this product's spec list
(`app/services/api_keys_store.API_KEY_SPECS`) + testers
(`app/services/api_keys_testers.make_testers`). No local route logic —
see `noctusai_seed.api_keys_router`'s own docstring for the exact
contract (paths, request/response shapes, status codes).

Write endpoints (`PUT`/`DELETE`) are admin-gated via `require_admin`
(this product's own `admin`/`moderador` role split —
`app.dependencies.get_community_role` — same convention every other
admin-gated community route uses; NOT the generic owner/admin
`user_metadata` check `social-wiring`'s own router used, which does not
know this product's vocabulary).
"""
from __future__ import annotations

from typing import Any

from noctusai_seed.api_keys_router import create_api_keys_router

from app.config import settings
from app.dependencies import get_community_role, get_current_user_org, require_admin
from app.services.api_keys_store import API_KEY_SPECS, build_community_api_key_store
from app.services.api_keys_testers import make_testers


def _require_admin_gate(user: Any, context: str) -> None:
    role = get_community_role(user)
    require_admin(role, action=f"gerenciar {context}")


router = create_api_keys_router(
    deps=None,
    settings=settings,
    specs=API_KEY_SPECS,
    store_factory=build_community_api_key_store,
    get_current_user_org=get_current_user_org,
    testers=make_testers(),
    require_admin=_require_admin_gate,
)

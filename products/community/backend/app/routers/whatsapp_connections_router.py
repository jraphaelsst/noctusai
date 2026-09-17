"""`/api/whatsapp/connections*` — multi-session, org-scoped WAHA
connection management, admin-only.

Mounts `noctusai_seed.whatsapp_connections_router.create_whatsapp_
connections_router` (lifted from `social-wiring`'s Slice A) over this
product's `community.whatsapp_connections` table (migration 011) +
its own WAHA server config (`community_waha_*`, `app/config.py`).

`base_url` / `session_name` are derived server-side from
`settings.community_waha_base_url` / `community_waha_session` — a
connection created here talks to COMMUNITY's own WAHA instance (D4:
"a separate container from whatever other product's WAHA session
exists"), never the shared `default` session `social-wiring` already
owns.

**Admin-gated by construction, not by the seed factory** — unlike
`create_api_keys_router`, `create_whatsapp_connections_router` has no
`require_admin` parameter (every route in it is a CRUD/live-ops
surface, none has a per-route "read is open, write is gated" split the
way api-keys does). The gate is applied at `include_router(...,
dependencies=[...])` — same trick `whatsapp_webhook_router.py` uses to
rate-limit a mounted seed router without forking it.

`NOC-REMEDIATE[community-waha-pairing]`: this mounts the CONNECTION
MANAGEMENT mechanism only — no number is paired in this slice (user
decision 2026-09-17). See `products/community/README.md`
§ "WhatsApp — não conectado por enquanto".
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_community_role,
    get_current_user_org,
    require_admin,
)


def _store_factory():
    return build_whatsapp_connection_store(
        get_admin_client(),
        encryption_key=settings.encryption_key,
        schema="community",
    )


def _resolve_webhook_base_url() -> str:
    return resolve_product_url("community")


def _require_admin_dep(auth: tuple = Depends(get_current_user_org)) -> None:
    user, _token, _org = auth
    role = get_community_role(user)
    require_admin(role, action="gerenciar conexões de WhatsApp")


def _resolve_user_id(user) -> UUID:
    # Same test-fixture-compatible coercion `coerce_org_uuid` applies to
    # `org_id` (the seed router's own default assumes a real UUID auth
    # id — `UUID(str(raw))` with no fallback — which 500s against this
    # product's non-UUID `MockUser` test fixtures).
    return coerce_org_uuid(getattr(user, "id", "") or "")


router = APIRouter()
router.include_router(
    create_whatsapp_connections_router(
        deps=None,
        settings=settings,
        store_factory=_store_factory,
        get_current_user_org=get_current_user_org,
        waha_base_url=settings.community_waha_base_url or None,
        resolve_webhook_base_url=_resolve_webhook_base_url,
        waha_session=settings.community_waha_session,
        resolve_org_id=coerce_org_uuid,
        resolve_user_id=_resolve_user_id,
    ),
    dependencies=[Depends(_require_admin_dep)],
)

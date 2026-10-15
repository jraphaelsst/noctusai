"""`/api/whatsapp/connections*` — org-scoped WAHA connection management, admin-only.

Mounts `noctusai_seed.whatsapp_connections_router.create_whatsapp_connections_router`
over `orbity.whatsapp_connections` (migration 018) — same wiring as community.
A connection created here is what the automation engine SENDS through
(`app/services/whatsapp_sender.py`) and what routes inbound replies back to the
right org (`/api/whatsapp/webhook/{token}`, `whatsapp_webhook_router.py`).

`base_url` / `session_name` / `webhook_url` are derived server-side from
`settings.waha_base_url` / `waha_session` and the product URL; the user only
supplies a label + the WAHA API key (encrypted at rest with `ENCRYPTION_KEY`).

Admin-gated by construction at `include_router(..., dependencies=[...])` (the
seed factory has no `require_admin` parameter), role read from the trusted
`noctus_users` row — never `user_metadata`.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    require_org_admin_for_whatsapp,
)


def _store_factory():
    return build_whatsapp_connection_store(
        get_admin_client(),
        encryption_key=settings.encryption_key,
        schema="orbity",
    )


def _resolve_webhook_base_url() -> str:
    return resolve_product_url("orbity")


def _require_admin_dep(request: Request, auth: tuple = Depends(get_current_user_org)) -> None:
    require_org_admin_for_whatsapp(request, auth)


def _resolve_user_id(user) -> UUID:
    # Same test-fixture-compatible coercion `coerce_org_uuid` applies to org ids.
    return coerce_org_uuid(getattr(user, "id", "") or "")


router = APIRouter()
router.include_router(
    create_whatsapp_connections_router(
        deps=None,
        settings=settings,
        store_factory=_store_factory,
        get_current_user_org=get_current_user_org,
        waha_base_url=settings.waha_base_url or None,
        resolve_webhook_base_url=_resolve_webhook_base_url,
        waha_session=settings.waha_session,
        resolve_org_id=coerce_org_uuid,
        resolve_user_id=_resolve_user_id,
    ),
    dependencies=[Depends(_require_admin_dep)],
)

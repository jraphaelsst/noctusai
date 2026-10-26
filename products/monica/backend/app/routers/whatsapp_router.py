"""WhatsApp for Monica: the QR connection lines (admin) and the conversations inbox (any org member).

Mounts the SEED organs, no product logic:

* `create_whatsapp_connections_router` -- `/api/whatsapp/connections*` over `monica.whatsapp_connections`
  (migration 015), ADMIN-gated (`make_organ_auth(...).admin`: the role is resolved for the SELECTED org).
  `base_url` / `session_name` are derived server-side from `MONICA_WAHA_BASE_URL` / `MONICA_WAHA_SESSION` -- Monica's
  own WAHA instance, never the shared one. Unset => create answers 503 "WAHA server not configured".
* `create_whatsapp_inbox_router` -- chats / messages / send / read / backfill / SSE + the PUBLIC webhook, over
  `monica.whatsapp_chats|messages`. `on_new_chat` turns each new inbound number into a lead, `on_message` keeps the
  card preview fresh (`app/services/whatsapp_leads.py`).

Per-app switch / borrowed session / purge: `PUT .../{id}/enabled`, `session_role='borrower'` (migration 017) and
`POST .../{id}/purge` (leads seam `on_purge`) come with the seed connections router -- see
`KB § INTEGRATIONS/whatsapp.md § Per-app switch, borrowed sessions and purge`.

The webhook prefix is the same default value in both routers (the connections router mints
`{product_url}/api/whatsapp/webhook/{token}`; the inbox router receives it).
"""
from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter

from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_lib.integrations.whatsapp.inbox import build_inbox_realtime, build_whatsapp_chat_store
from noctusai_lib.integrations.whatsapp.lid_auth import InMemoryLidPhoneCache
from noctusai_seed.organ_auth import make_organ_auth
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router
from noctusai_seed.whatsapp_inbox_router import create_whatsapp_inbox_router

from app.config import settings
from app.dependencies import _db, coerce_org_uuid, get_admin_client, get_current_user_org
from app.services.whatsapp_leads import on_message, on_new_chat, on_purge

SCHEMA = "monica"

_organ_auth = make_organ_auth(get_current_user_org, lambda: _db.get_core_client(), context="Conexões de WhatsApp")


def _connection_store():
    return build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key, schema=SCHEMA)


def _chat_store():
    return build_whatsapp_chat_store(get_admin_client(), schema=SCHEMA)


def _webhook_base_url() -> str:
    return resolve_product_url("monica")


def _resolve_user_id(user) -> UUID:
    return coerce_org_uuid(getattr(user, "id", "") or "")


@lru_cache(maxsize=1)
def build_realtime():
    """Redis when REDIS_URL is set. The in-process bus only where it is a declared single-worker choice
    (MONICA_INBOX_REALTIME_IN_PROCESS) or outside a deploy (dev / tests); a deploy with neither refuses to boot
    rather than leave the open conversation silently stale (`InboxRealtimeNotConfigured`)."""
    return build_inbox_realtime(
        redis_url=settings.redis_url or None,
        allow_in_process=settings.monica_inbox_realtime_in_process or not is_deploy_context(),
    )


router = APIRouter()
router.include_router(
    create_whatsapp_connections_router(
        deps=None,
        settings=settings,
        store_factory=_connection_store,
        get_current_user_org=_organ_auth.admin,
        waha_base_url=settings.monica_waha_base_url or None,
        resolve_webhook_base_url=_webhook_base_url,
        waha_session=settings.monica_waha_session,
        resolve_org_id=coerce_org_uuid,
        resolve_user_id=_resolve_user_id,
        chat_store_factory=_chat_store,
        on_purge=on_purge,
        audit_product_slug="monica",
    )
)
router.include_router(
    create_whatsapp_inbox_router(
        chat_store_factory=_chat_store,
        connection_store_factory=_connection_store,
        get_current_user_org=get_current_user_org,
        on_new_chat=on_new_chat,
        on_message=on_message,
        realtime=build_realtime(),
        lid_cache=InMemoryLidPhoneCache(),
        webhook_hmac_secret=settings.monica_waha_webhook_hmac_secret or None,
        resolve_org_id=coerce_org_uuid,
    )
)

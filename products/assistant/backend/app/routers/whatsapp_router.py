"""WhatsApp for the Assistant: the QR connection (admin) + the inbound webhook. NOTHING else.

* `create_whatsapp_connections_router` -- `/api/whatsapp/connections*` over `assistant.whatsapp_connections`
  (migration 015), ADMIN-gated. `base_url` / `session_name` come from `ASSISTANT_WAHA_BASE_URL` / `_SESSION`.
* `create_whatsapp_inbox_router(webhook_only=True, require_webhook_hmac=True)` -- ONLY the public webhook: no chats,
  no messages, no mark-read, no send, no backfill, no SSE (plan item 1b). The HMAC is mandatory: no secret => every
  webhook is a 401 and a deploy refuses to boot (`WebhookHmacRequired`).

Input contract (plan item 4), applied BEFORE anything is stored: `inbound_one_to_one_only` (no `from_me`, no
API-sourced, no groups/status/broadcast, minus the exclusion list), then the intake store dedups on the WAHA message
id, enforces forward-only from `paired_at` and keeps text only (`assistant.append_intake`).

Live reply (owner decision 2026-11-12, OFF by default -- `ASSISTANT_REPLY_ENABLED`): each stored inbound text is also
handed, through the `on_message` seam, to `app.live` (agent turn in `agents` -> bubbles back on the same line). The
shadow data (intake + classifier) is untouched. The line policy must be `send: enabled` for the reply path; the only
code that sends is `app.live.resposta`, behind its send-seam allow-list guard.
"""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_lib.integrations.whatsapp.inbox.predicates import inbound_one_to_one_only
from noctusai_lib.integrations.whatsapp.lid_auth import InMemoryLidPhoneCache
from noctusai_seed.organ_auth import make_organ_auth
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router
from noctusai_seed.whatsapp_inbox_router import create_whatsapp_inbox_router

from app.config import settings
from app.live.wiring import build_on_message, build_replier
from app.dependencies import _db, coerce_org_uuid, get_admin_client, get_current_user_org
from app.services.intake import IntakeChatStore
from app.services.pairing import apply_session_status

SCHEMA = "assistant"

_organ_auth = make_organ_auth(get_current_user_org, lambda: _db.get_core_client(), context="Conexões de WhatsApp")


def _connection_store():
    return build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key, schema=SCHEMA)


def _intake_store() -> IntakeChatStore:
    return IntakeChatStore(get_admin_client, lambda: settings.assistant_identity_hmac_key)


def webhook_base_url(product_url: Callable[[], str]) -> str:
    """Where WAHA posts inbound events: DIRECT to the product (the personal live line has no edge and no webhook relay)."""
    return product_url().rstrip("/")


def _webhook_base_url() -> str:
    return webhook_base_url(lambda: resolve_product_url("assistant"))


def _resolve_user_id(user) -> UUID:
    return coerce_org_uuid(getattr(user, "id", "") or "")


def _excluded() -> list[str]:
    return [x.strip() for x in settings.assistant_excluded_numbers.split(",") if x.strip()]


def build_should_store():
    """The pre-store input contract, built from the live settings (exclusion list included)."""
    return inbound_one_to_one_only(_excluded())


def _replier():
    return build_replier(_connection_store, get_admin_client)


async def _on_session_status(record, status: str) -> None:
    from starlette.concurrency import run_in_threadpool

    await run_in_threadpool(apply_session_status, get_admin_client, record, status)


router = APIRouter()
router.include_router(
    create_whatsapp_connections_router(
        deps=None,
        settings=settings,
        store_factory=_connection_store,
        get_current_user_org=_organ_auth.admin,
        waha_base_url=settings.assistant_waha_base_url or None,
        resolve_webhook_base_url=_webhook_base_url,
        waha_session=settings.assistant_waha_session,
        resolve_org_id=coerce_org_uuid,
        resolve_user_id=_resolve_user_id,
        audit_product_slug="assistant",
    )
)
router.include_router(
    create_whatsapp_inbox_router(
        chat_store_factory=_intake_store,
        connection_store_factory=_connection_store,
        get_current_user_org=get_current_user_org,
        lid_cache=InMemoryLidPhoneCache(),
        webhook_hmac_secret=settings.assistant_waha_webhook_hmac_secret or None,
        resolve_org_id=coerce_org_uuid,
        should_store=build_should_store(),
        on_message=build_on_message(_replier),
        webhook_only=True,
        require_webhook_hmac=True,
        on_session_status=_on_session_status,
    )
)

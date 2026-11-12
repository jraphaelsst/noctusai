"""WhatsApp for the Assistant: the QR connection, the owner's conversations (inbox) and the inbound webhook.

* `create_whatsapp_connections_router` -- `/api/whatsapp/connections*` over `assistant.whatsapp_connections`
  (migration 015), ADMIN-gated. `base_url` / `session_name` come from `ASSISTANT_WAHA_BASE_URL` / `_SESSION`.
* `create_whatsapp_inbox_router(require_webhook_hmac=True)` -- since 2026-11-12 (owner: "see and manage my conversations
  via the UI") the FULL inbox: chats / messages / send / mark-read / backfill / SSE, every one ADMIN-gated (tier `org`,
  the owner's personal line: `_organ_auth.admin`, 401 without a session, 403 for a member), plus the public webhook.
  Mark-read stays LOCAL (`mirror_read_to_whatsapp` is off): the Assistant never shows blue ticks or a presence on its own.
  The HMAC on the webhook is mandatory: no secret => every webhook is a 401 and a deploy refuses to boot
  (`WebhookHmacRequired`).
* The store behind the webhook is `MirrorChatStore` (`app/services/inbox_mirror.py`): the seed inbox tables (migration
  022, both directions, 1:1) AND the intake queue (inbound only, the classifier's input contract unchanged).

Input contracts, applied BEFORE anything is stored: the inbox keeps 1:1 conversations in both directions
(`conversation_should_store`: no groups/status/broadcast, minus the exclusion list); the intake queue additionally
requires inbound-only (`inbound_one_to_one_only`: no `from_me`, no API-sourced), then dedups on the WAHA message id,
enforces forward-only from `paired_at` and keeps text only (`assistant.append_intake`).

Live reply (owner decision 2026-11-12, OFF by default -- `ASSISTANT_REPLY_ENABLED`): each stored inbound text is also
handed, through the `on_message` seam, to `app.live` (agent turn in `agents` -> bubbles back on the same line). The
shadow data (intake + classifier) is untouched. The line policy must be `send: enabled` for the reply path; the only
code that sends is `app.live.resposta`, behind its send-seam allow-list guard.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable
from uuid import UUID

from fastapi import APIRouter

from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_lib.integrations.whatsapp.inbox import build_inbox_realtime, build_whatsapp_chat_store
from noctusai_lib.integrations.whatsapp.inbox.predicates import inbound_one_to_one_only
from noctusai_lib.integrations.whatsapp.lid_auth import InMemoryLidPhoneCache
from noctusai_seed.organ_auth import make_organ_auth
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router
from noctusai_seed.whatsapp_inbox_router import create_whatsapp_inbox_router

from app.config import settings
from app.live.wiring import build_on_message, build_replier
from app.dependencies import _db, coerce_org_uuid, get_admin_client, get_current_user_org
from app.services.humano_para_agente import build_human_forwarder
from app.services.inbox_mirror import build_mirror_store, conversation_should_store, guarded_on_message
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


def build_conversation_should_store():
    """The inbox's pre-store contract (1:1, both directions, minus the exclusion list)."""
    return conversation_should_store(_excluded())


def _mirror_store():
    """The ONE chat store behind the webhook, the reads and the sends: seed inbox tables + the intake feed."""
    return build_mirror_store(
        build_whatsapp_chat_store(get_admin_client(), schema=SCHEMA), _intake_store(), _excluded()
    )


@lru_cache(maxsize=1)
def build_realtime():
    """Redis when REDIS_URL is set. The in-process bus only where it is a declared single-worker choice
    (ASSISTANT_INBOX_REALTIME_IN_PROCESS) or outside a deploy (dev / tests); a deploy with neither refuses to boot
    rather than leave the open conversation silently stale (`InboxRealtimeNotConfigured`)."""
    return build_inbox_realtime(
        redis_url=settings.redis_url or None,
        allow_in_process=settings.assistant_inbox_realtime_in_process or not is_deploy_context(),
    )


def _owner_user_id(org_id, connection_id) -> str | None:
    rec = _connection_store().get_connection(connection_id=connection_id, org_id=org_id, decrypt=False)
    return str(rec.user_id) if rec is not None else None


_agents_holder: list = []


def _agents():
    """ONE agents client per process (built lazily; a missing token/url is a declared refusal, never a Fake)."""
    if not _agents_holder:
        from noctusai_lib.integrations.agents_channel import make_agents_client

        _agents_holder.append(make_agents_client(
            token=settings.assistant_agents_token, base_url=settings.assistant_agents_base_url, allow_fake=False,
        ))
    return _agents_holder[0]


def _human_forwarder():
    return build_human_forwarder(
        agents_factory=_agents, owner_user_id=_owner_user_id,
        identity_key=lambda: settings.assistant_identity_hmac_key, enabled=lambda: settings.assistant_reply_enabled,
    )


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
        chat_store_factory=_mirror_store,
        connection_store_factory=_connection_store,
        # the owner's personal line: admin of the selected org only (the webhook below is public, HMAC + token gated)
        get_current_user_org=_organ_auth.admin,
        realtime=build_realtime(),
        lid_cache=InMemoryLidPhoneCache(),
        webhook_hmac_secret=settings.assistant_waha_webhook_hmac_secret or None,
        resolve_org_id=coerce_org_uuid,
        should_store=build_conversation_should_store(),
        on_message=guarded_on_message(build_on_message(_replier), build_should_store(), _human_forwarder()),
        require_webhook_hmac=True,
        on_session_status=_on_session_status,
    )
)

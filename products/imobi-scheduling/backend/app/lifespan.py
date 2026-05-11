"""FastAPI lifespan hooks for Imobi Scheduling.

Two async callables consumed by `create_product_app(..., lifespan_startup=...,
lifespan_shutdown=...)`. Per the seed contract (see `seed/framework/backend/
noctusai_seed/app.py:55-86`) both run inside FastAPI's lifespan context.

**Startup contract** — `on_startup()`:

  1. Resolve the Supabase admin client via `app.dependencies.get_admin_client()`
     (late-binding wrapper around `app.database._db.get_admin_client()`).
  2. If admin client is absent (no service-role key in early-dev),
     log loud + skip conversation module wiring — the WhatsApp router
     drops inbounds with a loud WARN in that mode anyway.
  3. Otherwise: call `configure_conversation_module(...)` to wire the
     buffer / dispatcher / worker / audit-writer, then `start_worker()`
     to schedule the polling worker as an asyncio background task
     (via `noctusai_lib.primitives.tasks.schedule_coro` — see Phase 6
     §6 brief).

**Shutdown contract** — `on_shutdown()`:

  1. Signal `worker.should_stop = True`.
  2. Await the worker task with a small timeout (5s default).
  3. On timeout, cancel the task — `time.sleep` in the worker's poll
     loop can hold the to_thread executor for up to `poll_seconds`.

**Single-agency v1.** Per PROJECT.md Phase 0 Q4, the org_id is fixed at
deployment. We re-use `SINGLE_AGENCY_ORG_KEY` from
`app.routers.whatsapp_router` for consistency — both the inbound auth
boundary and the audit-row org_id MUST match.
"""
from __future__ import annotations

import logging

from app.dependencies import coerce_org_uuid, get_admin_client
from app.routers.whatsapp_router import SINGLE_AGENCY_ORG_KEY
from app.services.conversation import (
    configure_conversation_module,
    start_worker,
    stop_worker,
)

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Wire the conversation module + start the worker.

    Idempotent — re-entry (e.g. test fixtures driving lifespan twice)
    logs at debug and short-circuits.
    """
    admin = get_admin_client()
    if admin is None:
        logger.warning(
            "Conversation module NOT configured at startup: no admin client. "
            "Set SUPABASE_SERVICE_ROLE_KEY to enable conversation persistence. "
            "Worker not started; WhatsApp inbounds will drop with WARN."
        )
        return

    org_uuid = coerce_org_uuid(SINGLE_AGENCY_ORG_KEY)
    configure_conversation_module(admin_client=admin, org_id=org_uuid)
    start_worker()
    logger.info("Imobi Scheduling lifespan startup: conversation module ready.")


async def on_shutdown() -> None:
    """Stop the worker. Safe to call when startup short-circuited."""
    await stop_worker()
    logger.info("Imobi Scheduling lifespan shutdown complete.")


__all__ = ["on_startup", "on_shutdown"]

"""FastAPI lifespan hooks for Social Wiring.

Wires the seed conversation buffer + worker at startup, signals it to stop
+ awaits the task at shutdown. The hooks are consumed by
``create_product_app(..., lifespan_startup=on_startup, lifespan_shutdown=on_shutdown)``
in ``app/main.py``.

**Startup contract** — ``on_startup()``:

  1. Resolve the Supabase admin client via ``app.dependencies.get_admin_client()``.
  2. If absent (no service-role key in early-dev), log loud + skip wiring
     — the WhatsApp router will fall back to the inline chatbot path,
     which still works (just without multi-message accumulation).
  3. Resolve the default org id (first org with YouTube credentials,
     else ``settings.local_dev_org_id``).
  4. Call ``configure_conversation_module(...)`` to build the seed-backed
     ``ConversationBufferService`` + ``ConversationWorker``.
  5. Call ``start_worker()`` to schedule the polling worker as a background
     asyncio task (wrapped via ``asyncio.to_thread`` so its synchronous
     poll-loop doesn't block the event loop).

**Shutdown contract** — ``on_shutdown()``:

  1. Signal ``worker.should_stop = True``.
  2. Await the worker task with a 5s timeout.
  3. On timeout, cancel the task — the worker's ``time.sleep(poll_seconds)``
     can hold the thread for up to 2s after ``should_stop`` flips.

**Why this lives at the product layer.** The seed ships
``ConversationBufferService`` + ``ConversationWorker`` but NO universal
lifespan glue (the wiring is consumer-specific — different products need
different processors, audit writers, tool registries). This file is the
social-wiring-specific wiring, mirroring the shape that
``imobi-scheduling/app/lifespan.py`` uses.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.config import settings
from app.dependencies import get_admin_client
from app.modules.email_marketing.scheduler import (
    start_scheduler,
    stop_scheduler,
)
from app.services.conversation_module import (
    configure_conversation_module,
    start_worker,
    stop_worker,
)

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Wire the conversation module + start the worker.

    Idempotent — ``configure_conversation_module`` short-circuits if
    already configured (e.g. test fixtures driving lifespan twice).
    """
    admin = get_admin_client()
    if admin is None:
        logger.warning(
            "ConversationModule NOT configured at startup: no admin client. "
            "WhatsApp inbounds will fall back to the inline chatbot path "
            "(no multi-message accumulation). Set SUPABASE_SERVICE_ROLE_KEY "
            "or DATABASE_BACKEND=sqlite to enable the seed buffer worker."
        )
        return

    org_id = _resolve_default_org(admin) or UUID(settings.local_dev_org_id)

    configure_conversation_module(
        admin_supabase=admin,
        org_id=org_id,
    )
    start_worker()

    # Drive-download-cache orphan sweep. After a deploy / container
    # restart, /tmp/uploads may be wiped while Redis kept stale cache
    # entries. Sweep them away once at startup so cache.get() doesn't
    # waste a roundtrip on stale entries — also surfaces a friendly
    # eviction count in logs for visibility.
    try:
        import redis as _redis
        from app.modules.youtube.services.download_cache import DownloadCache

        cache_redis = _redis.from_url(settings.redis_url, decode_responses=True)
        cache = DownloadCache(
            cache_redis, ttl_hours=settings.download_cache_ttl_hours
        )
        evicted = cache.cleanup_orphans()
        if evicted:
            logger.info("DownloadCache: swept %d stale entries on startup.", evicted)
    except Exception:
        logger.exception(
            "DownloadCache orphan sweep skipped (Redis unreachable?)."
        )

    # email_marketing (W2.2) scheduler — send-loop / scheduled-campaign /
    # automation jobs were registered on the seed scheduler at module
    # registration time (``email_marketing.register()`` → ``scheduler.
    # configure()``). Start the seed APScheduler here. ``start_scheduler``
    # is idempotent (no-op if already running). N=1 lifespan-seam need
    # (only W2.2) → direct splice, NOT a ModuleRegistration lifespan seam
    # (HOLDING.md W2.3 decision).
    start_scheduler()

    logger.info(
        "Social Wiring lifespan startup: ConversationModule ready (org_id=%s).",
        org_id,
    )


async def on_shutdown() -> None:
    """Stop the worker. Safe to call when startup short-circuited."""
    await stop_worker()
    stop_scheduler()
    logger.info("Social Wiring lifespan shutdown complete.")


def _resolve_default_org(admin_supabase) -> UUID | None:
    """Find the first org that has YouTube credentials connected.

    Mirrors the resolution in ``app/routers/whatsapp_router.py`` — keep
    them aligned so the lifespan-resolved org matches the per-request
    intake-service org. Returns ``None`` on any error so the caller can
    fall through to ``settings.local_dev_org_id``.
    """
    try:
        response = (
            admin_supabase
            .schema("social_wiring")
            .table("credentials")
            .select("org_id")
            .eq("provider", "youtube")
            .limit(1)
            .execute()
        )
        if response.data:
            return UUID(response.data[0]["org_id"])
    except Exception:
        logger.exception("Lifespan org-id resolution failed; falling back to local_dev_org_id.")
    return None


__all__ = ["on_shutdown", "on_startup"]

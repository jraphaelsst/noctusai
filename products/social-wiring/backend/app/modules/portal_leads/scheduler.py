"""Scheduled job for the `portal_leads` module — the OLX inbox drain.

One job, every 15 minutes. It exists because the receiver answers 200 and
processes afterwards: a lead whose ingest failed (unresolvable org, a
mapping error, a DB blip) sits in `olx_lead_events` as `error` or
`unresolved` and nothing else would ever pick it up.

Fifteen minutes rather than daily because the drain is cheap — one
indexed DB read of a partial index that is almost always empty — and
because the cost of waiting is a real customer not being called back.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


def _drain_sync(
    *,
    admin_client_factory: Optional[Callable[[], Any]] = None,
    service_factory: Optional[Callable[..., Any]] = None,
) -> None:
    """Sync body of the drain. Collaborators are DI seams (Class-A,
    `KB § PATTERNS/backend/di-test-seam.md`) so a test drives the real job
    without a scheduler or a database."""
    admin = (admin_client_factory or get_admin_client)()
    if admin is None:
        logger.warning("olx drain: no admin client — skipping run")
        return

    if service_factory is None:
        from app.modules.portal_leads.services.olx_webhook_service import (
            OlxWebhookService,
        )

        service_factory = OlxWebhookService

    client = admin.schema(_SCHEMA)
    default_org = None
    try:
        from app.dependencies import coerce_org_uuid
        from app.modules.portal_leads.deps import get_olx_config

        configured = get_olx_config().leads_org_id
        if configured:
            default_org = coerce_org_uuid(configured)
    except Exception as exc:  # noqa: BLE001 — config gap must not kill the drain
        # Without a default org the drain still retries every row; those
        # that need the fallback simply stay `unresolved`, which is the
        # honest outcome rather than a guessed tenant.
        logger.warning("olx drain: could not resolve the default org (%s)", exc)

    svc = service_factory(client=client, default_org_id=default_org)
    try:
        result = svc.drain_pending()
        if result.get("examined"):
            logger.info(
                "olx drain: examined=%d processed=%d pending=%d exhausted=%d",
                result.get("examined", 0), result.get("processed", 0),
                result.get("still_pending", 0), result.get("exhausted", 0),
            )
    except Exception as exc:  # noqa: BLE001 — one bad run must not kill the schedule
        logger.warning("olx drain: run failed: %s", exc, exc_info=True)


async def olx_leads_retry_job() -> None:
    """Async wrapper — same thread-offload convention as `meta_ads`."""
    try:
        await asyncio.to_thread(_drain_sync)
    except Exception as exc:  # noqa: BLE001
        logger.error("olx drain: job wrapper error: %s", exc, exc_info=True)


async def portal_lead_forward_drain_job() -> None:
    """Deliver due entries from the downstream-forward outbox.

    Separate from the inbox drain, and on a tighter schedule, because the
    two protect different things. The inbox retries OUR ingest, where the
    lead is already safely stored. This one is the only path by which a
    downstream CRM — one that was being fed directly by Grupo OLX until
    we took over the Canal Pro URL — ever sees the lead at all. The
    vendor will not resend it.

    Five minutes is the compromise: fast enough that a downstream blip
    costs minutes rather than a quarter-hour of a broker's response time,
    cheap enough to ignore because the query is a partial index whose
    steady state is empty.
    """
    try:
        await _drain_forwards_async()
    except Exception as exc:  # noqa: BLE001 — one bad run must not kill the schedule
        logger.error("portal-forward drain: job wrapper error: %s", exc, exc_info=True)


async def _drain_forwards_async(
    *,
    admin_client_factory: Optional[Callable[[], Any]] = None,
    drain_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Async body of the forward drain. Collaborators are DI seams so a
    test drives the real job without a scheduler or a database."""
    admin = (admin_client_factory or get_admin_client)()
    if admin is None:
        logger.warning("portal-forward drain: no admin client — skipping run")
        return

    if drain_fn is None:
        from app.modules.portal_leads.services.forward_service import drain_forwards

        drain_fn = drain_forwards

    secret = None
    try:
        from app.modules.portal_leads.deps import get_olx_config

        secret = get_olx_config().webhook_secret
    except Exception as exc:  # noqa: BLE001 — config gap must not kill the drain
        # Without the secret, `passthrough` targets fail loudly per row
        # and land as `failed` with a readable reason — which is the
        # honest outcome, and better than sending unauthenticated.
        logger.warning("portal-forward drain: could not resolve the OLX config (%s)", exc)

    await drain_fn(admin.schema(_SCHEMA), webhook_secret=secret)


def configure() -> None:
    """Register both drains on the seed-side scheduler. Idempotent; called
    from `portal_leads/__init__.py::register()` at import time."""
    seed_scheduler.register(
        "olx_leads_retry",
        olx_leads_retry_job,
        cron="*/15 * * * *",
    )
    seed_scheduler.register(
        "portal_lead_forward_drain",
        portal_lead_forward_drain_job,
        cron="*/5 * * * *",
    )
    logger.info(
        "portal_leads scheduler configured: olx inbox retry '*/15 * * * *', "
        "forward drain '*/5 * * * *'"
    )


__all__ = [
    "configure",
    "olx_leads_retry_job",
    "portal_lead_forward_drain_job",
]

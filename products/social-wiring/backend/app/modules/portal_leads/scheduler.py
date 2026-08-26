"""Scheduled jobs for the `portal_leads` module — the inbox drains, the
forward drain, and the ImovelWeb reconciliation pull.

Four jobs, one per failure mode:

* **`olx_leads_retry`** (*/15) and **`imovelweb_leads_retry`** (*/15) drain
  their vendor's inbox. Both receivers answer first and process afterwards,
  so a lead whose ingest failed (unresolvable org, a mapping error, a DB
  blip) sits in the events table as `error` or `unresolved` and nothing
  else would ever pick it up. Fifteen minutes rather than daily because the
  drain is cheap — one indexed read of a partial index that is almost always
  empty — and because the cost of waiting is a real customer not being
  called back.

* **`portal_lead_forward_drain`** (*/5) drains the forward queue.

* **`imovelweb_reconcile`** (hourly) is a different thing entirely, and only
  ImovelWeb can have it: that vendor exposes a PULL API, so a delivery we
  never received is still recoverable. The drain re-tries what we HOLD; the
  reconcile fetches what we never got. It runs at :17 rather than :00 to
  stay out of the herd every other hourly job lands in.

All of them swallow per-run exceptions with a WARNING — one bad run must not
kill the schedule — and take DI seams so a test drives the real job without
a scheduler or a database (`KB § PATTERNS/backend/di-test-seam.md`).

── The empty-queue pre-flight ─────────────────────────────────────────
The jobs check whether there is ANY work before resolving config.

That ordering is the whole point. `get_olx_config()` is deliberately
never cached (see `deps.py`: an operator rotating the secret must not
need a redeploy), so every call costs four `app_integration_config`
reads. Both jobs used to pay that BEFORE discovering the queue was
empty, which on a tenant where OLX is not configured at all — no
webhook secret, no API key, no org mapping, zero rows ever received —
meant four wasted reads every five minutes, forever.

Measured on 2026-08-22: 2090 requests in 24h, 15.5% of ALL database
traffic for this project, to do nothing. The queue check itself was
never the cost; the config resolution in front of it was.

So the order is now: cheap indexed `LIMIT 1` first, and config only
when a row actually exists. Nothing is cached, so a rotated secret is
still picked up on the very next run that has work — the property
`deps.py` protects is untouched.

Deliberately NOT "disable the jobs when OLX is unconfigured": a retry
queue that silently stops existing is the failure shape this module was
built to avoid, and it would have to be remembered and re-enabled the
day OLX goes live. This costs one indexed read per run and needs no
one to remember anything.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


def _has_pending_events(client: Any) -> bool:
    """Is there at least one event awaiting re-processing?

    `LIMIT 1` on the same status filter `drain_pending` uses — the point
    is to answer "any work?" for one indexed row read, not to fetch the
    batch. `drain_pending` re-queries with the real limit when this says
    yes; that second query happens only on the rare non-empty run.

    A failure here returns True, not False: "I could not tell" must fall
    through to the real drain, which has its own error handling. Guessing
    "no work" on a transport blip would silently skip a real lead, which
    is the exact outcome this module exists to prevent.
    """
    from app.modules.portal_leads.services.olx_webhook_service import (
        PENDING_STATUSES,
    )

    try:
        resp = (
            client.table("olx_lead_events")
            .select("id")
            .in_("status", list(PENDING_STATUSES))
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — see docstring: fail OPEN
        logger.warning(
            "olx drain: pre-flight check failed (%s) — running the drain anyway",
            exc,
        )
        return True
    return bool(resp.data)


def _has_due_forwards(client: Any) -> bool:
    """Is there at least one forward due for delivery?

    Same shape and same fail-open rule as `_has_pending_events`, reusing
    `due_forwards` so the definition of "due" lives in exactly one place
    — a hand-rolled copy of that predicate here would drift the moment
    the backoff schedule changes.
    """
    from app.modules.portal_leads.services.forward_service import due_forwards

    try:
        return bool(due_forwards(client, limit=1))
    except Exception as exc:  # noqa: BLE001 — fail OPEN
        logger.warning(
            "portal-forward drain: pre-flight check failed (%s) — running "
            "the drain anyway", exc,
        )
        return True


def _drain_sync(
    *,
    admin_client_factory: Optional[Callable[[], Any]] = None,
    service_factory: Optional[Callable[..., Any]] = None,
    has_work_fn: Optional[Callable[[Any], bool]] = None,
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

    # Pre-flight BEFORE config: see the module docstring. Returning here
    # skips four uncached `app_integration_config` reads on every run of a
    # queue that is empty ~always.
    if not (has_work_fn or _has_pending_events)(client):
        return

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


def _imovelweb_drain_sync(
    *,
    admin_client_factory: Optional[Callable[[], Any]] = None,
    service_factory: Optional[Callable[..., Any]] = None,
) -> None:
    """Sync body of the ImovelWeb drain. Same DI-seam shape as the OLX one."""
    admin = (admin_client_factory or get_admin_client)()
    if admin is None:
        logger.warning("imovelweb drain: no admin client — skipping run")
        return

    if service_factory is None:
        from app.modules.portal_leads.services.imovelweb_webhook_service import (
            ImovelWebWebhookService,
        )

        service_factory = ImovelWebWebhookService

    client = admin.schema(_SCHEMA)
    default_org = None
    try:
        from app.dependencies import coerce_org_uuid
        from app.services.app_config_store import resolve_imovelweb_config

        configured = resolve_imovelweb_config().leads_org_id
        if configured:
            default_org = coerce_org_uuid(configured)
    except Exception as exc:  # noqa: BLE001 — config gap must not kill the drain
        # Without a default org the drain still retries every row; those that
        # need the fallback stay `unresolved`, which is the honest outcome
        # rather than a guessed tenant.
        logger.warning("imovelweb drain: could not resolve the default org (%s)", exc)

    svc = service_factory(client=client, default_org_id=default_org)
    try:
        result = svc.drain_pending()
        if result.get("examined"):
            logger.info(
                "imovelweb drain: examined=%d processed=%d pending=%d exhausted=%d",
                result.get("examined", 0), result.get("processed", 0),
                result.get("still_pending", 0), result.get("exhausted", 0),
            )
    except Exception as exc:  # noqa: BLE001 — one bad run must not kill the schedule
        logger.warning("imovelweb drain: run failed: %s", exc, exc_info=True)


async def _imovelweb_reconcile_async(
    *,
    admin_client_factory: Optional[Callable[[], Any]] = None,
    adapter_factory: Optional[Callable[[], Any]] = None,
) -> None:
    """Body of the reconciliation pull.

    Async all the way down rather than thread-offloaded like the drains: the
    OpenNavent client is async, and wrapping an async client in
    `asyncio.to_thread` would need a nested event loop.
    """
    admin = (admin_client_factory or get_admin_client)()
    if admin is None:
        logger.warning("imovelweb reconcile: no admin client — skipping run")
        return

    if adapter_factory is None:
        from app.modules.portal_leads.routers.imovelweb_webhook import (
            get_imovelweb_adapter,
        )

        adapter_factory = get_imovelweb_adapter

    from app.modules.portal_leads.services import imovelweb_reconcile_service

    client = admin.schema(_SCHEMA)
    try:
        adapter = adapter_factory()
        result = await imovelweb_reconcile_service.reconcile_all_agencies(
            client, adapter
        )
        if result.get("recovered"):
            # Worth an INFO every time it is non-zero: a recovered lead is a
            # lead the callback path LOST, and a rising count is the signal
            # that the 1.5-second budget is not being met.
            logger.info(
                "imovelweb reconcile: agencies=%d recovered=%d",
                result.get("agencies", 0), result.get("recovered", 0),
            )
    except Exception as exc:  # noqa: BLE001 — one bad run must not kill the schedule
        logger.warning("imovelweb reconcile: run failed: %s", exc, exc_info=True)


async def imovelweb_leads_retry_job() -> None:
    """Async wrapper — same thread-offload convention as the OLX drain."""
    try:
        await asyncio.to_thread(_imovelweb_drain_sync)
    except Exception as exc:  # noqa: BLE001
        logger.error("imovelweb drain: job wrapper error: %s", exc, exc_info=True)


async def imovelweb_reconcile_job() -> None:
    try:
        await _imovelweb_reconcile_async()
    except Exception as exc:  # noqa: BLE001
        logger.error("imovelweb reconcile: job wrapper error: %s", exc, exc_info=True)


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
    has_work_fn: Optional[Callable[[Any], bool]] = None,
) -> None:
    """Async body of the forward drain. Collaborators are DI seams so a
    test drives the real job without a scheduler or a database."""
    admin = (admin_client_factory or get_admin_client)()
    if admin is None:
        logger.warning("portal-forward drain: no admin client — skipping run")
        return

    # Pre-flight BEFORE config — same reasoning as the inbox drain.
    if not (has_work_fn or _has_due_forwards)(admin.schema(_SCHEMA)):
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
    seed_scheduler.register(
        "imovelweb_leads_retry",
        imovelweb_leads_retry_job,
        cron="*/15 * * * *",
    )
    # :17 rather than :00 — every other hourly job in the fleet fires on the
    # hour, and this one makes an upstream call per authorized agency.
    seed_scheduler.register(
        "imovelweb_reconcile",
        imovelweb_reconcile_job,
        cron="17 * * * *",
    )
    logger.info(
        "portal_leads scheduler configured: olx inbox retry '*/15 * * * *', "
        "forward drain '*/5 * * * *', imovelweb inbox retry '*/15 * * * *', "
        "imovelweb reconcile '17 * * * *'"
    )


__all__ = [
    "configure",
    "imovelweb_leads_retry_job",
    "imovelweb_reconcile_job",
    "olx_leads_retry_job",
    "portal_lead_forward_drain_job",
]

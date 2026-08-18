"""Scheduled steady-state pass for the `clientes` person layer.

🔴 Why this exists (found 2026-08-18, five days after Phase 1 landed).

`clientes_service.run_backfill` was written re-runnable exactly as the Phase 1
contract demanded (`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md`
§7: "make the backfill re-runnable such that a second pass picks up
stragglers"). It was then run ONCE, by hand, on 2026-08-13 16:42 — and nothing
in the codebase ever called it again. There was no router exposing it, no
scheduler job, and no database trigger on `leads` / `meta_ads_leads`.

WhatsApp intake never stopped. Measured against the live project five days
later: 44 `leads` and 44 `meta_ads_leads` rows had no `cliente_touches` row,
and 88 `negociacoes_venda` rows had a NULL `cliente_id` — every one of them
created AFTER the backfill ran, none of them keyless (all 44 leads carried a
valid `contato_norm`, so all were fully resolvable). The board simply stopped
showing new arrivals, at roughly nine leads a day, and nothing said so.

The contract closed the MID-run race (a lead arriving while the backfill is
working). What was missing was the POST-run steady state: a one-shot backfill
against a table that keeps growing is a snapshot, not a projection. This
module is that missing leg.

Shape is deliberately the same as `whatsapp_backfill`'s — the sibling job in
this product — so there is one scheduled-sweep idiom here, not two:
a `run_*` body with `cfg` / `admin_client` DI seams, a `_run_*_job` wrapper
that swallows everything so one bad run cannot de-register the job, and a
`configure()` called from `app/main.py` at import time, before
`start_scheduler()` fires in `app/lifespan.py`.

KB § PATTERNS/architect/project-execution.md · roadmap
`project-history/roadmaps/lead-card-hub-2026-08.md` §5 Phase 1.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client
from app.services import clientes_service

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_PAGE = 1000
# The two intake tables. An org appears here iff it owns a source row that
# could need a touch, which makes this list correct by construction — an org
# registry would have to be kept in sync, and a brand-new org whose first lead
# just landed would be missing from `clientes.org_id`.
_SOURCE_TABLES = ("leads", "meta_ads_leads")


def _list_org_ids(admin_client: Any) -> list[UUID]:
    """Every org owning at least one intake row, across ALL orgs.

    Reads the single `org_id` column (paginated — PostgREST caps a response at
    1 000 rows and returns the truncation silently) and dedupes in Python;
    PostgREST has no DISTINCT.
    """
    seen: set[str] = set()
    for table in _SOURCE_TABLES:
        start = 0
        while True:
            rows = (
                admin_client.schema(_SCHEMA)
                .table(table)
                .select("org_id")
                .range(start, start + _PAGE - 1)
                .execute()
            ).data or []
            for row in rows:
                if row.get("org_id"):
                    seen.add(str(row["org_id"]))
            if len(rows) < _PAGE:
                break
            start += _PAGE
    return [UUID(o) for o in sorted(seen)]


def run_clientes_backfill(
    *,
    cfg: Any = None,
    admin_client: Any = None,
    admin_factory: Any = None,
    backfill_fn: Any = None,
) -> dict[str, Any]:
    """Body of the scheduled job — one `run_backfill` per org, degrading per org.

    A failure resolving one org must not stop the others, for the same reason
    `whatsapp_backfill` isolates per connection: a single tenant's bad row
    should not freeze every other tenant's board.

    Returns a per-org summary so the caller (and the tests) can assert on what
    actually happened rather than on log text.

    Every collaborator arrives through a Class-B kwarg seam — `cfg`, the admin
    client (either directly or via `admin_factory`, so the "no client at all"
    branch is reachable without patching), and `backfill_fn`. Production passes
    none of them. This is deliberate and load-bearing: substituting a
    collaborator through a declared seam keeps the real code path under test,
    whereas `monkeypatch.setattr` on our own module replaces the thing the test
    claims to exercise. → KB § PATTERNS/compliance/testing.md (no monkey-
    patching, including in tests; `check_seed_compliance` enforces it).
    """
    cfg = cfg or settings
    if not cfg.clientes_backfill_enabled:
        logger.debug("clientes_backfill: disabled via settings — skipping run")
        return {"skipped": "disabled", "orgs": []}

    resolve_admin = admin_factory or get_admin_client
    admin = admin_client if admin_client is not None else resolve_admin()
    if admin is None:
        logger.warning("clientes_backfill: no admin client — skipping run")
        return {"skipped": "no-admin-client", "orgs": []}

    org_ids = _list_org_ids(admin)
    if not org_ids:
        logger.debug("clientes_backfill: no orgs with intake rows — nothing to do")
        return {"skipped": None, "orgs": []}

    results: list[dict[str, Any]] = []
    for org_id in org_ids:
        try:
            report = (backfill_fn or clientes_service.run_backfill)(admin, org_id)
        except Exception:
            # Named, logged, and carried in the return value — a swallowed
            # per-org failure that left no trace would be the silent-error
            # shape this whole module exists to close.
            logger.error(
                "clientes_backfill: org %s failed — other orgs continue",
                org_id, exc_info=True,
            )
            results.append({"org_id": str(org_id), "ok": False})
            continue
        results.append({
            "org_id": str(org_id),
            "ok": True,
            "clientes_created": report.clientes_created,
            "touches_created": report.touches_created,
            "negociacoes_repointed": report.negociacoes_repointed,
            "negociacoes_collapsed": report.negociacoes_collapsed,
            "stragglers_parked_for_review": report.stragglers_parked_for_review,
            # D16's reactivation half: a new touch attaching to a cliente
            # the inactivity sweep (`clientes_inactivity_service.py`) had
            # put to sleep flips it back to `ativo=true` right here, at
            # touch-insert time — see `_reactivate_if_inactive`'s
            # docstring for why that lives here rather than in the sweep.
            "clientes_reactivated": report.clientes_reactivated,
        })
        if (
            report.clientes_created or report.touches_created
            or report.negociacoes_repointed or report.negociacoes_collapsed
            or report.clientes_reactivated
        ):
            # Only speak up when the pass actually attached something. A quiet
            # no-op run every interval is the healthy state and should not be
            # noise in the log.
            logger.info(
                "clientes_backfill: org %s — %d cliente(s), %d touch(es), "
                "%d negociac%s repointed, %d collapsed into a sibling, "
                "%d reactivated",
                org_id, report.clientes_created, report.touches_created,
                report.negociacoes_repointed,
                "ão" if report.negociacoes_repointed == 1 else "ões",
                report.negociacoes_collapsed,
                report.clientes_reactivated,
            )
    return {"skipped": None, "orgs": results}


def _run_clientes_backfill_job(*, run_fn: Any = None) -> None:
    """Scheduler entrypoint — swallows ALL exceptions so a bug in one run
    never crashes the scheduler or de-registers the job.

    `run_fn` is the seam that lets a test drive the swallow branch with a
    throwing double instead of patching this module."""
    try:
        (run_fn or run_clientes_backfill)()
    except Exception:
        logger.error("clientes_backfill: job run failed", exc_info=True)


def configure(*, cfg: Any = None, scheduler: Any = None) -> None:
    """Register the steady-state pass on the seed-side scheduler.

    Called from ``app/main.py`` at import time (mirrors
    ``whatsapp_backfill.configure()``) so the job lands before
    ``start_scheduler()`` fires in ``app/lifespan.py``. Idempotent —
    ``noctusai_lib.api.scheduler.register`` replaces the job on
    re-registration.
    """
    cfg = cfg or settings
    (scheduler or seed_scheduler).register(
        "clientes_backfill",
        _run_clientes_backfill_job,
        hours=cfg.clientes_backfill_interval_hours,
    )
    logger.info(
        "clientes_backfill scheduler configured: every %dh",
        cfg.clientes_backfill_interval_hours,
    )


__all__ = ["configure", "run_clientes_backfill"]

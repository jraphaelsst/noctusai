"""Scheduled inactivity sweep for `clientes` — D16, the 180-day rule.

Roadmap `project-history/roadmaps/lead-card-hub-2026-08.md` D16: "Inactivity
threshold: 180 days, configurable in the UI." `048` (P1.1) shipped the
columns (`ativo` / `inativo_em` / `arquivado_em`) and the manual half — an
operator can flip a cliente inactive/active by hand via
`PATCH /api/clientes/{id}`. Nothing ever set `inativo_em` on its own. The
working Ativos/Inativos board tabs made this look finished, which is exactly
why the gap survived Phase 1: `frontend/src/hooks/useClientes.ts` even
carries a comment noting `arquivado_em` has "no documented write path" —
the automatic side was simply never built. This module is that missing leg.

THE SILENCE DEFINITION (the crux of this slice — read this before touching
the predicate)
--------------------------------------------------------------------------
"Silence" is computed from `clientes.ultimo_contato_em`
(`cliente_touches.ocorreu_em`'s MAX, kept current by
`clientes_service._recompute_span` on every touch write — see `048`'s
header), NEVER from `clientes.updated_at`. `updated_at` moves on ANY write
to the row (a merge, an undo, a name edit) and would silently shrink the
inactivity window for reasons that have nothing to do with the person
actually being reachable. `ultimo_contato_em` is the honest signal: it only
advances when a REAL touch (a `leads` row, a `meta_ads_leads` row) lands.

That alone is not enough, though — a cliente a human just restored by hand
still has a stale `ultimo_contato_em` (the restore did not manufacture a new
touch). Sweeping it right back to inactive on the very next tick because
"nothing new actually happened" would be the single most infuriating outcome
this slice could ship. So the sweep's effective signal is:

    effective_last_activity = GREATEST(ultimo_contato_em, reativado_em)

`reativado_em` (migration `058`) is set in exactly two places, both outside
this module:
  1. `PATCH /api/clientes/{id}` with `ativo=true` (manual restore,
     `clientes_router.py::update_cliente_route`).
  2. A NEW touch attaching to a cliente the sweep had previously put to
     sleep (`clientes_service.py::_reactivate_if_inactive`, called from
     `_attach_touches` — the reconciliation path a subsequent
     `clientes_backfill_job` run exercises for an already-resolved
     identity).
This is a DELIBERATE split: reactivation-by-touch belongs at TOUCH-INSERT
TIME (where clientes_backfill_job already discovers new touches every 6h),
not in this sweep — the sweep only ever looks at clientes that are
CURRENTLY `ativo = true`, so it has no reason to ever inspect an inactive
row's touches. Building reactivation into the sweep would mean re-scanning
every inactive cliente's touch history on every tick for a case that is
already, naturally, discovered the moment a new touch is written.

`reativado_em` is intentionally NEVER set for a MANUALLY archived cliente
(`arquivado_em IS NOT NULL`) by either of the two call sites above —
`arquivado_em` is a stronger, human, presumably-terminal decision this
sweep (and the reactivation path) must never second-guess. A manually
archived cliente is also structurally invisible to this sweep regardless
(it is already `ativo = false`, so it never appears in the sweep's own
candidate query) — the guard on the reactivation side exists because that
path is reachable through `ativo = false` rows too.

STATE TABLE (every combination that matters)
--------------------------------------------------------------------------
| ativo | inativo_em | arquivado_em | meaning                              |
|-------|------------|--------------|--------------------------------------|
| true  | NULL       | NULL         | normal, active                       |
| true  | NULL       | NULL (+reativado_em set) | restored / reactivated   |
| false | set        | NULL         | auto-swept by THIS module            |
| false | NULL/stale | set          | manually archived by a human — never |
|       |            |              | touched by the sweep OR reactivation |

IDEMPOTENCY + PER-ORG DEGRADATION
--------------------------------------------------------------------------
Shape mirrors `clientes_backfill_job.py` deliberately (same product, same
sweep idiom, so there is one scheduled-sweep pattern here, not two): a
`run_*` body with `cfg`/`admin_client` DI seams, a `_run_*_job` wrapper that
swallows everything so one bad run cannot de-register the job, and
`configure()` called from `app/main.py` at import time, before
`start_scheduler()` fires in `app/lifespan.py`.

The sweep only ever SELECTs `ativo = true` rows, so re-running on unchanged
data is a true no-op — an already-swept cliente never matches the query a
second time. A failing org is caught and logged; the rest of the run
continues (same reasoning as `clientes_backfill_job`: one tenant's bad row
must not freeze every other tenant's board).

`client` MUST ALREADY BE SCHEMA-SCOPED for the same reason
`clientes_service.py`'s module docstring gives: `MockSupabaseClient.schema()`
returns a brand-new wrapper with an empty per-table cache on every call, so
this module resolves `.schema("social_wiring")` exactly ONCE per run and
threads that single scoped client through org enumeration, config
resolution, and the sweep itself.

KB § PATTERNS/architect/project-execution.md · roadmap
`project-history/roadmaps/lead-card-hub-2026-08.md` §5 P1.5.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_PAGE = 1000
_CLIENTES_TABLE = "clientes"
_CONFIG_TABLE = "clientes_inactivity_config"
# PostgREST puts `in_` values in the URL query string — an unbounded id
# list becomes an over-long request line and a bare 400 (the same class of
# incident `clientes_service.py::list_review_groups` documents). Batched
# updates keep the longest request line comfortably under the usual 8 KB
# limit (200 UUIDs ~= 7.6 KB).
_IN_FILTER_BATCH = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    """Same idiom as `identidade_service._parse_dt` / `notification_service`
    — duplicated here rather than imported because the source is a private,
    underscore-prefixed helper in a sibling module (not a public seam), and
    this is now the THIRD occurrence of this exact parse in this product.
    Flagged as a `scoped-improvement:` in this dispatch's delivery note —
    a shared `noctusai_lib.parsing` helper would be the right absorption at
    N=3, not a fourth ad-hoc copy."""
    if len(value) <= 10:  # bare "YYYY-MM-DD"
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ─── org enumeration ────────────────────────────────────────────────────


def _list_org_ids(scoped_client: Any) -> list[UUID]:
    """Every org owning at least one `clientes` row — the sweep's own
    source of truth, unlike `clientes_backfill_job`'s `leads`/
    `meta_ads_leads` sourcing: an org with zero clientes has nothing for
    THIS sweep to do (a cliente is always created by the backfill before
    it could ever go inactive)."""
    seen: set[str] = set()
    start = 0
    while True:
        rows = (
            scoped_client.table(_CLIENTES_TABLE)
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


# ─── per-org configured threshold (D16) ─────────────────────────────────


def get_threshold_config(
    scoped_client: Any, org_id: UUID, *, default_days: int
) -> dict[str, Any]:
    """Resolve the org's configured threshold AND whether it is actually
    configured (a row exists) or falling back to `default_days`. The
    settings endpoint (`GET /api/settings/clientes-inactivity`) needs
    BOTH — a UI rendering "using the default (365)" vs. "set to 45" needs
    to tell those two apart, not just see the resolved integer."""
    rows = (
        scoped_client.table(_CONFIG_TABLE)
        .select("threshold_days")
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {"threshold_days": default_days, "configured": False}
    return {"threshold_days": int(rows[0]["threshold_days"]), "configured": True}


def get_threshold_days(scoped_client: Any, org_id: UUID, *, default_days: int) -> int:
    """Resolve just the effective threshold value — the sweep's own call
    shape, thin wrapper over :func:`get_threshold_config`. No row for this
    org -> the org never configured one -> `default_days` (the platform
    default, 365 since 2026-08-18 — migration `059`; D16 originally said
    180, and `migrations/APPLIED.md` records why it moved). A row WHOSE
    `threshold_days` is 0 is a DIFFERENT,
    explicit state (the org turned the sweep off) — the caller decides
    what to do with a 0, this function only ever reports what is actually
    stored. See this module's docstring / `058`'s header for why these
    two are kept distinct."""
    return get_threshold_config(scoped_client, org_id, default_days=default_days)[
        "threshold_days"
    ]


def set_threshold_days(scoped_client: Any, org_id: UUID, threshold_days: int) -> dict:
    """Upsert (by hand — see below) the org's configured threshold.
    `threshold_days = 0` is a valid, meaningful value (disables the sweep
    for this org) — only a negative value is rejected, at the router
    boundary via `Field(ge=0)` AND here (belt-and-suspenders: this
    function has its own callers beyond the router, e.g. a future admin
    script).

    SELECT-then-INSERT/UPDATE rather than a bare `.upsert(on_conflict=...)`
    call: `MockSupabaseClient.upsert()` is a documented no-op in the seed
    test double (`noctusai_lib/testing/mocks.py` — "Upsert propagation is
    deferred to a follow-up project"), so a real `.upsert()` call here
    would be silently UNVERIFIABLE by any test in this product today. The
    explicit two-step is fully correct against real PostgREST (org_id is
    the primary key) and is what every existing write path in this
    product's test suite can actually observe (`.update()`/`.insert()`
    mutate the mock's shared row list; `.upsert()` does not)."""
    if threshold_days < 0:
        raise ValueError("threshold_days must be >= 0")
    payload = {
        "org_id": str(org_id),
        "threshold_days": threshold_days,
        "updated_at": _now().isoformat(),
    }
    existing = (
        scoped_client.table(_CONFIG_TABLE)
        .select("org_id")
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    if existing:
        scoped_client.table(_CONFIG_TABLE).update(payload).eq(
            "org_id", str(org_id)
        ).execute()
    else:
        scoped_client.table(_CONFIG_TABLE).insert(payload).execute()
    return payload


# ─── the sweep itself ────────────────────────────────────────────────────


def _select_active_clientes(scoped_client: Any, org_id: UUID) -> list[dict]:
    """Every currently-active cliente for `org_id`, paginated past
    PostgREST's 1 000-row cap — ~9 300 clientes exist live, comfortably
    past the cap for a single org's slice on a busy tenant."""
    out: list[dict] = []
    start = 0
    while True:
        rows = (
            scoped_client.table(_CLIENTES_TABLE)
            .select("id,ultimo_contato_em,reativado_em")
            .eq("org_id", str(org_id))
            .eq("ativo", True)
            .range(start, start + _PAGE - 1)
            .execute()
        ).data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def _effective_last_activity(row: dict) -> Optional[datetime]:
    """GREATEST(ultimo_contato_em, reativado_em) — see the module docstring
    for why `reativado_em` is part of this at all."""
    candidates = [
        _parse_dt(value)
        for value in (row.get("ultimo_contato_em"), row.get("reativado_em"))
        if value
    ]
    return max(candidates) if candidates else None


def _sweep_org(scoped_client: Any, org_id: UUID, cfg: Any, moment: datetime) -> dict[str, Any]:
    threshold_days = get_threshold_days(
        scoped_client, org_id, default_days=cfg.clientes_inactivity_threshold_days_default
    )
    if threshold_days <= 0:
        return {"skipped": "disabled", "swept": 0, "threshold_days": threshold_days}

    cutoff = moment - timedelta(days=threshold_days)
    candidates = _select_active_clientes(scoped_client, org_id)

    stale_ids: list[str] = []
    skipped_no_signal = 0
    for row in candidates:
        last_activity = _effective_last_activity(row)
        if last_activity is None:
            # No `ultimo_contato_em` at all should never happen for a real
            # cliente (every one is created WITH touches — see `048`'s
            # header) — but guessing an inactivation for a row with no
            # honest signal is exactly the silent-error shape this module
            # must not produce. Skip and say so, rather than assume.
            skipped_no_signal += 1
            logger.warning(
                "clientes_inactivity: cliente %s (org %s) has no "
                "ultimo_contato_em/reativado_em — skipping, not guessing",
                row["id"], org_id,
            )
            continue
        if last_activity >= cutoff:
            continue
        stale_ids.append(row["id"])

    moment_iso = moment.isoformat()
    for batch in _batched(stale_ids, _IN_FILTER_BATCH):
        (
            scoped_client.table(_CLIENTES_TABLE)
            .update({
                "ativo": False,
                "inativo_em": moment_iso,
                "inativo_threshold_dias": threshold_days,
                "updated_at": moment_iso,
            })
            .eq("org_id", str(org_id))
            .in_("id", batch)
            .execute()
        )

    return {
        "skipped": None,
        "swept": len(stale_ids),
        "threshold_days": threshold_days,
        "candidates": len(candidates),
        "skipped_no_signal": skipped_no_signal,
    }


def run_clientes_inactivity_sweep(
    *,
    cfg: Any = None,
    admin_client: Any = None,
    admin_factory: Any = None,
    now: Optional[datetime] = None,
    sweep_fn: Any = None,
) -> dict[str, Any]:
    """Body of the scheduled job — one org at a time, degrading per org
    (mirrors `clientes_backfill_job.run_clientes_backfill` exactly, same
    reasoning: one tenant's bad row must not freeze every other tenant's
    board). Every collaborator arrives through a declared Class-B kwarg
    seam — `cfg`, the admin client (directly or via `admin_factory`),
    `now` (so a test can pin "the present" instead of racing the wall
    clock), and `sweep_fn` (the per-org body, swappable with a throwing
    double to exercise the per-org-isolation branch) — never via
    `monkeypatch.setattr` on this module.
    → KB § PATTERNS/compliance/testing.md."""
    cfg = cfg or settings
    if not cfg.clientes_inactivity_sweep_enabled:
        logger.debug("clientes_inactivity: disabled via settings — skipping run")
        return {"skipped": "disabled", "orgs": []}

    resolve_admin = admin_factory or get_admin_client
    admin = admin_client if admin_client is not None else resolve_admin()
    if admin is None:
        logger.warning("clientes_inactivity: no admin client — skipping run")
        return {"skipped": "no-admin-client", "orgs": []}

    scoped = admin.schema(_SCHEMA)
    org_ids = _list_org_ids(scoped)
    if not org_ids:
        logger.debug("clientes_inactivity: no orgs with clientes — nothing to do")
        return {"skipped": None, "orgs": []}

    moment = now or _now()
    body = sweep_fn or _sweep_org
    results: list[dict[str, Any]] = []
    for org_id in org_ids:
        try:
            report = body(scoped, org_id, cfg, moment)
        except Exception:
            logger.error(
                "clientes_inactivity: org %s failed — other orgs continue",
                org_id, exc_info=True,
            )
            results.append({"org_id": str(org_id), "ok": False})
            continue
        results.append({"org_id": str(org_id), "ok": True, **report})
        if report.get("swept"):
            logger.info(
                "clientes_inactivity: org %s — %d cliente(s) swept inactive "
                "(threshold %dd)",
                org_id, report["swept"], report["threshold_days"],
            )
    return {"skipped": None, "orgs": results}


def _run_clientes_inactivity_job(*, run_fn: Any = None) -> None:
    """Scheduler entrypoint — swallows ALL exceptions so a bug in one run
    never crashes the scheduler or de-registers the job."""
    try:
        (run_fn or run_clientes_inactivity_sweep)()
    except Exception:
        logger.error("clientes_inactivity: job run failed", exc_info=True)


def configure(*, cfg: Any = None, scheduler: Any = None) -> None:
    """Register the sweep on the seed-side scheduler. Called from
    `app/main.py` at import time (mirrors `clientes_backfill_job.configure()`)
    so the job lands before `start_scheduler()` fires in `app/lifespan.py`.
    Idempotent — `noctusai_lib.api.scheduler.register` replaces the job on
    re-registration."""
    cfg = cfg or settings
    (scheduler or seed_scheduler).register(
        "clientes_inactivity_sweep",
        _run_clientes_inactivity_job,
        hours=cfg.clientes_inactivity_sweep_interval_hours,
    )
    logger.info(
        "clientes_inactivity scheduler configured: every %dh",
        cfg.clientes_inactivity_sweep_interval_hours,
    )


__all__ = [
    "configure",
    "run_clientes_inactivity_sweep",
    "get_threshold_config",
    "get_threshold_days",
    "set_threshold_days",
]

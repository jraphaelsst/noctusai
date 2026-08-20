"""Daily Vista catalog refresh — registration, org discovery, isolation.

Pins the three things that make this job either work or silently not:

  · It must register at **00:05 America/Sao_Paulo**, not UTC. The seed
    scheduler is constructed with that timezone, so a cron string is local
    time; asserting the literal pins the user-agreed hour.
  · Org discovery must paginate. PostgREST caps an unbounded select at
    1000 rows and this table holds ~1919 per org — an uncapped read would
    see only the first page and, with a single org, still look correct.
    That is the exact trap `imoveis_service._select_all` documents.
  · One org failing must not cost the others their refresh.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.services import imoveis_sync_scheduler as sched

_ORG_A = "6dd73140-74a4-41c6-aeff-bc94b5312b53"
_ORG_B = "0f5b1a2c-9d3e-4a7b-8c1d-2e3f4a5b6c7d"


class _FakeTable:
    """Minimal PostgREST chain stand-in — only `.range().execute()` is used."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self.ranges: list[tuple[int, int]] = []

    def select(self, *_a, **_kw):
        return self

    def range(self, start: int, end: int):
        self.ranges.append((start, end))
        index = start // 1000
        self._current = self._pages[index] if index < len(self._pages) else []
        return self

    def execute(self):
        return MagicMock(data=self._current)


class _FakeAdmin:
    def __init__(self, table: _FakeTable) -> None:
        self._table = table

    def schema(self, _name):
        return self

    def table(self, _name):
        return self._table


# ─── Registration ───────────────────────────────────────────────────────


def test_configure_registers_job_at_five_past_midnight():
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()

    job = seed_scheduler.scheduler.get_job("imoveis_vista_sync_daily")
    assert job is not None, "job did not register — the mirror would never refresh"

    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "0"
    assert fields["minute"] == "5"
    # Local time, not UTC — the seed scheduler owns the timezone.
    assert str(job.trigger.timezone) == "America/Sao_Paulo"


def test_configure_reuses_one_stable_job_id():
    """Two `configure()` calls must not create two DIFFERENT jobs.

    Deliberately not asserting `len(get_jobs()) == 1`. `register()` passes
    `replace_existing=True`, but APScheduler only honours that when the
    scheduler is RUNNING — on a stopped one it queues into `_pending_jobs`
    and the dedup happens at `start()`. So a stopped scheduler genuinely
    holds two same-id entries, and the seed docstring's "re-import is
    idempotent" claim is true only post-start.

    That is a seed-level doc-vs-behaviour gap, surfaced rather than papered
    over here. What this job needs is the property that survives it: one
    stable id, so `start()` collapses the duplicates instead of scheduling
    two nightly full pulls.
    """
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()
    sched.configure()

    ids = {j.id for j in seed_scheduler.scheduler.get_jobs()}
    assert ids == {"imoveis_vista_sync_daily"}


# ─── Org discovery ──────────────────────────────────────────────────────


def test_orgs_with_catalog_paginates_past_the_postgrest_cap():
    # Two full pages then a short one: an uncapped read would stop at 1000
    # and never see org B, which only appears on page 2.
    pages = [
        [{"org_id": _ORG_A}] * 1000,
        [{"org_id": _ORG_B}] * 1000,
        [{"org_id": _ORG_B}] * 19,
    ]
    table = _FakeTable(pages)

    orgs = sched._orgs_with_catalog(_FakeAdmin(table))

    assert orgs == sorted([_ORG_A, _ORG_B])
    assert table.ranges == [(0, 999), (1000, 1999), (2000, 2999)]


def test_orgs_with_catalog_empty_table_returns_empty():
    assert sched._orgs_with_catalog(_FakeAdmin(_FakeTable([[]]))) == []


def test_orgs_with_catalog_skips_null_org_ids():
    table = _FakeTable([[{"org_id": _ORG_A}, {"org_id": None}, {}]])
    assert sched._orgs_with_catalog(_FakeAdmin(table)) == [_ORG_A]


# ─── The job ────────────────────────────────────────────────────────────


def test_job_skips_entirely_when_vista_unconfigured(monkeypatch):
    """No adapter ⇒ no discovery, no sync. Not an empty sync — no sync."""
    monkeypatch.setattr(sched, "get_admin_client", lambda: MagicMock())
    monkeypatch.setattr(sched, "_build_adapter", lambda: None)
    discovery = MagicMock()
    monkeypatch.setattr(sched, "_orgs_with_catalog", discovery)

    asyncio.run(sched.daily_imoveis_sync_job())

    discovery.assert_not_called()


def test_job_skips_when_no_org_has_a_catalog(monkeypatch):
    """An empty table is not seeded — the first import is the manual button."""
    monkeypatch.setattr(sched, "get_admin_client", lambda: MagicMock())
    monkeypatch.setattr(sched, "_build_adapter", lambda: MagicMock())
    monkeypatch.setattr(sched, "_orgs_with_catalog", lambda _admin: [])
    build = MagicMock()
    monkeypatch.setattr(sched, "build_sync_service", build)

    asyncio.run(sched.daily_imoveis_sync_job())

    build.assert_not_called()


def test_job_isolates_a_failing_org_and_still_syncs_the_rest(monkeypatch):
    synced: list[str] = []

    class _Svc:
        def __init__(self, org_id_str: str) -> None:
            self._org = org_id_str

        async def sync(self, org_id, *, with_detalhes):
            assert with_detalhes is True, (
                "listar-only would blank caracteristicas on every touched row"
            )
            if str(org_id) == _ORG_A:
                raise RuntimeError("vista 500")
            synced.append(str(org_id))
            return MagicMock(
                complete=True, upserted=1919, detalhes_fetched=1919,
                page_failures=[], detalhes_failed=[], duration_seconds=300.0,
            )

    monkeypatch.setattr(sched, "get_admin_client", lambda: MagicMock())
    monkeypatch.setattr(sched, "_build_adapter", lambda: MagicMock())
    monkeypatch.setattr(
        sched, "_orgs_with_catalog", lambda _admin: [_ORG_A, _ORG_B]
    )
    monkeypatch.setattr(
        sched, "build_sync_service", lambda _admin, _adapter: _Svc(_ORG_A)
    )

    asyncio.run(sched.daily_imoveis_sync_job())

    assert synced == [_ORG_B], "org A's failure swallowed org B's refresh"


def test_job_survives_a_discovery_failure(monkeypatch):
    monkeypatch.setattr(sched, "get_admin_client", lambda: MagicMock())
    monkeypatch.setattr(sched, "_build_adapter", lambda: MagicMock())

    def _boom(_admin):
        raise RuntimeError("postgrest down")

    monkeypatch.setattr(sched, "_orgs_with_catalog", _boom)
    build = MagicMock()
    monkeypatch.setattr(sched, "build_sync_service", build)

    # Must not raise — an escaping exception reaches APScheduler as a bare
    # traceback with no org context.
    asyncio.run(sched.daily_imoveis_sync_job())
    build.assert_not_called()


def test_job_warns_rather_than_claiming_clean_on_a_degraded_run(monkeypatch, caplog):
    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            return MagicMock(
                complete=False, upserted=1900, detalhes_fetched=1880,
                page_failures=["page 12"], detalhes_failed=["CA0190"],
                duration_seconds=310.0,
            )

    monkeypatch.setattr(sched, "get_admin_client", lambda: MagicMock())
    monkeypatch.setattr(sched, "_build_adapter", lambda: MagicMock())
    monkeypatch.setattr(sched, "_orgs_with_catalog", lambda _admin: [_ORG_A])
    monkeypatch.setattr(
        sched, "build_sync_service", lambda _admin, _adapter: _Svc()
    )

    with caplog.at_level("INFO"):
        asyncio.run(sched.daily_imoveis_sync_job())

    levels = {r.levelname for r in caplog.records if "imoveis_vista_sync" in r.message}
    assert "WARNING" in levels, "a partial pull logged as a clean run"

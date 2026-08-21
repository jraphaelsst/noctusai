"""Daily Vista catalog refresh — registration, discovery, catch-up.

Pins the things that make this job either work or silently not:

  · It registers at **00:05 America/Sao_Paulo**, not UTC, with an hour of
    misfire grace so a restart spanning the slot still fires.
  · Org discovery paginates. PostgREST caps an unbounded select at 1000
    rows and this table holds ~1919 per org — an uncapped read would see
    only the first page and, with a single org, still look correct. The
    trap `imoveis_service._select_all` documents.
  · One org failing must not cost the others their refresh.
  · The startup catch-up re-runs a MISSED slot and stays quiet otherwise.
    This is the layer that turns the refresh from best-effort into
    guaranteed, so its arithmetic is tested directly rather than inferred.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.services import imoveis_sync_scheduler as sched

_ORG_A = "6dd73140-74a4-41c6-aeff-bc94b5312b53"
_ORG_B = "0f5b1a2c-9d3e-4a7b-8c1d-2e3f4a5b6c7d"
_TZ = ZoneInfo("America/Sao_Paulo")


class _FakeTable:
    """Minimal PostgREST chain stand-in."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self._current: list[dict] = []
        self.ranges: list[tuple[int, int]] = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def range(self, start: int, end: int):
        self.ranges.append((start, end))
        index = start // 1000
        self._current = self._pages[index] if index < len(self._pages) else []
        return self

    def execute(self):
        return MagicMock(data=self._current or (self._pages[0] if self._pages else []))


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
    assert str(job.trigger.timezone) == "America/Sao_Paulo"


def test_configure_sets_an_hour_of_misfire_grace():
    """The seed default is 30s, which would skip a restart spanning 00:05."""
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()

    job = seed_scheduler.scheduler.get_job("imoveis_vista_sync_daily")
    assert job.misfire_grace_time == 3600


def test_configure_is_idempotent():
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()
    sched.configure()
    assert len(seed_scheduler.scheduler.get_jobs()) == 1


# ─── Overdue arithmetic ─────────────────────────────────────────────────


def test_last_slot_is_today_when_now_is_after_the_slot():
    now = datetime(2026, 8, 20, 9, 0, tzinfo=_TZ)
    assert sched._last_expected_slot(now) == datetime(2026, 8, 20, 0, 5, tzinfo=_TZ)


def test_last_slot_is_yesterday_when_now_is_before_the_slot():
    """00:02 belongs to YESTERDAY's slot — the classic off-by-one here."""
    now = datetime(2026, 8, 20, 0, 2, tzinfo=_TZ)
    assert sched._last_expected_slot(now) == datetime(2026, 8, 19, 0, 5, tzinfo=_TZ)


def test_last_slot_handles_a_utc_instant():
    """Callers pass an aware datetime; it must be converted, not assumed."""
    now = datetime(2026, 8, 20, 2, 0, tzinfo=timezone.utc)  # 23:00 on the 19th local
    assert sched._last_expected_slot(now) == datetime(2026, 8, 19, 0, 5, tzinfo=_TZ)


def test_org_synced_after_the_slot_is_not_overdue():
    # `sincronizado_em` is stored UTC. 00:06 local is 03:06Z — writing the
    # naive-looking "00:06Z" here would be 21:06 the PREVIOUS day locally,
    # i.e. still overdue. The comparison is instant-vs-instant on purpose.
    now = datetime(2026, 8, 20, 9, 0, tzinfo=_TZ)
    admin = _FakeAdmin(_FakeTable([[{"sincronizado_em": "2026-08-20T03:06:00+00:00"}]]))
    assert sched._overdue_orgs(admin, [_ORG_A], now) == []


def test_org_synced_before_the_slot_is_overdue():
    now = datetime(2026, 8, 20, 9, 0, tzinfo=_TZ)
    admin = _FakeAdmin(_FakeTable([[{"sincronizado_em": "2026-08-03T23:51:41+00:00"}]]))
    assert sched._overdue_orgs(admin, [_ORG_A], now) == [_ORG_A]


def test_org_never_synced_is_overdue():
    now = datetime(2026, 8, 20, 9, 0, tzinfo=_TZ)
    admin = _FakeAdmin(_FakeTable([[{"sincronizado_em": None}]]))
    assert sched._overdue_orgs(admin, [_ORG_A], now) == [_ORG_A]


def test_unreadable_last_sync_counts_as_overdue():
    """Re-running an idempotent sync is cheaper than a day of staleness."""
    now = datetime(2026, 8, 20, 9, 0, tzinfo=_TZ)

    class _Boom(_FakeAdmin):
        def table(self, _name):
            raise RuntimeError("postgrest down")

    assert sched._overdue_orgs(_Boom(_FakeTable([])), [_ORG_A], now) == [_ORG_A]


# ─── Org discovery ──────────────────────────────────────────────────────


def test_orgs_with_catalog_paginates_past_the_postgrest_cap():
    pages = [
        [{"org_id": _ORG_A}] * 1000,
        [{"org_id": _ORG_B}] * 1000,
        [{"org_id": _ORG_B}] * 19,
    ]
    table = _FakeTable(pages)

    orgs = sched._orgs_with_catalog(_FakeAdmin(table))

    assert orgs == sorted([_ORG_A, _ORG_B])
    assert table.ranges == [(0, 999), (1000, 1999), (2000, 2999)]


def test_orgs_with_catalog_skips_null_org_ids():
    table = _FakeTable([[{"org_id": _ORG_A}, {"org_id": None}, {}]])
    assert sched._orgs_with_catalog(_FakeAdmin(table)) == [_ORG_A]


# ─── The cron path ──────────────────────────────────────────────────────


def test_job_skips_entirely_when_vista_unconfigured():
    discovery = MagicMock()

    asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: None, discover_fn=discovery))

    discovery.assert_not_called()


def test_job_skips_when_no_org_has_a_catalog():
    build = MagicMock()

    asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [], sync_service_factory=build))

    build.assert_not_called()


def test_cron_path_does_not_filter_by_overdue():
    """The scheduled run refreshes everyone; only catch-up filters."""
    synced: list[str] = []

    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            synced.append(str(org_id))
            return MagicMock(
                complete=True, upserted=1, detalhes_fetched=1,
                page_failures=[], detalhes_failed=[], duration_seconds=1.0,
            )

    overdue = MagicMock()

    asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A, _ORG_B], sync_service_factory=lambda _a, _b: _Svc(), overdue_fn=overdue))

    assert synced == [_ORG_A, _ORG_B]
    overdue.assert_not_called()


def test_job_isolates_a_failing_org_and_still_syncs_the_rest():
    synced: list[str] = []

    class _Svc:
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


    asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A, _ORG_B], sync_service_factory=lambda _a, _b: _Svc()))

    assert synced == [_ORG_B], "org A's failure swallowed org B's refresh"


def test_job_survives_a_discovery_failure():

    def _boom(_a):
        raise RuntimeError("postgrest down")

    build = MagicMock()

    asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=_boom, sync_service_factory=build))
    build.assert_not_called()


def test_job_warns_rather_than_claiming_clean_on_a_degraded_run(caplog):
    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            return MagicMock(
                complete=False, upserted=1900, detalhes_fetched=1880,
                page_failures=["page 12"], detalhes_failed=["CA0190"],
                duration_seconds=310.0,
            )


    with caplog.at_level("INFO"):
        asyncio.run(sched.daily_imoveis_sync_job(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A], sync_service_factory=lambda _a, _b: _Svc()))

    levels = {r.levelname for r in caplog.records if "imoveis_vista_sync" in r.message}
    assert "WARNING" in levels, "a partial pull logged as a clean run"


# ─── The catch-up path ──────────────────────────────────────────────────


def test_catch_up_runs_the_missed_slot():
    """The guarantee: container down at 00:05, sync happens on boot."""
    synced: list[str] = []

    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            synced.append(str(org_id))
            return MagicMock(
                complete=True, upserted=1919, detalhes_fetched=1919,
                page_failures=[], detalhes_failed=[], duration_seconds=300.0,
            )


    asyncio.run(sched.catch_up_if_overdue(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A], overdue_fn=lambda _a, orgs, _now: orgs, sync_service_factory=lambda _a, _b: _Svc()))

    assert synced == [_ORG_A]


def test_catch_up_is_a_no_op_when_nothing_is_overdue():
    """The normal boot: must not trigger a 4-6 minute pull for nothing."""
    build = MagicMock()

    asyncio.run(sched.catch_up_if_overdue(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A, _ORG_B], overdue_fn=lambda _a, _orgs, _now: [], sync_service_factory=build))

    build.assert_not_called()


def test_catch_up_syncs_only_the_overdue_org():
    synced: list[str] = []

    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            synced.append(str(org_id))
            return MagicMock(
                complete=True, upserted=1, detalhes_fetched=1,
                page_failures=[], detalhes_failed=[], duration_seconds=1.0,
            )


    asyncio.run(sched.catch_up_if_overdue(admin_factory=lambda: MagicMock(), adapter_factory=lambda: MagicMock(), discover_fn=lambda _a: [_ORG_A, _ORG_B], overdue_fn=lambda _a, _orgs, _now: [_ORG_B], sync_service_factory=lambda _a, _b: _Svc()))

    assert synced == [_ORG_B]


def test_schedule_catch_up_returns_a_task_and_does_not_block():
    """Lifespan must not await a 4-6 minute pull."""
    started = asyncio.Event()

    async def _slow():
        started.set()
        await asyncio.sleep(0)

    async def _drive():
        import app.services.imoveis_sync_scheduler as m
        original = m.catch_up_if_overdue
        m.catch_up_if_overdue = _slow
        try:
            task = m.schedule_catch_up()
            assert task is not None
            assert not task.done(), "schedule_catch_up blocked on the sync"
            await task
            assert started.is_set()
        finally:
            m.catch_up_if_overdue = original

    asyncio.run(_drive())


def test_schedule_catch_up_outside_a_loop_reports_rather_than_crashing(caplog):
    """No event loop ⇒ say the catch-up did not start; never raise."""
    with caplog.at_level("ERROR"):
        assert sched.schedule_catch_up() is None
    assert any("did NOT start" in r.message for r in caplog.records)


def test_cron_and_catch_up_cannot_run_concurrently():
    """A boot at 00:04 must not run two full pulls against one table."""
    concurrent = 0
    peak = 0

    class _Svc:
        async def sync(self, org_id, *, with_detalhes):
            nonlocal concurrent, peak
            concurrent += 1
            peak = max(peak, concurrent)
            await asyncio.sleep(0)
            concurrent -= 1
            return MagicMock(
                complete=True, upserted=1, detalhes_fetched=1,
                page_failures=[], detalhes_failed=[], duration_seconds=1.0,
            )

    seams = dict(
        admin_factory=lambda: MagicMock(),
        adapter_factory=lambda: MagicMock(),
        discover_fn=lambda _a: [_ORG_A],
        overdue_fn=lambda _a, orgs, _now: orgs,
        sync_service_factory=lambda _a, _b: _Svc(),
    )

    async def _both():
        await asyncio.gather(
            sched.daily_imoveis_sync_job(**seams),
            sched.catch_up_if_overdue(**seams),
        )

    asyncio.run(_both())

    assert peak == 1, f"two syncs overlapped (peak={peak})"

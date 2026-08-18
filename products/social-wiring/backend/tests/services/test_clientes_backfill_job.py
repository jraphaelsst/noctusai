"""Tests for clientes_backfill_job.py — the lead-card-hub Phase 1 steady state.

🔴 What this guards. `clientes_service.run_backfill` was written re-runnable
and then never re-run: no router, no scheduler job, no DB trigger called it
after the one manual pass on 2026-08-13. Five days later 44 `leads` + 44
`meta_ads_leads` rows had no `cliente_touches` row and 88 `negociacoes_venda`
rows had a NULL `cliente_id`, all created after that pass. The board stopped
showing new arrivals and nothing said so.

The failure was never in the backfill's logic — it was that nothing invoked
it. So the tests that matter here are the wiring ones: `configure()` actually
registers on the scheduler, the job survives a throwing run, and one org's
failure does not stop the next org. A test of resolution correctness would
have passed happily throughout the outage; `test_clientes_service.py` already
owns that.

🔴 Every collaborator here arrives through a declared Class-B kwarg seam
(`cfg`, `admin_client` / `admin_factory`, `backfill_fn`, `run_fn`,
`scheduler`). The first draft of this file substituted collaborators by
reaching into our own modules and reassigning their attributes instead, and
`check_seed_compliance` caught it on the integration tip with four
high-severity findings. Replacing an attribute on the module under test
swaps out the very thing the test claims to exercise, so the test stops
being evidence — the seams keep the real code path running.
→ KB § PATTERNS/compliance/testing.md.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.services import clientes_backfill_job as job

_ORG_A = "00000000-0000-4000-8000-0000000000a1"
_ORG_B = "00000000-0000-4000-8000-0000000000b2"


def _cfg(*, enabled: bool = True, hours: int = 6) -> SimpleNamespace:
    return SimpleNamespace(
        clientes_backfill_enabled=enabled,
        clientes_backfill_interval_hours=hours,
    )


def _report(**kw) -> SimpleNamespace:
    base = dict(
        clientes_created=0, touches_created=0, negociacoes_repointed=0,
        stragglers_parked_for_review=0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _FakeTable:
    """Minimal PostgREST chain returning canned `org_id` pages."""

    def __init__(self, pages: list[list[dict]]):
        self._pages = pages
        self.ranges: list[tuple[int, int]] = []

    def select(self, _cols):
        return self

    def range(self, start, end):
        self.ranges.append((start, end))
        idx = start // job._PAGE
        self._current = self._pages[idx] if idx < len(self._pages) else []
        return self

    def execute(self):
        return SimpleNamespace(data=self._current)


class _FakeAdmin:
    def __init__(self, tables: dict[str, _FakeTable]):
        self._tables = tables
        self.schemas_used: list[str] = []

    def schema(self, name):
        self.schemas_used.append(name)
        return self

    def table(self, name):
        return self._tables[name]


def _admin_with(leads: list[dict], meta: list[dict]) -> _FakeAdmin:
    return _FakeAdmin({
        "leads": _FakeTable([leads]),
        "meta_ads_leads": _FakeTable([meta]),
    })


# ── Guard clauses ─────────────────────────────────────────────────────────


class TestGuards:
    def test_disabled_setting_skips_without_touching_the_db(self):
        admin = MagicMock()
        out = job.run_clientes_backfill(cfg=_cfg(enabled=False), admin_client=admin)
        assert out == {"skipped": "disabled", "orgs": []}
        admin.schema.assert_not_called()

    def test_no_admin_client_skips(self):
        out = job.run_clientes_backfill(cfg=_cfg(), admin_factory=lambda: None)
        assert out == {"skipped": "no-admin-client", "orgs": []}

    def test_no_orgs_is_a_quiet_no_op(self):
        out = job.run_clientes_backfill(
            cfg=_cfg(), admin_client=_admin_with([], []),
        )
        assert out == {"skipped": None, "orgs": []}


# ── Org enumeration ───────────────────────────────────────────────────────


class TestOrgEnumeration:
    def test_dedupes_across_both_source_tables(self):
        seen: list[UUID] = []
        admin = _admin_with(
            [{"org_id": _ORG_A}, {"org_id": _ORG_A}, {"org_id": _ORG_B}],
            [{"org_id": _ORG_A}],
        )
        job.run_clientes_backfill(
            cfg=_cfg(), admin_client=admin,
            backfill_fn=lambda _c, org_id: seen.append(org_id) or _report(),
        )
        assert sorted(str(o) for o in seen) == [_ORG_A, _ORG_B]

    def test_pages_past_the_postgrest_row_cap(self):
        """PostgREST truncates at 1 000 rows and says nothing — an org whose
        only rows sit past the cap must still be swept."""
        page1 = [{"org_id": _ORG_A}] * job._PAGE
        page2 = [{"org_id": _ORG_B}]
        leads = _FakeTable([page1, page2])
        admin = _FakeAdmin({"leads": leads, "meta_ads_leads": _FakeTable([[]])})
        out = job.run_clientes_backfill(
            cfg=_cfg(), admin_client=admin, backfill_fn=lambda _c, _o: _report(),
        )
        assert {o["org_id"] for o in out["orgs"]} == {_ORG_A, _ORG_B}
        assert len(leads.ranges) == 2

    def test_ignores_rows_with_a_null_org_id(self):
        admin = _admin_with([{"org_id": None}, {"org_id": _ORG_A}], [])
        out = job.run_clientes_backfill(
            cfg=_cfg(), admin_client=admin, backfill_fn=lambda _c, _o: _report(),
        )
        assert [o["org_id"] for o in out["orgs"]] == [_ORG_A]


# ── Per-org isolation — the property the outage needed ────────────────────


class TestPerOrgIsolation:
    def test_one_org_failing_does_not_stop_the_next(self, caplog):
        def _flaky(_client, org_id):
            if str(org_id) == _ORG_A:
                raise RuntimeError("resolution blew up")
            return _report(touches_created=3)

        admin = _admin_with([{"org_id": _ORG_A}, {"org_id": _ORG_B}], [])
        with caplog.at_level(logging.ERROR):
            out = job.run_clientes_backfill(
                cfg=_cfg(), admin_client=admin, backfill_fn=_flaky,
            )

        by_org = {o["org_id"]: o for o in out["orgs"]}
        assert by_org[_ORG_A]["ok"] is False
        assert by_org[_ORG_B]["ok"] is True
        assert by_org[_ORG_B]["touches_created"] == 3
        # The failure is named in the log AND carried in the return value —
        # a swallowed per-org error leaving no trace is the silent-error
        # shape this module exists to close.
        assert _ORG_A in caplog.text

    def test_report_counts_are_surfaced_per_org(self):
        out = job.run_clientes_backfill(
            cfg=_cfg(), admin_client=_admin_with([{"org_id": _ORG_A}], []),
            backfill_fn=lambda _c, _o: _report(
                clientes_created=44, touches_created=88,
                negociacoes_repointed=88, stragglers_parked_for_review=2,
            ),
        )
        assert out["orgs"][0] == {
            "org_id": _ORG_A, "ok": True, "clientes_created": 44,
            "touches_created": 88, "negociacoes_repointed": 88,
            "stragglers_parked_for_review": 2,
        }

    def test_quiet_run_logs_nothing_at_info(self, caplog):
        """The healthy steady state is a no-op every 6h; it must not be noise."""
        with caplog.at_level(logging.INFO, logger=job.logger.name):
            job.run_clientes_backfill(
                cfg=_cfg(), admin_client=_admin_with([{"org_id": _ORG_A}], []),
                backfill_fn=lambda _c, _o: _report(),
            )
        assert "attached" not in caplog.text


# ── The wiring — what was actually missing ────────────────────────────────


class TestSchedulerWiring:
    def test_configure_registers_the_job(self):
        calls: list[tuple] = []

        class _FakeScheduler:
            def register(self, name, fn, **kw):
                calls.append((name, fn, kw))

        job.configure(cfg=_cfg(hours=6), scheduler=_FakeScheduler())
        assert len(calls) == 1
        name, fn, kw = calls[0]
        assert name == "clientes_backfill"
        assert fn is job._run_clientes_backfill_job
        assert kw == {"hours": 6}

    def test_job_wrapper_swallows_so_the_scheduler_survives(self, caplog):
        """A throwing run must not propagate — APScheduler would otherwise
        de-register the job and the drift would resume, silently, forever."""
        def _boom():
            raise RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            job._run_clientes_backfill_job(run_fn=_boom)  # must not raise
        assert "job run failed" in caplog.text

    def test_main_registers_it_alongside_the_sibling_jobs(self):
        """The whole outage was an unwired function. Assert the wiring exists
        in `app/main.py`, not just that `configure()` works when called."""
        from pathlib import Path
        main_src = (
            Path(__file__).resolve().parents[2] / "app" / "main.py"
        ).read_text()
        assert "clientes_backfill_job" in main_src
        assert "clientes_backfill_job.configure()" in main_src

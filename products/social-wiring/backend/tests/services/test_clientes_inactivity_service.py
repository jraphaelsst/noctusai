"""Tests for `clientes_inactivity_service.py` — D16, the 180-day rule.

Roadmap `project-history/roadmaps/lead-card-hub-2026-08.md` D16. `048`
shipped `clientes.ativo`/`inativo_em`/`arquivado_em` and a manual restore
path; nothing ever set `inativo_em` automatically. This file covers the
three things that make that gap dangerous if gotten wrong:

  1. The silence definition — `ultimo_contato_em`, never `updated_at`,
     and `GREATEST(ultimo_contato_em, reativado_em)` so a restore sticks.
  2. Idempotency + per-org isolation (mirrors
     `test_clientes_backfill_job.py`'s reasoning — the failure mode that
     matters most is "one bad org freezes every other tenant's board").
  3. The PostgREST 1 000-row cap on both the org-enumeration query and the
     active-clientes query — this sweep is exactly the code path that
     hits it at the live ~9 300-cliente scale.

Reactivation-on-touch (`_reactivate_if_inactive`) lives in
`clientes_service.py`, not here — see
`tests/services/test_clientes_service.py::TestReactivationOnTouch`.

Every collaborator arrives through a declared Class-B kwarg seam (`cfg`,
`admin_client`/`admin_factory`, `now`, `sweep_fn`), never via
`monkeypatch.setattr` on this module — see `test_clientes_backfill_job.py`'s
module docstring for the compliance finding that made this non-negotiable
in this product.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import clientes_inactivity_service as svc
from noctusai_lib.testing import MockSupabaseClient

ORG_A = "00000000-0000-4000-8000-0000000000a1"
ORG_B = "00000000-0000-4000-8000-0000000000b2"

_NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def _scoped_client() -> MockSupabaseClient:
    return MockSupabaseClient().schema("social_wiring")


class _AdminOverSchema:
    """`.schema(name)` returns the SAME pre-scoped `MockSupabaseClient`
    every call — mirrors production calling `admin.schema(...)` exactly
    once per run (see the module docstring's "client MUST ALREADY BE
    SCHEMA-SCOPED" section). Seeding through the returned instance BEFORE
    the run is what makes rows visible to `run_clientes_inactivity_sweep`."""

    def __init__(self, scoped_client: MockSupabaseClient):
        self._scoped = scoped_client

    def schema(self, name):
        assert name == "social_wiring"
        return self._scoped


def _cfg(*, enabled: bool = True, default_days: int = 180, hours: int = 6) -> SimpleNamespace:
    return SimpleNamespace(
        clientes_inactivity_sweep_enabled=enabled,
        clientes_inactivity_threshold_days_default=default_days,
        clientes_inactivity_sweep_interval_hours=hours,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _cliente(
    id_=None, *, org=ORG_A, ativo=True, ultimo=None, reativado=None,
    inativo=None, threshold_dias=None,
) -> dict:
    return {
        "id": id_ or str(uuid4()),
        "org_id": org,
        "ativo": ativo,
        "ultimo_contato_em": ultimo,
        "reativado_em": reativado,
        "inativo_em": inativo,
        "inativo_threshold_dias": threshold_dias,
    }


def _clientes(client) -> list[dict]:
    return client.table("clientes").select("*").execute().data


# ── threshold config (D16 — configurable in the UI) ───────────────────────


class TestThresholdConfig:
    def test_no_row_falls_back_to_default(self):
        client = _scoped_client()
        client.set_table_data("clientes_inactivity_config", [])
        resolved = svc.get_threshold_config(client, ORG_A, default_days=180)
        assert resolved == {"threshold_days": 180, "configured": False}
        assert svc.get_threshold_days(client, ORG_A, default_days=180) == 180

    def test_configured_row_wins_over_default(self):
        client = _scoped_client()
        svc.set_threshold_days(client, ORG_A, 45)
        resolved = svc.get_threshold_config(client, ORG_A, default_days=180)
        assert resolved == {"threshold_days": 45, "configured": True}
        assert svc.get_threshold_days(client, ORG_A, default_days=180) == 45

    def test_zero_is_a_valid_configured_value_distinct_from_unconfigured(self):
        """0 = explicitly disabled — a DIFFERENT state from 'no row at
        all' (falls back to the default). Collapsing them would make
        'reset to default' and 'turn off forever' indistinguishable."""
        client = _scoped_client()
        svc.set_threshold_days(client, ORG_A, 0)
        resolved = svc.get_threshold_config(client, ORG_A, default_days=180)
        assert resolved == {"threshold_days": 0, "configured": True}

    def test_negative_threshold_is_rejected(self):
        client = _scoped_client()
        with pytest.raises(ValueError):
            svc.set_threshold_days(client, ORG_A, -1)

    def test_set_is_scoped_per_org(self):
        client = _scoped_client()
        svc.set_threshold_days(client, ORG_A, 30)
        svc.set_threshold_days(client, ORG_B, 90)
        assert svc.get_threshold_days(client, ORG_A, default_days=180) == 30
        assert svc.get_threshold_days(client, ORG_B, default_days=180) == 90

    def test_re_setting_upserts_rather_than_duplicates(self):
        client = _scoped_client()
        svc.set_threshold_days(client, ORG_A, 30)
        svc.set_threshold_days(client, ORG_A, 60)
        rows = client.table("clientes_inactivity_config").select("*").eq(
            "org_id", ORG_A
        ).execute().data
        assert len(rows) == 1
        assert rows[0]["threshold_days"] == 60


# ── guard clauses ──────────────────────────────────────────────────────────


class TestGuards:
    def test_disabled_setting_skips_without_touching_the_db(self):
        class _ExplodingAdmin:
            def schema(self, _name):
                raise AssertionError("must not be called when disabled")

        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(enabled=False), admin_client=_ExplodingAdmin()
        )
        assert out == {"skipped": "disabled", "orgs": []}

    def test_no_admin_client_skips(self):
        out = svc.run_clientes_inactivity_sweep(cfg=_cfg(), admin_factory=lambda: None)
        assert out == {"skipped": "no-admin-client", "orgs": []}

    def test_no_orgs_is_a_quiet_no_op(self):
        client = _scoped_client()
        client.set_table_data("clientes", [])
        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client)
        )
        assert out == {"skipped": None, "orgs": []}


# ── the silence definition — the crux of this slice ────────────────────────


class TestSweepMarksInactive:
    def test_cliente_past_the_threshold_is_marked_inactive(self):
        client = _scoped_client()
        stale = _cliente(ultimo=_iso(_NOW - timedelta(days=200)))
        client.set_table_data("clientes", [stale])
        client.set_table_data("clientes_inactivity_config", [])

        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        assert out["orgs"] == [{
            "org_id": ORG_A, "ok": True, "skipped": None, "swept": 1,
            "threshold_days": 180, "candidates": 1, "skipped_no_signal": 0,
        }]
        [row] = _clientes(client)
        assert row["ativo"] is False
        assert row["inativo_em"] == _NOW.isoformat()
        assert row["inativo_threshold_dias"] == 180

    def test_cliente_inside_the_threshold_is_left_alone(self):
        """The test that must fail without the fix: a naive '> some fixed
        window' or an off-by-one on the boundary would wrongly sweep this
        row. Verified failing first by temporarily using `>` instead of
        `>=` for the cutoff comparison — see the delivery note."""
        client = _scoped_client()
        fresh = _cliente(ultimo=_iso(_NOW - timedelta(days=10)))
        client.set_table_data("clientes", [fresh])
        client.set_table_data("clientes_inactivity_config", [])

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [row] = _clientes(client)
        assert row["ativo"] is True
        assert row["inativo_em"] is None

    def test_exactly_at_the_boundary_is_not_yet_stale(self):
        """`last_activity == cutoff` must NOT be swept — 180 days of
        silence means silence for MORE than 180 days, not exactly 180."""
        client = _scoped_client()
        cutoff = _NOW - timedelta(days=180)
        boundary = _cliente(ultimo=_iso(cutoff))
        client.set_table_data("clientes", [boundary])
        client.set_table_data("clientes_inactivity_config", [])

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [row] = _clientes(client)
        assert row["ativo"] is True

    def test_org_configured_threshold_overrides_the_platform_default(self):
        client = _scoped_client()
        stale_for_45_not_180 = _cliente(ultimo=_iso(_NOW - timedelta(days=60)))
        client.set_table_data("clientes", [stale_for_45_not_180])
        svc.set_threshold_days(client, ORG_A, 45)

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(default_days=180), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [row] = _clientes(client)
        assert row["ativo"] is False
        assert row["inativo_threshold_dias"] == 45

    def test_zero_threshold_disables_the_sweep_for_that_org(self):
        client = _scoped_client()
        very_stale = _cliente(ultimo=_iso(_NOW - timedelta(days=900)))
        client.set_table_data("clientes", [very_stale])
        svc.set_threshold_days(client, ORG_A, 0)

        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        assert out["orgs"][0]["skipped"] == "disabled"
        [row] = _clientes(client)
        assert row["ativo"] is True  # untouched

    def test_already_inactive_clientes_are_never_candidates(self):
        client = _scoped_client()
        already = _cliente(ativo=False, inativo="2026-01-01T00:00:00+00:00")
        client.set_table_data("clientes", [already])
        client.set_table_data("clientes_inactivity_config", [])

        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        assert out["orgs"][0]["candidates"] == 0

    def test_no_last_activity_signal_is_skipped_not_guessed(self, caplog):
        """A cliente with no `ultimo_contato_em`/`reativado_em` at all
        should never happen in practice (every cliente is created WITH
        touches), but this must degrade to a named skip, never a silent
        guess — the no-silent-errors rule."""
        client = _scoped_client()
        blank = _cliente(ultimo=None, reativado=None)
        client.set_table_data("clientes", [blank])
        client.set_table_data("clientes_inactivity_config", [])

        with caplog.at_level(logging.WARNING):
            out = svc.run_clientes_inactivity_sweep(
                cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
            )
        assert out["orgs"][0]["skipped_no_signal"] == 1
        assert out["orgs"][0]["swept"] == 0
        assert "no ultimo_contato_em" in caplog.text
        [row] = _clientes(client)
        assert row["ativo"] is True


# ── idempotency ──────────────────────────────────────────────────────────


class TestIdempotency:
    def test_rerun_on_unchanged_data_does_not_restamp(self):
        client = _scoped_client()
        stale = _cliente(ultimo=_iso(_NOW - timedelta(days=200)))
        client.set_table_data("clientes", [stale])
        client.set_table_data("clientes_inactivity_config", [])

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [after_first] = _clientes(client)
        assert after_first["inativo_em"] == _NOW.isoformat()

        later = _NOW + timedelta(hours=6)
        second = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=later,
        )
        # already ativo=false -> not a candidate at all on the second pass
        assert second["orgs"][0]["candidates"] == 0
        [after_second] = _clientes(client)
        assert after_second["inativo_em"] == _NOW.isoformat()  # unchanged


# ── manual restore must win (D4) ────────────────────────────────────────


class TestManualRestoreWins:
    def test_a_restored_cliente_with_a_stale_touch_is_not_immediately_reswept(self):
        """The single most likely way to ship something infuriating: a
        human restores a cliente by hand
        (`PATCH /api/clientes/{id}` ativo=true, which sets `reativado_em`
        — see `clientes_router.py`), but their most recent REAL touch is
        still 200 days old. The very next scheduled tick must NOT sweep
        them straight back to inactive."""
        client = _scoped_client()
        restored = _cliente(
            ultimo=_iso(_NOW - timedelta(days=200)),
            reativado=_iso(_NOW - timedelta(days=1)),  # restored yesterday
        )
        client.set_table_data("clientes", [restored])
        client.set_table_data("clientes_inactivity_config", [])

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [row] = _clientes(client)
        assert row["ativo"] is True

    def test_a_restore_old_enough_to_exceed_the_threshold_is_swept_again(self):
        """Restore-wins is not permanent immunity — it resets the clock
        FROM the restore moment. 200 days after a restore with no new
        real touch, the cliente is legitimately silent again."""
        client = _scoped_client()
        old_restore = _cliente(
            ultimo=_iso(_NOW - timedelta(days=400)),
            reativado=_iso(_NOW - timedelta(days=200)),
        )
        client.set_table_data("clientes", [old_restore])
        client.set_table_data("clientes_inactivity_config", [])

        svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        [row] = _clientes(client)
        assert row["ativo"] is False


# ── per-org isolation ──────────────────────────────────────────────────────


class TestPerOrgIsolation:
    def test_one_org_failing_does_not_stop_the_next(self, caplog):
        client = _scoped_client()
        client.set_table_data(
            "clientes", [_cliente(org=ORG_A), _cliente(org=ORG_B)]
        )

        def _flaky(_client, org_id, _cfg, _moment):
            if str(org_id) == ORG_A:
                raise RuntimeError("boom")
            return {"skipped": None, "swept": 3, "threshold_days": 180, "candidates": 1}

        with caplog.at_level(logging.ERROR):
            out = svc.run_clientes_inactivity_sweep(
                cfg=_cfg(), admin_client=_AdminOverSchema(client),
                now=_NOW, sweep_fn=_flaky,
            )
        by_org = {o["org_id"]: o for o in out["orgs"]}
        assert by_org[ORG_A]["ok"] is False
        assert by_org[ORG_B]["ok"] is True
        assert by_org[ORG_B]["swept"] == 3
        assert ORG_A in caplog.text


# ── the PostgREST 1 000-row cap ─────────────────────────────────────────


class TestPostgrestRowCap:
    def test_org_enumeration_pages_past_the_cap(self):
        client = _scoped_client()
        many = [_cliente(org=ORG_A) for _ in range(1_200)]
        client.set_table_data("clientes", many)
        assert svc._list_org_ids(client) == [__import__("uuid").UUID(ORG_A)]

    def test_active_clientes_query_pages_past_the_cap(self):
        client = _scoped_client()
        many = [
            _cliente(ultimo=_iso(_NOW - timedelta(days=200))) for _ in range(1_200)
        ]
        client.set_table_data("clientes", many)
        client.set_table_data("clientes_inactivity_config", [])

        out = svc.run_clientes_inactivity_sweep(
            cfg=_cfg(), admin_client=_AdminOverSchema(client), now=_NOW,
        )
        assert out["orgs"][0]["candidates"] == 1_200
        assert out["orgs"][0]["swept"] == 1_200
        assert all(not row["ativo"] for row in _clientes(client))


# ── scheduler wiring ────────────────────────────────────────────────────


class TestSchedulerWiring:
    def test_configure_registers_the_job(self):
        calls: list[tuple] = []

        class _FakeScheduler:
            def register(self, name, fn, **kw):
                calls.append((name, fn, kw))

        svc.configure(cfg=_cfg(hours=6), scheduler=_FakeScheduler())
        assert len(calls) == 1
        name, fn, kw = calls[0]
        assert name == "clientes_inactivity_sweep"
        assert fn is svc._run_clientes_inactivity_job
        assert kw == {"hours": 6}

    def test_job_wrapper_swallows_so_the_scheduler_survives(self, caplog):
        def _boom():
            raise RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            svc._run_clientes_inactivity_job(run_fn=_boom)  # must not raise
        assert "job run failed" in caplog.text

    def test_main_registers_it_alongside_the_sibling_jobs(self):
        from pathlib import Path

        main_src = (
            Path(__file__).resolve().parents[2] / "app" / "main.py"
        ).read_text()
        assert "clientes_inactivity_service" in main_src
        assert "clientes_inactivity_service.configure()" in main_src

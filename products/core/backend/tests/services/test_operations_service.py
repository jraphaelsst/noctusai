"""Operação read side + the owner daily brief — on `MockSupabaseClient`,
with every external reader (LLM spend, fleet, e-mail) passed in as an
argument. Nothing of ours is patched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.scheduler_runs import ALERT_KIND
from noctusai_lib.testing import MockSupabaseClient

from app import scheduler as core_scheduler
from app.services import operations_service as ops
from app.services import owner_brief_service as brief

# 2026-10-29 10:00 UTC = 07:00 America/Sao_Paulo.
NOW = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG = "11111111-1111-1111-1111-111111111111"


def _ts(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


def _run(product, job, status, ago, error=None):
    started = NOW - ago
    return {
        "product": product, "job": job, "status": status, "error": error,
        "started_at": started.isoformat(), "finished_at": (started + timedelta(seconds=1)).isoformat(),
        "duration_ms": 1000, "alerted": False,
    }


@pytest.fixture
def db():
    client = MockSupabaseClient()
    client.set_table_data("products", [
        {"slug": "social-wiring", "ativo": True},
        {"slug": "erp-imobiliario", "ativo": False},
    ])
    client.set_table_data("noctus_users", [{"id": ADMIN, "role": "admin"}, {"id": "u-2", "role": "user"}])
    client.set_table_data("notifications", [])
    client.set_table_data("owner_briefs", [])
    client.set_table_data("organizations", [{"id": ORG, "nome": "Imobiliária X"}])
    client.set_table_data("cost_ledger", [
        {"org_id": ORG, "category": "openai_edit", "amount_brl": 12.5, "fx_pending": False,
         "created_at": _ts(-timedelta(hours=20))},
        {"org_id": ORG, "category": "openai_edit", "amount_brl": None, "fx_pending": True,
         "created_at": _ts(-timedelta(hours=19))},
    ])
    client.set_table_data("scheduler_jobs", [
        {"product": "social-wiring", "job": "sw_nightly", "cron": "0 3 * * *", "interval_seconds": None,
         "timezone": "America/Sao_Paulo", "misfire_grace_time": 3600, "last_seen_at": _ts(-timedelta(days=3))},
        {"product": "social-wiring", "job": "sw_tick", "cron": None, "interval_seconds": 300,
         "timezone": "America/Sao_Paulo", "misfire_grace_time": 30, "last_seen_at": _ts(-timedelta(days=3))},
        {"product": "social-wiring", "job": "sw_fine", "cron": None, "interval_seconds": 3600,
         "timezone": "America/Sao_Paulo", "misfire_grace_time": 30, "last_seen_at": _ts(-timedelta(days=3))},
        {"product": "erp-imobiliario", "job": "erp_sleepy", "cron": "0 3 * * *", "interval_seconds": None,
         "timezone": "America/Sao_Paulo", "misfire_grace_time": 30, "last_seen_at": _ts(-timedelta(days=40))},
    ])
    client.set_table_data("scheduler_runs", [
        # sw_nightly: no run at the 03:00 slot today -> missing.
        _run("social-wiring", "sw_tick", "error", timedelta(minutes=3), "RuntimeError: waha 502"),
        _run("social-wiring", "sw_fine", "ok", timedelta(minutes=20)),
    ])
    return client


def _llm(db, start, end):
    return {"source": "test", "per_product": [{"product": "social-wiring", "calls": 4, "cost_usd": 0.12}],
            "per_org": None, "total_usd": 0.12, "calls": 4}


def _fleet():
    return [
        {"slug": "core", "state": "running", "health": "healthy", "running": True},
        {"slug": "igig", "state": "exited", "health": "none", "running": False},
        {"slug": "old", "state": "absent", "health": "none", "running": False},
    ]


class TestOverdue:
    def test_last_expected_fire_finds_todays_slot(self):
        due = ops.last_expected_fire("0 3 * * *", "America/Sao_Paulo", NOW)
        assert due.astimezone(timezone.utc) == datetime(2026, 10, 29, 6, 0, tzinfo=timezone.utc)

    def test_a_weekly_cron_outside_its_slot_owes_nothing(self):
        assert ops.last_expected_fire("0 3 * * 0", "America/Sao_Paulo", NOW) is None  # 2026-10-29 is a Thursday

    def test_cron_with_a_run_after_the_slot_is_not_overdue(self):
        job = {"cron": "0 3 * * *", "timezone": "America/Sao_Paulo", "misfire_grace_time": 60}
        ran = datetime(2026, 10, 29, 6, 0, 2, tzinfo=timezone.utc)
        assert ops.overdue_since(job, ran, NOW) is None

    def test_cron_registered_after_the_slot_is_not_overdue(self):
        job = {"cron": "0 3 * * *", "timezone": "America/Sao_Paulo", "misfire_grace_time": 60,
               "last_seen_at": _ts(-timedelta(hours=1))}
        assert ops.overdue_since(job, None, NOW) is None

    def test_interval_overdue_after_one_interval_plus_allowance(self):
        job = {"interval_seconds": 300, "misfire_grace_time": 30}
        assert ops.overdue_since(job, NOW - timedelta(minutes=10), NOW) is None
        assert ops.overdue_since(job, NOW - timedelta(minutes=20), NOW) is not None


class TestRoutines:
    def test_failures_and_missing_runs_lead_and_asleep_products_are_not_flagged(self, db):
        data = ops.list_routines(db, NOW)
        products = {p["product"]: p for p in data["products"]}
        sw = products["social-wiring"]
        assert sw["active"] is True
        # failing/overdue first, then by error count (desc), then name.
        assert [j["job"] for j in sw["jobs"]] == ["sw_tick", "sw_nightly", "sw_fine"]
        jobs = {j["job"]: j for j in sw["jobs"]}
        assert jobs["sw_nightly"]["overdue"] is True
        assert jobs["sw_tick"]["last_run"]["status"] == "error"
        assert jobs["sw_tick"]["errors_24h"] == 1
        assert jobs["sw_fine"]["overdue"] is False
        assert sw["failing"] == 2
        erp = products["erp-imobiliario"]
        assert erp["active"] is False and erp["jobs"][0]["overdue"] is False
        assert data["totals"]["overdue"] == 1

    def test_brief_deadman_flags_a_missing_brief(self, db):
        assert ops.brief_status(db, NOW)["missing"] is True
        db.set_table_data("scheduler_runs", [_run("core", ops.BRIEF_JOB, "ok", timedelta(hours=25))])
        assert ops.brief_status(db, NOW)["missing"] is False
        db.set_table_data("scheduler_runs", [_run("core", ops.BRIEF_JOB, "ok", timedelta(hours=27))])
        assert ops.brief_status(db, NOW)["missing"] is True

    def test_runs_filter(self, db):
        rows = ops.list_runs(db, product="social-wiring", status="error")
        assert [r["job"] for r in rows] == ["sw_tick"]


def test_model_catalog_is_the_seed_catalog():
    models = ops.model_catalog()
    assert any(m["id"] == "gpt-4o-mini" and m["provider"] == "openai" for m in models)
    assert all({"priced", "kind", "label"} <= set(m) for m in models)


def test_costs_summary_reads_the_ledger_and_the_llm_source(db):
    data = ops.costs_summary(db, NOW, llm_source=_llm)
    assert data["llm_yesterday"]["available"] is True
    assert data["llm_yesterday"]["total_usd"] == 0.12
    [org] = data["cost_ledger_yesterday"]["per_org"]
    assert org["org_name"] == "Imobiliária X"
    assert org["amount_brl"] == 12.5 and org["pending_fx"] == 1


def test_a_failing_llm_source_is_reported_not_swallowed(db):
    def broken(db, start, end):
        raise TypeError("signature changed")

    data = ops.costs_summary(db, NOW, llm_source=broken)
    assert data["llm_yesterday"]["available"] is False
    assert "signature changed" in data["llm_yesterday"]["error"]


class TestOwnerBrief:
    def test_compose_lists_every_exception(self, db):
        payload = brief.compose_brief(db, NOW, llm_source=_llm, fleet_source=_fleet, build_sha="abc1234")
        assert [f["job"] for f in payload["scheduler"]["failed"]] == ["sw_tick"]
        assert [m["job"] for m in payload["scheduler"]["missing"]] == ["sw_nightly"]
        assert [p["slug"] for p in payload["fleet"]["problems"]] == ["igig"]
        assert payload["deploy"]["core_build_sha"] == "abc1234"
        assert payload["exceptions_count"] == 3
        text = brief.render_text(payload)
        assert "FALHOU · social-wiring / sw_tick" in text
        assert "FALTANDO · social-wiring / sw_nightly" in text
        assert "US$ 0.12" in text
        assert "R$ 12,50" in text
        assert "<script>" not in brief.render_html({**payload, "deploy": {"core_build_sha": "<script>"}})

    def test_an_unavailable_fleet_is_an_exception_not_a_green(self, db):
        def no_docker():
            raise RuntimeError("docker socket indisponível")

        payload = brief.compose_brief(db, NOW, llm_source=_llm, fleet_source=no_docker, build_sha="x")
        assert payload["fleet"]["available"] is False
        assert "indisponível" in brief.render_text(payload)

    def test_run_delivers_in_app_and_email_and_stores_the_brief(self, db):
        sent = []

        def sender(to, subject, html):
            sent.append((to, subject))
            return True

        result = brief.run_owner_brief(db, NOW, llm_source=_llm, fleet_source=_fleet,
                                       email_sender=sender, owner_email="owner@noctus.test", build_sha="x")
        assert result.email_status == "sent" and result.in_app_sent == 1
        assert sent[0][0] == "owner@noctus.test" and "Brief diário" in sent[0][1]
        [note] = db.table("notifications").inserted_payloads
        assert note["user_id"] == ADMIN and note["metadata"]["tipo"] == brief.BRIEF_KIND
        assert note["metadata"]["tipo"] != ALERT_KIND
        [row] = db.table("owner_briefs").inserted_payloads
        assert row["exceptions_count"] == 3 and row["email_status"] == "sent"

    def test_no_owner_address_is_recorded_as_not_configured(self, db):
        result = brief.run_owner_brief(db, NOW, llm_source=_llm, fleet_source=_fleet,
                                       email_sender=lambda *a: True, owner_email="", build_sha="x")
        assert result.email_status == "not_configured"

    def test_a_failed_send_is_recorded(self, db):
        result = brief.run_owner_brief(db, NOW, llm_source=_llm, fleet_source=_fleet,
                                       email_sender=lambda *a: False, owner_email="o@x.test", build_sha="x")
        assert result.email_status == "failed"

    def test_preview_does_not_deliver(self, db):
        result = brief.run_owner_brief(db, NOW, deliver=False, llm_source=_llm, fleet_source=_fleet, build_sha="x")
        assert result.email_status == "not_sent" and result.in_app_sent == 0
        assert db.table("notifications").inserted_payloads == []
        assert len(db.table("owner_briefs").inserted_payloads) == 1


class TestCoreJobs:
    def test_brief_and_retention_jobs_are_registered(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        seed_scheduler.reset_for_testing()
        try:
            core_scheduler.configure()
            ids = {j.id for j in seed_scheduler.scheduler.get_jobs()}
            assert {core_scheduler.OWNER_BRIEF_JOB, core_scheduler.RUNS_RETENTION_JOB} <= ids
            spec = {s.job: s for s in seed_scheduler.job_specs()}[core_scheduler.OWNER_BRIEF_JOB]
            assert spec.cron == "0 7 * * *"
        finally:
            seed_scheduler.reset_for_testing()

    @pytest.mark.asyncio
    async def test_retention_trims_old_rows_only(self, db):
        db.set_table_data("scheduler_runs", [
            {**_run("p", "a", "ok", timedelta(days=20)), "id": 1},
            {**_run("p", "a", "ok", timedelta(days=2)), "id": 2},
            {**_run("p", "a", "error", timedelta(days=30)), "id": 3},
            {**_run("p", "a", "error", timedelta(days=100)), "id": 4},
        ])
        await core_scheduler.scheduler_runs_retention_job(db)
        left = sorted(r["id"] for r in db.table("scheduler_runs").select("*").execute().data)
        assert left == [2, 3]

"""Core's background jobs on the seed scheduler primitive.

No patching of our own code: job bodies take their dependencies as
arguments (a Mock DB / a `BillingContext` of Fakes), and the start guard
is exercised through the real environment variable it reads.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.testing import MockSupabaseClient

from app import scheduler as core_scheduler
from tests.billing_fakes import NOW, make_ctx, managed_subscription, seed_catalog

JOB_IDS = {
    core_scheduler.WEBHOOK_RETENTION_JOB,
    core_scheduler.AUDIT_LOG_RETENTION_JOB,
    core_scheduler.BILLING_AUTOMATIONS_JOB,
    core_scheduler.PTAX_JOB,
    core_scheduler.STORAGE_SNAPSHOT_JOB,
}


@pytest.fixture
def fresh_scheduler():
    seed_scheduler.reset_for_testing()
    yield seed_scheduler
    seed_scheduler.reset_for_testing()


def test_configure_registers_every_core_job(fresh_scheduler):
    core_scheduler.configure()
    registered = {job.id for job in fresh_scheduler.scheduler.get_jobs()}
    assert JOB_IDS <= registered


def test_configure_is_idempotent(fresh_scheduler):
    core_scheduler.configure()
    core_scheduler.configure()
    ids = [job.id for job in fresh_scheduler.scheduler.get_jobs()]
    assert sorted(ids) == sorted(set(ids))


def test_scheduler_refuses_to_start_without_the_deploy_marker(fresh_scheduler, monkeypatch):
    # The env var is the guard's input, not our code — setting it is the
    # honest way to drive the guard.
    monkeypatch.delenv(seed_scheduler.SCHEDULERS_ENABLED_ENV, raising=False)
    core_scheduler.configure()
    core_scheduler.start_scheduler()
    assert not fresh_scheduler.scheduler.running


@pytest.mark.asyncio
async def test_scheduler_starts_with_the_deploy_marker(fresh_scheduler, monkeypatch):
    monkeypatch.setenv(seed_scheduler.SCHEDULERS_ENABLED_ENV, "1")
    core_scheduler.configure()
    try:
        core_scheduler.start_scheduler()
        assert fresh_scheduler.scheduler.running
        core_scheduler.start_scheduler()  # idempotent
        assert fresh_scheduler.scheduler.running
    finally:
        core_scheduler.stop_scheduler()


def test_stop_is_safe_when_not_running(fresh_scheduler):
    core_scheduler.stop_scheduler()
    assert not fresh_scheduler.scheduler.running


@pytest.mark.asyncio
async def test_retention_job_purges_expired_rows():
    db = MockSupabaseClient()
    db.set_table_data(
        "webhook_deliveries",
        [
            {"id": "d-old", "retention_until": "2000-01-01T00:00:00+00:00"},
            {"id": "d-new", "retention_until": "2999-01-01T00:00:00+00:00"},
        ],
    )
    result = await core_scheduler.webhook_retention_sweep_job(db)
    assert result == {"purged": 1}
    remaining = db.table("webhook_deliveries").select("id").execute().data
    assert [r["id"] for r in remaining] == ["d-new"]


class _BrokenDb:
    def table(self, name):
        raise RuntimeError("DB down")

    def rpc(self, name, params=None):
        raise RuntimeError("DB down")


@pytest.mark.asyncio
async def test_retention_job_reports_errors_instead_of_raising(caplog):
    result = await core_scheduler.webhook_retention_sweep_job(_BrokenDb())
    assert result == {"error": "DB down"}
    assert "DB down" in caplog.text


@pytest.mark.asyncio
async def test_audit_log_retention_job_calls_the_purge_rpc_and_reports_count():
    db = MockSupabaseClient()
    db.set_rpc_data("purge_expired_audit_logs", 4)
    result = await core_scheduler.audit_log_retention_sweep_job(db)
    assert result == {"purged": 4}


@pytest.mark.asyncio
async def test_audit_log_retention_job_reports_errors_instead_of_raising(caplog):
    result = await core_scheduler.audit_log_retention_sweep_job(_BrokenDb())
    assert result == {"error": "DB down"}
    assert "DB down" in caplog.text


@pytest.mark.asyncio
async def test_billing_job_does_nothing_while_switched_off():
    ctx, fakes = make_ctx(automations=False)
    seed_catalog(fakes.db)
    fakes.db.set_table_data("subscriptions", [managed_subscription(status="past_due", past_due_since=NOW.isoformat())])
    reports = await core_scheduler.billing_automations_job(ctx)
    assert reports and all(r["skipped"] for r in reports)
    assert fakes.db.table("subscriptions").updated_payloads == []


@pytest.mark.asyncio
async def test_ptax_job_stores_the_bulletin_and_prices_pending_rows():
    ctx, fakes = make_ctx(ptax={date(2026, 9, 16): Decimal("5.20000")})
    fakes.db.set_table_data("fx_rates", [])
    fakes.db.set_table_data(
        "cost_ledger",
        [{"id": 1, "org_id": "o", "category": "openai_edit", "amount_native": "2.000000",
          "currency": "USD", "fx_pending": True, "created_at": NOW.isoformat()}],
    )
    fakes.db.set_table_data("billing_payments", [])
    result = await core_scheduler.ptax_job(ctx)
    assert result["stored_quote_date"] == "2026-09-16"
    assert result["resolved_cost_rows"] == 1
    row = fakes.db.table("cost_ledger").select("*").execute().data[0]
    assert row["fx_pending"] is False
    assert Decimal(row["amount_brl"]) == Decimal("10.400000")
    assert row["fx_quote_date"] == "2026-09-16"

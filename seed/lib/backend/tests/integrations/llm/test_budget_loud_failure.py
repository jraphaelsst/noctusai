"""The monthly budget guard is LOUD on a failed lookup (2026-11-09) — it used to fail open silently.

Policy under test (`budget` module docstring): one bounded retry; then the FRESH last-known verdict of the org
(announced: ERROR + admin bell); none fresh ⇒ `LLMBudgetUnverifiable` (503) unless
`LLM_BUDGET_UNKNOWN_POLICY=allow`. "No budget row" (a successful empty read) stays unlimited.
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.llm import budget
from noctusai_lib.integrations.llm.exceptions import LLMBudgetExceeded, LLMBudgetUnverifiable


class _Db:
    """Admin-client fake. `fail` toggles every read to raise; `fail_times` fails the first N org_settings reads."""

    def __init__(self, *, budget_value: str | None, spent_usd: float = 0.0) -> None:
        self.budget_value = budget_value
        self.spent_usd = spent_usd
        self.fail = False
        self.fail_times = 0
        self.ledger_fail = False
        self.settings_reads = 0
        self.notifications: list[Any] = []

    def __call__(self) -> Any:
        sb = MagicMock()
        outer = self

        def table(name: str) -> Any:
            t = MagicMock()
            for m in ("select", "eq", "limit", "gte", "lte", "order"):
                getattr(t, m).return_value = t
            if name == "org_settings":
                def run():
                    outer.settings_reads += 1
                    if outer.fail or outer.fail_times > 0:
                        outer.fail_times = max(0, outer.fail_times - 1)
                        raise RuntimeError("connection reset")
                    return MagicMock(data=[{"value": outer.budget_value}] if outer.budget_value is not None else [])
                t.execute.side_effect = run
            elif name == "credit_wallets":
                t.execute.return_value = MagicMock(data=[])
            elif name == "noctus_users":
                t.execute.return_value = MagicMock(data=[{"id": "00000000-0000-0000-0000-000000000001"}])
            elif name == "notifications":
                t.insert.side_effect = lambda rows: (outer.notifications.extend(rows), t)[1]
                t.execute.return_value = MagicMock(data=[])
            else:  # ai_usage
                def rng(a, b):
                    if outer.fail or outer.ledger_fail:
                        t.execute.side_effect = RuntimeError("ledger down")
                    else:
                        t.execute.return_value = MagicMock(
                            data=[{"id": "1", "cost_usd": outer.spent_usd, "cost_brl": outer.spent_usd * 5}][a:b + 1]
                        )
                    return t
                t.range.side_effect = rng
            return t

        sb.schema.side_effect = lambda _n: MagicMock(table=table)
        return sb


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    budget.configure_budget_module(admin_client_factory=None)
    budget._reset_credit_state_for_tests()
    monkeypatch.setenv("LLM_BUDGET_RETRY_DELAY_S", "0")
    for k in ("LLM_BUDGET_UNKNOWN_POLICY", "LLM_BUDGET_LKG_MAX_AGE_S"):
        monkeypatch.delenv(k, raising=False)
    yield
    budget.configure_budget_module(admin_client_factory=None)


@pytest.mark.asyncio
async def test_unknown_budget_is_refused_loudly_not_failed_open(caplog):
    db = _Db(budget_value="100")
    db.fail = True
    budget.configure_budget_module(admin_client_factory=db)
    # the org is known as non-prepaid (so the credits leg does not refuse first)
    budget._credit_last_mode["org-1"] = None
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMBudgetUnverifiable) as exc:
            await budget.enforce_budget("org-1")
    assert exc.value.status_code == 503
    assert any("llm.budget.degraded" in r.getMessage() and r.levelname == "ERROR" for r in caplog.records)
    assert db.notifications, "the platform admins are told (bell), not just the log"


@pytest.mark.asyncio
async def test_one_blip_is_absorbed_by_the_bounded_retry(caplog):
    db = _Db(budget_value="100")
    db.fail_times = 1
    budget.configure_budget_module(admin_client_factory=db)
    budget._credit_last_mode["org-1"] = None
    await budget.enforce_budget("org-1")  # no raise
    assert db.settings_reads == 2
    assert not db.notifications


@pytest.mark.asyncio
async def test_fresh_last_known_verdict_keeps_live_traffic_flowing_but_announces_it(caplog):
    db = _Db(budget_value="100", spent_usd=1.0)
    budget.configure_budget_module(admin_client_factory=db)
    await budget.enforce_budget("org-1")  # healthy: seeds the last-known status
    db.fail = True
    with caplog.at_level(logging.ERROR):
        await budget.enforce_budget("org-1")  # blip: served on the last-known ok, loudly
    assert any("decision=last_known" in r.getMessage() for r in caplog.records)
    assert db.notifications


@pytest.mark.asyncio
async def test_last_known_hard_stop_still_refuses_during_a_blip():
    db = _Db(budget_value="100", spent_usd=50.0)  # 250 BRL spent of 100
    budget.configure_budget_module(admin_client_factory=db)
    with pytest.raises(LLMBudgetExceeded):
        await budget.enforce_budget("org-1")
    db.fail = True
    with pytest.raises(LLMBudgetExceeded):
        await budget.enforce_budget("org-1")


@pytest.mark.asyncio
async def test_stale_last_known_is_not_served(monkeypatch):
    db = _Db(budget_value="100", spent_usd=1.0)
    t = [1000.0]
    budget._reset_credit_state_for_tests(clock=lambda: t[0])
    budget.configure_budget_module(admin_client_factory=db)
    monkeypatch.setenv("LLM_BUDGET_LKG_MAX_AGE_S", "60")
    await budget.enforce_budget("org-1")
    db.fail = True
    t[0] += 61
    with pytest.raises(LLMBudgetUnverifiable):
        await budget.enforce_budget("org-1")


@pytest.mark.asyncio
async def test_explicit_allow_policy_is_still_loud(monkeypatch, caplog):
    monkeypatch.setenv("LLM_BUDGET_UNKNOWN_POLICY", "allow")
    db = _Db(budget_value="100")
    db.fail = True
    budget.configure_budget_module(admin_client_factory=db)
    budget._credit_last_mode["org-1"] = None
    with caplog.at_level(logging.ERROR):
        await budget.enforce_budget("org-1")
    assert any("allowed_by_policy" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_no_budget_row_is_still_unlimited_and_silent(caplog):
    db = _Db(budget_value=None)
    budget.configure_budget_module(admin_client_factory=db)
    with caplog.at_level(logging.ERROR):
        await budget.enforce_budget("org-1")
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.asyncio
async def test_ledger_read_failure_is_not_spent_zero():
    db = _Db(budget_value="100", spent_usd=1.0)
    db.ledger_fail = True
    budget.configure_budget_module(admin_client_factory=db)
    budget._credit_last_mode["org-1"] = None
    # budget readable, ledger down => this used to be `spent=0` (open); now degraded -> refused (no last-known)
    with pytest.raises(LLMBudgetUnverifiable):
        await budget.enforce_budget("org-1")

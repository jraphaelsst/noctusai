"""The configured budget is read once per TTL, not once per LLM call (2026-11-09 egress incident:
~1.9k `org_settings monthly_llm_budget_brl` reads in 22 h). Counts reads; correctness alone cannot see it."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.llm import budget


class _Db:
    def __init__(self, value: str | None) -> None:
        self.value = value
        self.reads = 0
        self.fail = False

    def __call__(self) -> Any:
        outer = self
        sb = MagicMock()
        t = MagicMock()
        for m in ("select", "eq", "limit"):
            getattr(t, m).return_value = t

        def run():
            outer.reads += 1
            if outer.fail:
                raise RuntimeError("connection reset")
            return MagicMock(data=[{"value": outer.value}] if outer.value is not None else [])

        t.execute.side_effect = run
        sb.schema.return_value.table.return_value = t
        return sb


@pytest.fixture
def db():
    d = _Db("100")
    budget.configure_budget_module(admin_client_factory=d)
    yield d
    budget.configure_budget_module(admin_client_factory=None)


@pytest.mark.asyncio
async def test_500_llm_calls_read_the_budget_once(db):
    for _ in range(500):
        assert await budget.fetch_budget_brl("org-1") == 100.0
    assert db.reads == 1


@pytest.mark.asyncio
async def test_unset_is_cached_too_and_a_write_invalidates(db):
    db.value = None
    assert await budget.fetch_budget_brl("org-1") is None
    assert await budget.fetch_budget_brl("org-1") is None
    assert db.reads == 1
    db.value = "50"
    budget.invalidate_budget_cache("org-1")
    assert await budget.fetch_budget_brl("org-1") == 50.0


@pytest.mark.asyncio
async def test_a_failed_read_is_never_cached(db):
    db.fail = True
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await budget.fetch_budget_brl("org-1")
    assert db.reads == 2
    db.fail = False
    assert await budget.fetch_budget_brl("org-1") == 100.0

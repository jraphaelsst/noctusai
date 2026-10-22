"""`compute_spend_usd` counts every usage row, not the first 1 000.

PostgREST caps each response at 1 000 rows regardless of `.limit()`; the old
`.limit(50_000)` read silently under-counted a busy month, so the budget gate
could let spend run past the hard stop. KB § PATTERNS/backend/postgrest-row-cap.md
"""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.llm import budget

_CAP = 1000


class _Query:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._range: tuple[int, int] | None = None
        self.ordered = False

    def table(self, _name):
        return self

    def select(self, _cols):
        return self

    def eq(self, *_a):
        return self

    def gte(self, *_a):
        return self

    def lte(self, *_a):
        return self

    def order(self, _col):
        self.ordered = True
        return self

    def limit(self, _n):  # accepted and ignored past the cap, like PostgREST
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        start, end = self._range if self._range else (0, len(self._rows) - 1)
        page = self._rows[start : end + 1][:_CAP]  # the server-side cap
        return type("R", (), {"data": page})()


class _Client:
    """One schema holds 2 500 rows of 0.01 USD; the others are empty."""

    def __init__(self):
        self.rows = {
            "social_wiring": [{"id": f"{i:06d}", "cost_estimate_usd": 0.01} for i in range(2500)],
        }

    def schema(self, name):
        return _Query(self.rows.get(name, []))


@pytest.fixture
def client():
    c = _Client()
    budget.configure_budget_module(admin_client_factory=lambda: c)
    yield c
    budget.configure_budget_module(admin_client_factory=None)


def test_spend_counts_rows_past_the_postgrest_cap(client):
    total = asyncio.run(budget.compute_spend_usd("org-1", start_iso="2026-10-01", end_iso="2026-10-31"))
    assert total == pytest.approx(25.0)  # 2 500 × 0.01, not the capped 10.0

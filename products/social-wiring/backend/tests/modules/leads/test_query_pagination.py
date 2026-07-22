"""Regression tests for the PostgREST 1000-row cap in ``fetch_filtered``.

Why these use a bespoke double instead of ``MockSupabaseClient``
────────────────────────────────────────────────────────────────
``noctusai_lib.testing.mocks``' request builder implements ``.range()``
as a no-op that returns ``self`` (it ignores the bounds and always
replays the full stored table). That is exactly why the original bug was
invisible to the suite: against the mock a single unbounded
``.select().execute()`` and a correct paging loop produce IDENTICAL
results, so no fixture could distinguish them.

The double below HONOURS ``range(start, end)`` the way PostgREST does —
returning at most the requested slice — which is the only way to
actually exercise the pager. Bug observed live 2026-07-22: the summary
endpoint reported ``total=1000`` against 12,177 real rows.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.leads.services.query import (
    LeadFilters,
    LeadsResultTooLargeError,
    fetch_filtered,
)

ORG_ID = uuid.UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")


class _RangeHonouringBuilder:
    """Minimal PostgREST-like builder: applies eq filters, then slices."""

    def __init__(self, rows: list[dict], cap: int) -> None:
        self._rows = rows
        self._cap = cap
        self._start = 0
        self._end: int | None = None

    # -- filter surface used by apply_db_filters / fetch_filtered --------
    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
        return self

    def in_(self, col, vals):
        wanted = {str(v) for v in vals}
        self._rows = [r for r in self._rows if str(r.get(col)) in wanted]
        return self

    def gte(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) >= str(val)]
        return self

    def lte(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) <= str(val)]
        return self

    def or_(self, *_a, **_k):
        return self

    def order(self, col, *_a, **_k):
        self._rows = sorted(self._rows, key=lambda r: str(r.get(col)))
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def execute(self):
        end = len(self._rows) - 1 if self._end is None else self._end
        window = self._rows[self._start : end + 1]
        # PostgREST never returns more than db-max-rows in one response.
        return type("Resp", (), {"data": window[: self._cap]})()


class _FakeClient:
    def __init__(self, rows: list[dict], cap: int = 1000) -> None:
        self._rows = rows
        self._cap = cap

    def table(self, _name):
        return _RangeHonouringBuilder(list(self._rows), self._cap)


def _make_rows(n: int, org_id: uuid.UUID = ORG_ID) -> list[dict]:
    return [
        {
            "id": f"{i:08d}-0000-0000-0000-000000000000",
            "org_id": str(org_id),
            "data_entrada": "2026-01-15",
            "cliente_nome": f"Cliente {i}",
            "origem_raw": "ZAP",
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("total", [0, 1, 999, 1000, 1001, 2500, 12177])
def test_fetch_filtered_returns_every_row_past_the_1000_cap(total):
    """The whole point: a result larger than one PostgREST page must come
    back COMPLETE, not silently truncated at the cap."""
    client = _FakeClient(_make_rows(total))
    rows = fetch_filtered(client, ORG_ID, LeadFilters())
    assert len(rows) == total


def test_single_unbounded_select_would_have_been_capped():
    """Guards the guard: proves the double really does enforce the cap, so
    a regression back to an unpaged select FAILS the test above instead of
    passing by accident."""
    client = _FakeClient(_make_rows(12177))
    capped = client.table("leads").select("*").execute().data
    assert len(capped) == 1000


def test_rows_are_unique_across_pages():
    """A pager without a stable sort can repeat or drop rows at page
    boundaries — assert the union is exactly the source set."""
    client = _FakeClient(_make_rows(3210))
    rows = fetch_filtered(client, ORG_ID, LeadFilters())
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) == 3210


def test_org_scoping_still_applies_while_paging():
    other = uuid.UUID("11111111-2222-3333-4444-555555555555")
    client = _FakeClient(_make_rows(1500) + _make_rows(1500, org_id=other))
    rows = fetch_filtered(client, ORG_ID, LeadFilters())
    assert len(rows) == 1500
    assert {r["org_id"] for r in rows} == {str(ORG_ID)}


def test_runaway_pager_raises_instead_of_looping_or_truncating():
    """A client whose `.range()` is a no-op (exactly what the shared mock
    does) must blow up loudly rather than spin forever or return a
    plausible-but-wrong set."""

    class _IgnoresRange(_FakeClient):
        def table(self, _name):
            builder = _RangeHonouringBuilder(list(self._rows), self._cap)
            builder.range = lambda *_a, **_k: builder  # type: ignore[assignment]
            return builder

    client = _IgnoresRange(_make_rows(1000))
    with pytest.raises(LeadsResultTooLargeError):
        fetch_filtered(client, ORG_ID, LeadFilters())

"""Regression tests for `query.iter_leads_rows` — the shared pager every
`dimensions_service` unmapped/relink/reassign function and
`import_service`'s existing-row lookups now route through instead of a
bare `.select().execute()` (each of those was independently capped at
PostgREST's 1000-row response limit with no truncation signal — see
`query.py`'s header comment for the incident this class of bug caused).

Same reasoning as `test_query_pagination.py` (which covers the sibling
`fetch_filtered` primitive): `noctusai_lib.testing.mocks`' request
builder treats `.range()` as a no-op that replays the full stored table,
so a correct pager and a naive unbounded select are indistinguishable
against it. The double below actually enforces the cap.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.leads.services.query import LeadsResultTooLargeError, iter_leads_rows

ORG_ID = uuid.UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")


class _RangeHonouringBuilder:
    """Minimal PostgREST-like builder: applies eq filters, then slices,
    capping at ``cap`` per response — same shape as
    ``test_query_pagination.py``'s double."""

    def __init__(self, rows: list[dict], cap: int) -> None:
        self._rows = rows
        self._cap = cap
        self._start = 0
        self._end: int | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
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
        return type("Resp", (), {"data": window[: self._cap]})()


class _FakeClient:
    def __init__(self, rows: list[dict], cap: int = 1000) -> None:
        self._rows = rows
        self._cap = cap

    def table(self, _name):
        return _RangeHonouringBuilder(list(self._rows), self._cap)


def _make_rows(n: int, org_id: uuid.UUID = ORG_ID, **extra) -> list[dict]:
    return [
        {
            "id": f"{i:08d}-0000-0000-0000-000000000000",
            "org_id": str(org_id),
            "origem_raw": "SOME BRAND NEW SPELLING",
            **extra,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("total", [0, 1, 999, 1000, 1001, 2500])
def test_iter_leads_rows_returns_every_row_past_the_1000_cap(total):
    client = _FakeClient(_make_rows(total))
    rows = iter_leads_rows(client, ORG_ID, "id, origem_raw")
    assert len(rows) == total


def test_single_unbounded_select_would_have_been_capped():
    """Guards the guard — proves the double really enforces the cap."""
    client = _FakeClient(_make_rows(2500))
    capped = client.table("leads").select("*").execute().data
    assert len(capped) == 1000


def test_extra_eq_filter_is_applied_across_pages():
    rows = _make_rows(1500, source_sheet="JULHO_26") + _make_rows(
        1500, org_id=ORG_ID, source_sheet="JULHO_24"
    )
    client = _FakeClient(rows)
    result = iter_leads_rows(client, ORG_ID, "id, source_sheet", source_sheet="JULHO_26")
    assert len(result) == 1500
    assert {r["source_sheet"] for r in result} == {"JULHO_26"}


def test_org_scoping_still_applies_while_paging():
    other = uuid.UUID("11111111-2222-3333-4444-555555555555")
    client = _FakeClient(_make_rows(1200) + _make_rows(1200, org_id=other))
    rows = iter_leads_rows(client, ORG_ID, "id")
    assert len(rows) == 1200
    assert {r["org_id"] for r in rows} == {str(ORG_ID)}


def test_runaway_pager_raises_instead_of_looping_or_truncating():
    class _IgnoresRange(_FakeClient):
        def table(self, _name):
            builder = _RangeHonouringBuilder(list(self._rows), self._cap)
            builder.range = lambda *_a, **_k: builder  # type: ignore[assignment]
            return builder

    client = _IgnoresRange(_make_rows(1000))
    with pytest.raises(LeadsResultTooLargeError):
        iter_leads_rows(client, ORG_ID, "id")

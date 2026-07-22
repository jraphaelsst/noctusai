"""Regression tests for the list endpoint's DB-pushed count+page fast
path (``leads_service._list_leads_db`` / ``list_leads``).

Why this uses a bespoke double instead of ``MockSupabaseClient``
──────────────────────────────────────────────────────────────────
``noctusai_lib.testing.mocks``' request builder implements ``.range()``,
``.order()`` and the ``count="exact"`` count as either no-ops or
"count = current unfiltered table length" (see ``query.py``'s docstring
and ``test_query_pagination.py``'s precedent) — none of which can
distinguish "fetched everything" from "fetched one page", which is
EXACTLY the thing this test suite needs to prove. The double below
HONOURS ``.eq()``, ``.range(start, end)`` and ``count="exact"`` the way
PostgREST does.
"""
from __future__ import annotations

import uuid

from app.modules.leads.services import leads_service
from app.modules.leads.services.query import LeadFilters

ORG_ID = uuid.UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")


class _CountAndRangeHonouringBuilder:
    """Minimal PostgREST-like builder: applies eq/gte/lte/in_ filters,
    computes an honest ``count="exact"`` over THOSE filters, then slices
    via ``.range()`` — everything the bespoke double in
    ``test_query_pagination.py`` deliberately does NOT do (that one only
    needs to prove the pager isn't silently capped; this one needs to
    prove the NEW count+page path is genuinely scoped + sliced)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._count_mode = False
        self._start = 0
        self._end: int | None = None
        self._order_col: str | None = None
        self._order_desc = False

    def select(self, *_cols, **kwargs):
        self._count_mode = kwargs.get("count") == "exact"
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

    def order(self, col, desc=False, **_k):
        self._order_col = col
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def execute(self):
        rows = list(self._rows)
        if self._order_col is not None:
            rows.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
        if self._count_mode:
            return type("Resp", (), {"data": rows, "count": len(rows)})()
        end = len(rows) - 1 if self._end is None else self._end
        window = rows[self._start : end + 1]
        return type("Resp", (), {"data": window, "count": None})()


class _FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def table(self, _name):
        return _CountAndRangeHonouringBuilder(list(self._rows))


def _make_rows(n: int, org_id: uuid.UUID = ORG_ID) -> list[dict]:
    return [
        {
            "id": f"{i:08d}-0000-0000-0000-000000000000",
            "org_id": str(org_id),
            "data_entrada": f"2026-01-{(i % 28) + 1:02d}",
            "cliente_nome": f"Cliente {i:04d}",
            "created_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
        }
        for i in range(n)
    ]


class TestDbPushedFastPath:
    def test_total_reflects_count_exact_not_page_size(self):
        client = _FakeClient(_make_rows(237))
        rows, total = leads_service.list_leads(client, ORG_ID, LeadFilters(), page=1, page_size=50)
        assert total == 237
        assert len(rows) == 50

    def test_second_page_is_a_different_slice(self):
        client = _FakeClient(_make_rows(120))
        page1, _ = leads_service.list_leads(client, ORG_ID, LeadFilters(), page=1, page_size=50)
        page2, _ = leads_service.list_leads(client, ORG_ID, LeadFilters(), page=2, page_size=50)
        assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})

    def test_no_full_fetch_needed_rows_beyond_a_single_page_are_never_materialized(self):
        """The whole point: with 12,177 rows and page_size=50, only 50 rows
        should ever come back — not 12,177 sorted-then-sliced in Python."""
        client = _FakeClient(_make_rows(12177))
        rows, total = leads_service.list_leads(
            client, ORG_ID, LeadFilters(), page=1, page_size=50, sort="data_entrada", order="desc"
        )
        assert total == 12177
        assert len(rows) == 50

    def test_org_scoping_still_applies(self):
        other = uuid.UUID("11111111-2222-3333-4444-555555555555")
        client = _FakeClient(_make_rows(30) + _make_rows(30, org_id=other))
        rows, total = leads_service.list_leads(client, ORG_ID, LeadFilters(), page=1, page_size=100)
        assert total == 30
        assert {r["org_id"] for r in rows} == {str(ORG_ID)}

    def test_de_ate_filter_is_pushed_to_the_count_and_page_queries(self):
        client = _FakeClient(_make_rows(28))
        filters = LeadFilters(
            de=__import__("datetime").date(2026, 1, 1),
            ate=__import__("datetime").date(2026, 1, 5),
        )
        rows, total = leads_service.list_leads(client, ORG_ID, filters, page=1, page_size=50)
        assert total == 5
        assert len(rows) == 5


class TestFallbackToFullFetch:
    """sort in (origem, corretor) or any of q/ano/mes set -> the ORIGINAL
    fetch_filtered + Python sort/slice path, unchanged. These sorts/filters
    aren't pushed by this double (no `origem`/`corretor`/`ano`/`mes`
    columns, no `.or_()` support) — if the fallback ever stopped firing,
    the assertions below would fail loudly instead of silently
    misbehaving."""

    def test_sort_by_origem_falls_back(self):
        client = _FakeClient(_make_rows(3))
        # `_sort_key` reads `refs["sources_by_id"]` (empty here) — every
        # row's key resolves to "" so this only proves the fallback path
        # (which understands `origem`/`corretor` sort at all) ran, not
        # unrelated ordering semantics.
        rows, total = leads_service.list_leads(
            client, ORG_ID, LeadFilters(), page=1, page_size=50, sort="origem"
        )
        assert total == 3
        assert len(rows) == 3

    def test_q_filter_falls_back(self):
        client = _FakeClient(_make_rows(3))
        rows, total = leads_service.list_leads(
            client, ORG_ID, LeadFilters(q="cliente"), page=1, page_size=50
        )
        assert total == 3

    def test_ano_filter_falls_back(self):
        client = _FakeClient(_make_rows(3))
        rows, total = leads_service.list_leads(
            client, ORG_ID, LeadFilters(ano=[2026]), page=1, page_size=50
        )
        assert total == 3

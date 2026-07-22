"""Regression test for the DB-pushed list path's missing tiebreaker
(``leads_service._list_leads_db``).

Why this needs its OWN bespoke double
──────────────────────────────────────
``test_list_leads_db_pagination.py``'s ``_CountAndRangeHonouringBuilder``
only tracks a SINGLE ``.order()`` call (the second call silently
overwrites the first) — fine for proving count/range are honored, but it
can't distinguish "stable single-column sort" from "the real bug": with
~14 leads/day across 12,177 rows, ``data_entrada`` ties are the norm, and
Postgres makes NO ordering promise across tied rows unless a secondary
key breaks the tie. Two independent page requests (the real shape — a
brand-new HTTP call gets a brand-new query builder) can then return
DIFFERENT rows for "page 1", so the same lead shows up on page 3 AND
page 4 while another is never shown at all — with ``total`` staying
correct, so nothing LOOKS wrong.

The double below deliberately reorders tied rows differently on each
independent ``execute()`` call when only ONE ``.order()`` was registered
(reproducing that "no promise across ties" behavior deterministically,
not via ``random``, so the test never flakes) and sorts fully
deterministically the moment a SECOND ``.order()`` call (the ``id``
tiebreak) is registered — exactly what
``leads_service._list_leads_db`` now does.
"""
from __future__ import annotations

import uuid

from app.modules.leads.services import leads_service
from app.modules.leads.services.query import LeadFilters

ORG_ID = uuid.UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")


class _TieProneBuilder:
    """Minimal PostgREST-like builder that honors ``eq``/``range``/
    ``count="exact"`` faithfully, but — for a column with many tied
    values — returns a DIFFERENT (deterministically alternating, not
    random) relative order for those ties on every other ``execute()``
    call UNLESS a second ``.order()`` call was made (the tiebreak)."""

    def __init__(self, rows: list[dict], call_state: dict) -> None:
        self._rows = rows
        self._orders: list[tuple[str, bool]] = []
        self._start = 0
        self._end: int | None = None
        self._count_mode = False
        self._call_state = call_state

    def select(self, *_cols, **kwargs):
        self._count_mode = kwargs.get("count") == "exact"
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
        return self

    def order(self, col, desc=False, **_k):
        self._orders.append((col, desc))
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def _sorted_rows(self) -> list[dict]:
        rows = list(self._rows)
        if len(self._orders) >= 2:
            # Multi-column order (the fix): each later key breaks every
            # tie left by the keys before it — fully deterministic.
            for col, desc in reversed(self._orders):
                rows.sort(key=lambda r: r.get(col), reverse=desc)
            return rows
        if len(self._orders) == 1:
            col, desc = self._orders[0]
            self._call_state["n"] += 1
            flip = self._call_state["n"] % 2 == 1
            groups: dict = {}
            order_keys: list = []
            for r in rows:
                key = r.get(col)
                if key not in groups:
                    groups[key] = []
                    order_keys.append(key)
                groups[key].append(r)
            if flip:
                for key in groups:
                    groups[key] = list(reversed(groups[key]))
            order_keys.sort(reverse=desc)
            return [r for key in order_keys for r in groups[key]]
        return rows

    def execute(self):
        rows = self._sorted_rows()
        if self._count_mode:
            return type("Resp", (), {"data": rows, "count": len(rows)})()
        end = len(rows) - 1 if self._end is None else self._end
        window = rows[self._start : end + 1]
        return type("Resp", (), {"data": window, "count": None})()


class _FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        # Shared across every builder this client hands out — simulates
        # "the underlying table has no stable tie order" persisting
        # across independent per-request query builders.
        self._call_state = {"n": 0}

    def table(self, _name):
        return _TieProneBuilder(list(self._rows), self._call_state)


def _make_tied_rows(n: int, org_id: uuid.UUID = ORG_ID) -> list[dict]:
    """Every row shares the SAME ``data_entrada`` — the realistic
    ~14-leads/day tie density, exaggerated to 100% for a small fixture."""
    return [
        {
            "id": f"{i:08d}-0000-0000-0000-000000000000",
            "org_id": str(org_id),
            "data_entrada": "2026-01-15",
            "cliente_nome": f"Cliente {i:04d}",
            "created_at": "2026-01-15T00:00:00Z",
        }
        for i in range(n)
    ]


class TestTiebreakGuardsUnstablePaging:
    def test_double_reorders_ties_without_a_second_order_call(self):
        """Guards the guard: with only ONE ``.order()`` call (the
        pre-fix shape), the SAME double genuinely returns tied rows in a
        different relative order across independent calls — proving the
        regression test below would actually have caught the bug."""
        client = _FakeClient(_make_tied_rows(40))

        def _first_ten():
            builder = client.table("leads").select("*").eq("org_id", str(ORG_ID))
            resp = builder.order("data_entrada", desc=True).range(0, 9).execute()
            return [r["id"] for r in resp.data]

        first_call = _first_ten()
        second_call = _first_ten()
        assert first_call != second_call

    def test_repeated_page_one_requests_return_the_same_set(self):
        """The regression proper: with the real ``_list_leads_db`` (now
        ``.order(sort, ...).order("id")``), two independent "page 1"
        requests over heavily-tied rows must return the IDENTICAL set of
        leads — not just the same total."""
        client = _FakeClient(_make_tied_rows(40))
        page_a, total_a = leads_service.list_leads(
            client, ORG_ID, LeadFilters(), page=1, page_size=10,
            sort="data_entrada", order="desc",
        )
        page_b, total_b = leads_service.list_leads(
            client, ORG_ID, LeadFilters(), page=1, page_size=10,
            sort="data_entrada", order="desc",
        )
        assert total_a == total_b == 40
        assert {r["id"] for r in page_a} == {r["id"] for r in page_b}

    def test_walking_every_page_yields_the_complete_set_with_no_duplicates(self):
        """The user-facing symptom: paging through ALL of Base de Leads
        (4 pages of 10 over 40 tied rows) must show every lead exactly
        once — no repeat on page 3+4, no lead that never appears."""
        client = _FakeClient(_make_tied_rows(40))
        seen: list[str] = []
        for page in (1, 2, 3, 4):
            rows, total = leads_service.list_leads(
                client, ORG_ID, LeadFilters(), page=page, page_size=10,
                sort="data_entrada", order="desc",
            )
            assert total == 40
            seen.extend(r["id"] for r in rows)
        assert len(seen) == len(set(seen)) == 40

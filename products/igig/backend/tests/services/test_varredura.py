"""`app.services.varredura` — the ONE cross-org discovery helper every daily
sweep now composes, replacing three independently-hand-rolled (and unpaged)
queries. A fake postgrest-shaped query builder stands in for the real
client: only `.select`/`.eq`/`.order`/`.range`/`.execute` matter here, and
this proves the composition + the pagination, not the real SDK.
"""
from __future__ import annotations

from app.services.varredura import linhas_cross_org, orgs_distintos


class _FakeQuery:
    """Chainable stand-in mirroring the postgrest builder shape used here."""

    def __init__(self, rows: list[dict], *, select: str = "*", filters: tuple = ()) -> None:
        self._rows = rows
        self.select_arg = select
        self.filters = filters
        self._order_col: str | None = None
        self._range: tuple[int, int] | None = None

    def eq(self, column, value):
        return _FakeQuery(self._rows, select=self.select_arg, filters=self.filters + (("eq", column, value),))

    def order(self, column):
        self._order_col = column
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = self._rows
        for op, column, value in self.filters:
            if op == "eq":
                rows = [r for r in rows if r.get(column) == value]
        assert self._order_col == "id", "linhas_cross_org must order by id_key before range()"
        start, end = self._range
        page = sorted(rows, key=lambda r: r["id"])[start : end + 1]
        return type("Response", (), {"data": page})()


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def select(self, columns):
        return _FakeQuery(self._rows, select=columns)


class _FakeDb:
    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self._tables = tables

    def table(self, name):
        return _FakeTable(self._tables.get(name, []))


def test_returns_every_row_across_a_single_page():
    db = _FakeDb({"automacao": [{"id": "1", "org_id": "a"}, {"id": "2", "org_id": "b"}]})
    rows = linhas_cross_org(db, "automacao", label="test")
    assert {r["id"] for r in rows} == {"1", "2"}


def test_pages_past_a_small_page_size():
    """The whole point: an unpaged `.select().execute()` truncates silently.
    A small `page_size` forces multiple round-trips through the same fake."""
    rows_in = [{"id": str(i), "org_id": "a"} for i in range(7)]
    db = _FakeDb({"fatura": rows_in})
    rows = linhas_cross_org(db, "fatura", page_size=2, label="test")
    assert sorted(r["id"] for r in rows) == [str(i) for i in range(7)]


def test_filtros_compose_onto_the_query_before_ordering():
    db = _FakeDb({"cliente": [
        {"id": "1", "org_id": "a", "status": "ativo"},
        {"id": "2", "org_id": "a", "status": "encerrado"},
    ]})
    rows = linhas_cross_org(
        db, "cliente", filtros=lambda q: q.eq("status", "ativo"), label="test",
    )
    assert [r["id"] for r in rows] == ["1"]


def test_select_can_be_narrowed_as_long_as_id_key_is_present():
    db = _FakeDb({"fatura": [{"id": "1", "org_id": "a", "cliente_id": "c1"}]})
    rows = linhas_cross_org(db, "fatura", select="id,org_id,cliente_id", label="test")
    assert rows == [{"id": "1", "org_id": "a", "cliente_id": "c1"}]


def test_orgs_distintos_dedupes_and_sorts():
    linhas = [{"org_id": "b"}, {"org_id": "a"}, {"org_id": "b"}, {"org_id": "c"}]
    assert orgs_distintos(linhas) == ["a", "b", "c"]


def test_orgs_distintos_of_nothing_is_empty():
    assert orgs_distintos([]) == []

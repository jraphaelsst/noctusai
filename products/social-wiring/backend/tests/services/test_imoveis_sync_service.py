"""`ImovelSyncService` — the full-pull sync.

Driven through `FakeVistaAdapter`, which is the point of having widened the
Fake+Real seam in P2.0b: this suite would otherwise need a live tenant.

The assertions worth reading are the ones about **honest reporting**. A sync
that fetches 1919 imóveis and silently drops the detalhes for 40 of them
looks identical, from the outside, to a clean run — and those 40 are exactly
the imóveis that then vanish from amenity filters with no error anywhere.
So `SyncReport.complete` and `detalhes_failed` are load-bearing, and tested
as such.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from noctusai_lib.domain.real_estate import Corretor, Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter

from app.services.imoveis_service import (
    ImovelSyncService,
    SyncReport,
    _imovel_to_row,
)

ORG = uuid4()


class _FakeTable:
    """Captures upserts so a test can assert idempotency and row shape."""

    def __init__(self, store: dict):
        self._store = store

    def upsert(self, rows, on_conflict=None):
        self._on_conflict = on_conflict
        for row in rows:
            # Emulate the real (org_id, codigo) PK — this is what makes a
            # second sync an UPDATE rather than a duplicate INSERT.
            self._store[(row["org_id"], row["codigo"])] = row
        return self

    def execute(self):
        return self


class _FakeClient:
    def __init__(self):
        self.store: dict = {}

    def schema(self, _name):
        return self

    def table(self, _name):
        return _FakeTable(self.store)


def _imovel(codigo: str, **kw) -> Imovel:
    return Imovel(codigo=codigo, **kw)


def _adapter_with(n: int) -> FakeVistaAdapter:
    adapter = FakeVistaAdapter()
    for i in range(n):
        adapter.add_imovel(_imovel(f"ONE{1000 + i}", categoria="Casa"))
    return adapter


def test_sync_upserts_every_imovel():
    client = _FakeClient()
    svc = ImovelSyncService(client, _adapter_with(7))
    report = asyncio.run(svc.sync(ORG, with_detalhes=False, page_size=3))

    assert report.total_reported == 7
    assert report.upserted == 7
    assert len(client.store) == 7
    assert report.complete is True


def test_sync_is_idempotent():
    """Running twice leaves N rows, not 2N — the whole point of upsert-by-PK."""
    client = _FakeClient()
    adapter = _adapter_with(5)
    svc = ImovelSyncService(client, adapter)

    asyncio.run(svc.sync(ORG, with_detalhes=False))
    first = dict(client.store)
    asyncio.run(svc.sync(ORG, with_detalhes=False))

    assert len(client.store) == 5
    assert set(client.store) == set(first)


def test_sync_paginates_through_every_page():
    client = _FakeClient()
    svc = ImovelSyncService(client, _adapter_with(10))
    report = asyncio.run(svc.sync(ORG, with_detalhes=False, page_size=3))
    # 10 items at 3/page = 4 pages
    assert report.pages_fetched == 4
    assert report.upserted == 10


def test_report_is_incomplete_when_a_detalhes_call_fails():
    """The honesty assertion.

    A detalhes failure downgrades one imóvel to its listar-only shape. The
    imóvel is still stored — better partial than missing — but the report
    must NOT claim completeness, because that imóvel now has no
    caracteristicas and will silently miss every amenity filter.
    """
    client = _FakeClient()
    adapter = _adapter_with(3)

    async def boom(code):
        if code == "ONE1001":
            raise RuntimeError("upstream 500")
        return await FakeVistaAdapter.get_imovel(adapter, code)

    adapter.get_imovel = boom  # type: ignore[assignment]

    svc = ImovelSyncService(client, adapter)
    report = asyncio.run(svc.sync(ORG, with_detalhes=True))

    assert report.complete is False
    assert report.detalhes_failed == ["ONE1001"]
    # The imóvel is still persisted — a failure must not silently drop it.
    assert (str(ORG), "ONE1001") in client.store
    assert report.upserted == 3


def test_report_as_dict_surfaces_the_failure_count():
    report = SyncReport(upserted=5, detalhes_failed=["A1", "B2"])
    payload = report.as_dict()
    assert payload["detalhes_failed_count"] == 2
    assert payload["complete"] is False
    assert payload["detalhes_failed"] == ["A1", "B2"]


def test_page_failure_is_recorded_not_swallowed():
    client = _FakeClient()
    adapter = _adapter_with(6)
    original = adapter.list_imoveis

    async def flaky(*, page=1, page_size=50, with_detalhes=False):
        if page == 2:
            raise RuntimeError("network reset")
        return await original(page=page, page_size=page_size, with_detalhes=with_detalhes)

    adapter.list_imoveis = flaky  # type: ignore[assignment]

    svc = ImovelSyncService(client, adapter)
    report = asyncio.run(svc.sync(ORG, with_detalhes=False, page_size=2))

    assert report.complete is False
    assert any("page 2" in f for f in report.page_failures)


# ─── row mapping ──────────────────────────────────────────────────────────


def test_row_serializes_sets_deterministically():
    """Sorted, so re-syncing unchanged data doesn't produce a spurious UPDATE."""
    imovel = _imovel(
        "ONE1",
        caracteristicas=frozenset({"piscina", "churrasqueira", "adega"}),
        finalidades=frozenset({"venda", "aluguel"}),
    )
    row = _imovel_to_row(imovel, ORG, "2026-08-03T00:00:00Z")
    assert row["caracteristicas"] == ["adega", "churrasqueira", "piscina"]
    assert row["finalidades"] == ["aluguel", "venda"]


def test_row_keeps_corretores_as_a_list_of_dicts():
    imovel = _imovel(
        "ONE1",
        corretores=[Corretor(codigo="1", nome="A"), Corretor(codigo="2", nome="B")],
    )
    row = _imovel_to_row(imovel, ORG, "2026-08-03T00:00:00Z")
    assert len(row["corretores"]) == 2
    assert row["corretores"][0]["nome"] == "A"


def test_row_preserves_the_zero_vs_none_distinction():
    """The census asymmetry has to survive serialization too."""
    imovel = _imovel("ONE1", dormitorios=0, valor_locacao=None, area_construida=None)
    row = _imovel_to_row(imovel, ORG, "2026-08-03T00:00:00Z")
    assert row["dormitorios"] == 0
    assert row["valor_locacao"] is None
    assert row["area_construida"] is None


# ─── PostgREST row cap ────────────────────────────────────────────────────


class _CappedTable:
    """A table that silently truncates like PostgREST does.

    The real failure was not an error — it was a short answer with an `ok`
    status. This fake reproduces exactly that: honour `.range()`, and never
    return more than `cap` rows in one response.
    """

    CAP = 1000

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._lo, self._hi = 0, None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def range(self, lo, hi):
        self._lo, self._hi = lo, hi
        return self

    def execute(self):
        hi = self._rows if self._hi is None else self._rows[self._lo : self._hi + 1]
        window = hi[: self.CAP]
        return type("R", (), {"data": window, "count": len(self._rows)})()


class _CappedClient:
    def __init__(self, rows):
        self._rows = rows

    def schema(self, _n):
        return self

    def table(self, _n):
        return _CappedTable(self._rows)


def test_filter_options_sees_values_past_the_postgrest_row_cap():
    """The measured bug: 19 categorias reported where 20 exist.

    A rare categoria that only appears after row 1000 was invisible to the
    filter dropdown, with no error anywhere. An unpaginated select cannot
    tell "these are all the values" from "these are the first 1000 rows'
    values".
    """
    from app.services.imoveis_service import ImoveisService

    rows = [{"status": "Venda", "categoria": "Casa", "cidade": "Cotia", "bairro": "X"}
            for _ in range(1500)]
    # The needle, deliberately in the tail — past the cap.
    rows[1400] = {"status": "Aluguel", "categoria": "Loft",
                  "cidade": "Ilhabela", "bairro": "Y"}

    opts = ImoveisService(_CappedClient(rows)).filter_options(ORG)
    assert "Loft" in opts["categoria"], "tail categoria lost to the row cap"
    assert "Ilhabela" in opts["cidade"], "tail cidade lost to the row cap"
    assert "Aluguel" in opts["status"]


def test_caracteristica_counts_counts_every_row_not_just_the_first_page():
    from app.services.imoveis_service import ImoveisService

    rows = [{"caracteristicas": ["piscina"]} for _ in range(1500)]
    counts = ImoveisService(_CappedClient(rows)).caracteristica_counts(ORG)
    assert counts["piscina"] == 1500, f"counted {counts['piscina']} of 1500"

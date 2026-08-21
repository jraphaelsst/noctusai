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

    def __init__(self, store: dict, key: str):
        self._store = store
        self._key = key

    def upsert(self, rows, on_conflict=None, ignore_duplicates=False):
        self._on_conflict = on_conflict
        for row in rows:
            # Emulate the real (org_id, <key>) PK — this is what makes a
            # second sync an UPDATE rather than a duplicate INSERT.
            k = (row["org_id"], row[self._key])
            if ignore_duplicates and k in self._store:
                # `ON CONFLICT DO NOTHING`: the incumbent row wins, which is
                # what preserves a registry row's original
                # `primeiro_visto_em` / `origem_descoberta`.
                continue
            self._store[k] = row
        return self

    def execute(self):
        return self


class _FakeClient:
    """Models the two tables the sync writes AND the sweep RPC.

    `rpc` is not decoration. `ImovelSyncService._sweep_registry` calls
    `client.rpc("sweep_imovel_registry", ...)`, and a fake without it raises
    AttributeError into the method's own except-branch — the sync still
    "succeeds", the test still passes, and the sweep is never exercised.
    That false green is exactly what this models away.
    """

    def __init__(self):
        self.store: dict = {}
        self.registry: dict = {}
        self.rpc_calls: list[tuple[str, dict]] = []
        self.sweep_result = {"marcados_ativos": 0, "marcados_delistados": 0}

    def schema(self, _name):
        return self

    def table(self, name):
        if name == "imovel_registry":
            return _FakeTable(self.registry, "codigo_canonical")
        return _FakeTable(self.store, "codigo")

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        client = self

        class _Resp:
            data = [client.sweep_result]

        class _Call:
            def execute(self):
                return _Resp()

        return _Call()


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


# ─── place-name merge logging (roadmap Q4, extended 2026-08-13) ───────────


def test_a_place_name_collision_logs_once_per_sync_not_once_per_row(caplog):
    """Two raw `Cidade` spellings that normalize to the same canonical value
    must produce exactly ONE log line for the whole sync — not one per row —
    even though every affected row is still upserted with the corrected
    value. Mirrors the live 57/19-row `Embu das Artes`/`Embu Das Artes`
    collision, at a scale small enough to assert precisely."""
    client = _FakeClient()
    adapter = FakeVistaAdapter()
    for i in range(3):
        adapter.add_imovel(
            _imovel(
                f"ONE{2000 + i}",
                cidade="Embu das Artes",
                vista_raw={"Cidade": "Embu das Artes"},
            )
        )
    for i in range(2):
        adapter.add_imovel(
            _imovel(
                f"ONE{3000 + i}",
                cidade="Embu das Artes",  # already-normalized by the seed adapter
                vista_raw={"Cidade": "Embu Das Artes"},  # the raw wire spelling
            )
        )

    svc = ImovelSyncService(client, adapter)
    with caplog.at_level("WARNING"):
        report = asyncio.run(svc.sync(ORG, with_detalhes=False))

    assert report.upserted == 5
    merge_lines = [
        r for r in caplog.records if "merged" in r.getMessage() and "cidade" in r.getMessage()
    ]
    assert len(merge_lines) == 1
    assert "Embu das Artes" in merge_lines[0].getMessage()
    assert "Embu Das Artes" in merge_lines[0].getMessage()


def test_no_place_name_collision_logs_nothing(caplog):
    """The common case — every raw spelling already matches its canonical
    value — must not log anything about a merge."""
    client = _FakeClient()
    adapter = FakeVistaAdapter()
    for i in range(3):
        adapter.add_imovel(
            _imovel(
                f"ONE{4000 + i}",
                cidade="Cotia",
                vista_raw={"Cidade": "Cotia"},
            )
        )

    svc = ImovelSyncService(client, adapter)
    with caplog.at_level("WARNING"):
        asyncio.run(svc.sync(ORG, with_detalhes=False))

    assert not any("merged" in r.getMessage() for r in caplog.records)


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


class TestRegistryMaintenance:
    """Migration 063 — the sync maintains `imovel_registry`.

    The registry is our PERMANENT imóvel identity. `imoveis` mirrors only
    the ACTIVE catalog, so 63.1% of leads on the live tenant point at
    imóveis that have left it. Everything of ours joins the registry, and
    the sync is what keeps it current.
    """

    @pytest.mark.asyncio
    async def test_sync_creates_a_registry_row_per_imovel(self):
        client = _FakeClient()
        svc = ImovelSyncService(client, _adapter_with(3))

        await svc.sync(ORG, with_detalhes=False)

        assert len(client.registry) == 3

    @pytest.mark.asyncio
    async def test_registry_key_is_the_canonical_code(self):
        client = _FakeClient()
        adapter = FakeVistaAdapter()
        adapter.add_imovel(_imovel("one1000", categoria="Casa"))
        svc = ImovelSyncService(client, adapter)

        await svc.sync(ORG, with_detalhes=False)

        assert (str(ORG), "ONE1000") in client.registry
        row = client.registry[(str(ORG), "ONE1000")]
        # Display keeps what Vista actually sent.
        assert row["codigo_display"] == "one1000"
        assert row["ativo_no_vista"] is True
        assert row["origem_descoberta"] == "vista_sync"

    @pytest.mark.asyncio
    async def test_resync_does_not_overwrite_an_existing_registry_row(self):
        """`ON CONFLICT DO NOTHING`.

        A row first discovered via a LEAD carries
        `origem_descoberta='lead'` and its own `primeiro_visto_em`. The
        catalog later showing us that imóvel must not rewrite either — the
        sweep owns the lifecycle columns, not this upsert.
        """
        client = _FakeClient()
        client.registry[(str(ORG), "ONE1000")] = {
            "org_id": str(ORG),
            "codigo_canonical": "ONE1000",
            "origem_descoberta": "lead",
            "primeiro_visto_em": "2024-01-01T00:00:00Z",
        }
        svc = ImovelSyncService(client, _adapter_with(1))

        await svc.sync(ORG, with_detalhes=False)

        row = client.registry[(str(ORG), "ONE1000")]
        assert row["origem_descoberta"] == "lead"
        assert row["primeiro_visto_em"] == "2024-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_complete_run_calls_the_sweep_with_the_run_timestamp(self):
        client = _FakeClient()
        svc = ImovelSyncService(client, _adapter_with(2))

        report = await svc.sync(ORG, with_detalhes=False)

        assert report.complete
        assert len(client.rpc_calls) == 1
        name, params = client.rpc_calls[0]
        assert name == "sweep_imovel_registry"
        assert params["p_org_id"] == str(ORG)
        # The sync's own stamp, not now() — the SQL compares against it.
        assert params["p_run_at"] == report.started_at

    @pytest.mark.asyncio
    async def test_sweep_counts_land_on_the_report(self):
        client = _FakeClient()
        client.sweep_result = {"marcados_ativos": 1984, "marcados_delistados": 65}
        svc = ImovelSyncService(client, _adapter_with(1))

        report = await svc.sync(ORG, with_detalhes=False)

        assert report.registry_ativos == 1984
        assert report.registry_delistados == 65
        assert report.as_dict()["registry_delistados"] == 65

    @pytest.mark.asyncio
    async def test_incomplete_run_does_NOT_sweep(self, monkeypatch):
        """The load-bearing guard.

        The sweep infers "left the catalog" from "not touched this run". On
        a run that dropped pages, thousands of imóveis are untouched because
        the FETCH failed — sweeping then would delist the catalog wholesale
        and stamp snapshots over live listings.
        """
        client = _FakeClient()
        svc = ImovelSyncService(client, _adapter_with(2))

        original = svc._fetch_page

        async def _flaky(page_no, page_size, report):
            page = await original(page_no, page_size, report)
            report.page_failures.append("page 99: simulated")
            return page

        monkeypatch.setattr(svc, "_fetch_page", _flaky)

        report = await svc.sync(ORG, with_detalhes=False)

        assert not report.complete
        assert client.rpc_calls == [], "swept on an incomplete run"

    @pytest.mark.asyncio
    async def test_a_failing_sweep_is_recorded_not_swallowed(self):
        client = _FakeClient()

        def _boom(_name, _params):
            raise RuntimeError("rpc exploded")

        client.rpc = _boom
        svc = ImovelSyncService(client, _adapter_with(1))

        report = await svc.sync(ORG, with_detalhes=False)

        assert report.registry_failures, "sweep failure vanished"
        assert "rpc exploded" in report.registry_failures[0]

    @pytest.mark.asyncio
    async def test_registry_failure_does_not_mark_the_catalog_pull_incomplete(self):
        """`complete` gates the sweep, so it must not depend on the sweep.

        Folding registry errors into `complete` would mean a failed sweep
        marks the run incomplete, which on the NEXT run skips the sweep that
        was trying to repair it — a latch that never clears.
        """
        client = _FakeClient()

        def _boom(_name, _params):
            raise RuntimeError("rpc exploded")

        client.rpc = _boom
        svc = ImovelSyncService(client, _adapter_with(1))

        report = await svc.sync(ORG, with_detalhes=False)

        assert report.complete is True
        assert report.upserted == 1

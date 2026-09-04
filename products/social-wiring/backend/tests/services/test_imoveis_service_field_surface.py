"""`imoveis-vista-field-surface` — storage+API slice tests.

Covers the three read-path behaviours CONTRACT.md adds on top of the
existing `ImoveisService`/`_imovel_to_row` (backend-storage slice; the seed
`Imovel` dataclass + normalizer are a PARALLEL slice, not touched here):

1. `_imovel_to_row` maps the 29 new columns off an `Imovel`-shaped object.
2. `dias_desde_atualizacao` (CONTRACT §3), derived from `vista_raw` at read
   time, never a stored column.
3. `orientacao_solar` (CONTRACT §3), split out of `caracteristicas`, and
   excluded from `caracteristica_counts`.

**Why `_imovel_to_row`'s new-field mapping is tested via a duck-typed
stand-in, not a real `Imovel(...)` call.** This worktree's copy of
`noctusai_lib.domain.real_estate.Imovel` does not yet declare the 29 new
attributes — a SIBLING branch adds them (this slice owns storage+API only,
per the dispatch brief). `_imovel_to_row` reads them via
`getattr(imovel, name, None)` for exactly that reason: it degrades to `None`
pre-merge and picks up real values post-merge with no code change. A test
against the real (not-yet-updated) `Imovel` could only ever assert "reads as
None", which proves the fallback, not the mapping. `types.SimpleNamespace`
seeded from a real `Imovel`'s `vars()` plus the 29 new attributes gives an
object with the exact attribute surface `_imovel_to_row` will see once the
two branches merge, so the WRITE-side mapping is verified now instead of
only after integration.
"""

from __future__ import annotations

import types
from uuid import uuid4

from noctusai_lib.domain.real_estate import Imovel

from app.services.imoveis_service import (
    ImoveisService,
    _augment_row_derived,
    _dias_desde_atualizacao,
    _imovel_to_row,
    _split_orientacao_solar,
)

from tests.imoveis_rows import imovel_row

ORG = uuid4()
_SYNCED_AT = "2026-09-04T12:00:00Z"

# Mirrors CONTRACT §1's table, value → wire-shaped python value.
_NEW_CONTRACT_FIELDS = {
    "descricao_web": "Apartamento reformado, 3 quartos.",
    "observacoes": "Chave com o zelador.",
    "valor_condominio": 850.0,
    "valor_iptu": 210.5,
    "ano_construcao": 1998,
    "situacao": "Usado",
    "ocupacao": "Desocupado",
    "pavimentos": 0,
    "posicao": "Frente",
    "elevador": True,
    "portaria": True,
    "exclusivo": False,
    "aceita_permuta": True,
    "aceita_financiamento": True,
    "destaque_web": True,
    "super_destaque_web": False,
    "exibir_no_site": True,
    "chave": "Corretor(a)",
    "zona": "Zona Sul",
    "regiao": None,
    "area_terreno": 300.0,
    "closet": 0,
    "frente": 12.5,
    "fundos": 12.5,
    "referencia": "ONE10640",
    "matricula_vista": "123.456",
    "inscricao_municipal": "São Paulo",
    "video_destaque": None,
    "tour_360": "https://tour.example.com/one10640",
}


def _imovel_with_contract_fields(**kw) -> types.SimpleNamespace:
    """A real `Imovel` (existing fields, seed-owned) plus the 29 CONTRACT
    fields grafted on as a duck-typed stand-in (see module docstring)."""
    base = Imovel(codigo="ONE10640", **kw)
    merged = {**vars(base), **_NEW_CONTRACT_FIELDS}
    return types.SimpleNamespace(**merged)


class TestImovelToRowMapsTheNewContractFields:
    def test_all_29_fields_land_on_the_row(self):
        fake = _imovel_with_contract_fields()
        row = _imovel_to_row(fake, ORG, _SYNCED_AT)
        for field, value in _NEW_CONTRACT_FIELDS.items():
            assert row[field] == value, f"{field}: expected {value!r}, got {row[field]!r}"

    def test_matricula_vista_is_the_column_name_not_matricula(self):
        fake = _imovel_with_contract_fields()
        row = _imovel_to_row(fake, ORG, _SYNCED_AT)
        assert row["matricula_vista"] == "123.456"
        assert "matricula" not in row  # bare key must never appear

    def test_degrades_to_none_when_the_real_imovel_lacks_the_fields(self):
        """Pre-merge safety net: a real `Imovel` (this worktree's current
        copy) has none of the 29 attributes yet. `_imovel_to_row` must not
        raise — every new column lands `None`, exactly like any other
        Vista field this tenant doesn't populate."""
        real = Imovel(codigo="ONE10641")
        row = _imovel_to_row(real, ORG, _SYNCED_AT)
        for field in _NEW_CONTRACT_FIELDS:
            assert row[field] is None

    def test_shadowed_fields_are_never_written_as_columns(self):
        """CORRECTION 2026-09-04: `lavabo`/`copa`/`escritorio` are Vista
        `Sim`/`Nao` values SHADOWED (returned `null`) at the top level
        whenever `Caracteristicas` rides in the same request — which our
        sync always does. `_imovel_to_row` must never write these keys; the
        true value already lives in `caracteristicas`/`caracteristicas_raw`.
        """
        fake = _imovel_with_contract_fields()
        row = _imovel_to_row(fake, ORG, _SYNCED_AT)
        for shadowed in ("lavabo", "copa", "escritorio"):
            assert shadowed not in row


class TestDiasDesdeAtualizacao:
    def test_reads_from_vista_raw(self):
        assert _dias_desde_atualizacao({"DataAtualizacaoDias": "12"}) == 12

    def test_accepts_a_native_int(self):
        assert _dias_desde_atualizacao({"DataAtualizacaoDias": 5}) == 5

    def test_missing_key_yields_none(self):
        assert _dias_desde_atualizacao({}) is None

    def test_missing_vista_raw_yields_none(self):
        assert _dias_desde_atualizacao(None) is None

    def test_malformed_value_yields_none_not_an_exception(self):
        assert _dias_desde_atualizacao({"DataAtualizacaoDias": "não disponível"}) is None

    def test_non_dict_vista_raw_yields_none(self):
        assert _dias_desde_atualizacao("garbage") is None


class TestOrientacaoSolarSplit:
    def test_the_four_orientations_are_pulled_out(self):
        amenidades, orientacao = _split_orientacao_solar(
            ["piscina", "norte", "churrasqueira", "sul"]
        )
        assert orientacao == ["norte", "sul"]
        assert amenidades == ["churrasqueira", "piscina"]
        assert "norte" not in amenidades
        assert "sul" not in amenidades

    def test_no_orientation_present_is_a_clean_split(self):
        amenidades, orientacao = _split_orientacao_solar(["piscina", "sauna"])
        assert orientacao == []
        assert amenidades == ["piscina", "sauna"]

    def test_none_input_is_tolerated(self):
        assert _split_orientacao_solar(None) == ([], [])

    def test_augment_row_derived_moves_orientation_out_of_caracteristicas(self):
        row = {
            "caracteristicas": ["piscina", "leste", "oeste"],
            "vista_raw": {"DataAtualizacaoDias": "3"},
        }
        out = _augment_row_derived(row)
        assert out["caracteristicas"] == ["piscina"]
        assert out["orientacao_solar"] == ["leste", "oeste"]
        assert out["dias_desde_atualizacao"] == 3


class _FakeListTable:
    """Supports `.select(...).eq(...).order(...).range(...).execute()`."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def execute(self):
        rows = self._rows

        class _Resp:
            data = rows

        return _Resp()


class _FakeListClient:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def schema(self, _name):
        return self

    def table(self, _name):
        return _FakeListTable(self._rows)


class TestServiceListAndGetExposeDerivedFields:
    def _row(self, **kw) -> dict:
        return imovel_row("ONE10640", ORG, _SYNCED_AT, **kw)

    def test_list_augments_every_row(self):
        row = self._row(caracteristicas=["piscina", "norte"])
        row["vista_raw"] = {"DataAtualizacaoDias": "7"}
        svc = ImoveisService(_FakeListClient([row]))

        result = svc.list(ORG)

        item = result["items"][0]
        assert item["orientacao_solar"] == ["norte"]
        assert item["caracteristicas"] == ["piscina"]
        assert item["dias_desde_atualizacao"] == 7

    def test_get_augments_the_row(self):
        row = self._row(caracteristicas=["piscina", "sul"])
        row["vista_raw"] = {"DataAtualizacaoDias": "1"}

        class _FakeGetTable(_FakeListTable):
            def limit(self, *_a, **_kw):
                return self

        class _FakeGetClient(_FakeListClient):
            def table(self, _name):
                return _FakeGetTable(self._rows)

        svc = ImoveisService(_FakeGetClient([row]))
        result = svc.get(ORG, "ONE10640")

        assert result["orientacao_solar"] == ["sul"]
        assert result["caracteristicas"] == ["piscina"]
        assert result["dias_desde_atualizacao"] == 1


class TestCaracteristicaCountsExcludesOrientation:
    def test_orientation_slugs_never_appear_in_counts(self):
        rows = [
            imovel_row("ONE1", ORG, _SYNCED_AT, caracteristicas=["piscina", "norte"]),
            imovel_row("ONE2", ORG, _SYNCED_AT, caracteristicas=["piscina", "sul"]),
        ]

        class _PagedTable(_FakeListTable):
            pass

        class _PagedClient(_FakeListClient):
            def table(self, _name):
                return _PagedTable(self._rows)

        svc = ImoveisService(_PagedClient(rows))
        counts = svc.caracteristica_counts(ORG)

        assert counts == {"piscina": 2}
        assert "norte" not in counts
        assert "sul" not in counts

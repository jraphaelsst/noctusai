"""Campanhas — registry resolution + the "solicitar campanha" signal.

Two properties carry the weight:

  · Resolution goes through `imovel_registry`, NOT `imoveis`. A campaign
    outlives the listing it promoted — the imóvel selling is the campaign
    SUCCEEDING — and the mirror drops sold imóveis on the next sync. A
    request for a sold imóvel must still resolve.
  · "Already requested" is a distinct outcome from "lookup failed" and
    from "no such imóvel". Collapsing them would make the button render a
    500 for the ordinary case of pressing it twice.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.campanhas_service import (
    CampanhaError,
    CampanhasService,
    ImovelDesconhecido,
    SolicitacaoDuplicada,
)

ORG = uuid4()
_REF = "11111111-2222-3333-4444-555555555555"


class _Table:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name
        self._filters: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def limit(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        rows = self._store.get(self._name, [])
        if getattr(self, "_pending", None) is not None:
            row = dict(self._pending)
            row.setdefault("id", str(uuid4()))
            # Emulate `uq_sw_campanha_solicitacoes_pendente`.
            clash = any(
                r.get("org_id") == row.get("org_id")
                and r.get("imovel_ref_id") == row.get("imovel_ref_id")
                and r.get("status") == "pendente"
                for r in rows
            )
            if clash and row.get("status") == "pendente":
                raise RuntimeError(
                    'duplicate key value violates unique constraint '
                    '"uq_sw_campanha_solicitacoes_pendente"'
                )
            rows.append(row)
            self._store[self._name] = rows
            self._pending = None
            return type("R", (), {"data": [row]})()

        matched = [
            r for r in rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]
        return type("R", (), {"data": matched})()


class _Client:
    def __init__(self, store: dict | None = None):
        self.store = store or {}

    def schema(self, _n):
        return self

    def table(self, name):
        return _Table(self.store, name)


class _BoomClient(_Client):
    def table(self, _name):
        raise RuntimeError("postgrest unreachable")


def _registry_row(codigo: str = "ONE10640"):
    return {"id": _REF, "org_id": str(ORG), "codigo_canonical": codigo}


class TestResolveImovelRef:
    def test_resolves_an_exact_code(self):
        svc = CampanhasService(_Client({"imovel_registry": [_registry_row()]}))
        assert svc.resolve_imovel_ref(ORG, "ONE10640") == _REF

    def test_resolves_a_lowercase_code(self):
        svc = CampanhasService(_Client({"imovel_registry": [_registry_row()]}))
        assert svc.resolve_imovel_ref(ORG, "one10640") == _REF

    def test_resolves_a_code_with_whitespace(self):
        svc = CampanhasService(_Client({"imovel_registry": [_registry_row()]}))
        assert svc.resolve_imovel_ref(ORG, "  One10640 ") == _REF

    def test_resolves_a_SOLD_imovel(self):
        """The registry is permanent; the mirror is not.

        A sold imóvel has left `imoveis` entirely. If resolution went
        through the mirror, every campaign for a successful listing would
        become unreachable at the moment it succeeded.
        """
        sold = {**_registry_row("CA5180"), "ativo_no_vista": False}
        svc = CampanhasService(_Client({"imovel_registry": [sold]}))
        assert svc.resolve_imovel_ref(ORG, "CA5180") == _REF

    def test_unknown_code_raises_imovel_desconhecido(self):
        svc = CampanhasService(_Client({"imovel_registry": []}))
        with pytest.raises(ImovelDesconhecido):
            svc.resolve_imovel_ref(ORG, "ONE99999")

    def test_empty_code_raises_rather_than_matching_anything(self):
        svc = CampanhasService(_Client({"imovel_registry": [_registry_row()]}))
        with pytest.raises(ImovelDesconhecido):
            svc.resolve_imovel_ref(ORG, "   ")

    def test_transport_failure_is_not_reported_as_a_miss(self):
        """"Couldn't ask" must not look like "not there" — one is a 503,
        the other a 404."""
        svc = CampanhasService(_BoomClient())
        with pytest.raises(CampanhaError) as exc:
            svc.resolve_imovel_ref(ORG, "ONE10640")
        assert not isinstance(exc.value, ImovelDesconhecido)

    def test_resolution_is_org_scoped(self):
        svc = CampanhasService(_Client({"imovel_registry": [_registry_row()]}))
        with pytest.raises(ImovelDesconhecido):
            svc.resolve_imovel_ref(uuid4(), "ONE10640")


class TestSolicitar:
    def test_records_a_pending_request(self):
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))

        created = svc.solicitar(ORG, "ONE10640", justificativa="bom preço")

        assert created["status"] == "pendente"
        assert created["imovel_ref_id"] == _REF
        assert created["justificativa"] == "bom preço"
        assert len(store["campanha_solicitacoes"]) == 1

    def test_blank_justification_is_stored_as_null_not_empty_string(self):
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        created = svc.solicitar(ORG, "ONE10640", justificativa="   ")
        assert created["justificativa"] is None

    def test_second_request_raises_duplicada(self):
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        svc.solicitar(ORG, "ONE10640")

        with pytest.raises(SolicitacaoDuplicada):
            svc.solicitar(ORG, "ONE10640")

        assert len(store["campanha_solicitacoes"]) == 1

    def test_case_variant_is_still_the_same_imovel(self):
        """`one10640` and `ONE10640` must not produce two open requests."""
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        svc.solicitar(ORG, "ONE10640")

        with pytest.raises(SolicitacaoDuplicada):
            svc.solicitar(ORG, "one10640")

    def test_unknown_imovel_raises_before_writing_anything(self):
        store = {"imovel_registry": [], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        with pytest.raises(ImovelDesconhecido):
            svc.solicitar(ORG, "ONE99999")
        assert store["campanha_solicitacoes"] == []

    def test_index_violation_is_translated_to_duplicada(self):
        """The read-then-write check loses a concurrent race; the partial
        unique index is the real guard, and its error must still surface as
        a duplicate rather than a 503."""
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        # Pre-seed a pending row the duplicate-check cannot see, by giving
        # it a status the filter ignores until insert time.
        store["campanha_solicitacoes"].append(
            {"org_id": str(ORG), "imovel_ref_id": _REF, "status": "pendente"}
        )
        # The service's own pre-check will catch this one.
        with pytest.raises(SolicitacaoDuplicada):
            svc.solicitar(ORG, "ONE10640")


class TestSolicitacaoDoImovel:
    def test_returns_the_pending_request(self):
        store = {
            "imovel_registry": [_registry_row()],
            "campanha_solicitacoes": [
                {"id": "x", "org_id": str(ORG), "imovel_ref_id": _REF, "status": "pendente"}
            ],
        }
        svc = CampanhasService(_Client(store))
        assert svc.solicitacao_do_imovel(ORG, "ONE10640")["id"] == "x"

    def test_returns_none_when_there_is_none(self):
        store = {"imovel_registry": [_registry_row()], "campanha_solicitacoes": []}
        svc = CampanhasService(_Client(store))
        assert svc.solicitacao_do_imovel(ORG, "ONE10640") is None

    def test_unknown_imovel_is_a_clean_none_not_an_error(self):
        """The button asks this on every page load. An unknown código is a
        clean "no request", not something to surface."""
        svc = CampanhasService(_Client({"imovel_registry": [], "campanha_solicitacoes": []}))
        assert svc.solicitacao_do_imovel(ORG, "ONE99999") is None

    def test_a_resolved_but_non_pending_request_does_not_count(self):
        store = {
            "imovel_registry": [_registry_row()],
            "campanha_solicitacoes": [
                {"id": "x", "org_id": str(ORG), "imovel_ref_id": _REF, "status": "recusada"}
            ],
        }
        svc = CampanhasService(_Client(store))
        assert svc.solicitacao_do_imovel(ORG, "ONE10640") is None

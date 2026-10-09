"""`pipeline.funil_eventos.mover_por_evento` — CONTRACT sw-lead-to-contract §6."""
from __future__ import annotations

import sys
import types

import pytest
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.modules.pipeline import funil_eventos
from tests.modules.pipeline.conftest import (
    FUNIL_STAGES,
    ORG_A,
    STAGE_ID,
    atendimento,
    seed_titular,
)

# The real funnel's chaves (migration 037+). conftest's FUNIL_STAGES is the
# legacy set, so the stages under test are seeded here.
CHAVES = ["qualificacao", "visitas", "proposta_recebida", "proposta_decisao", "processos_venda"]
ESTAGIOS = [
    {"id": f"s-{c}", "org_id": ORG_A, "pipeline": "funil", "slug": c, "label": c,
     "cor": "secondary", "posicao": i, "papel": "proposta_aceite" if c == "proposta_decisao" else None,
     "ativo": True}
    for i, c in enumerate(CHAVES)
]


def _db(etapa="qualificacao", *, apto=True, estagios=ESTAGIOS, status="aberta"):
    mock = MockSupabaseClient()
    row = atendimento("neg-1", "novo", status=status)
    row["etapa_id"] = f"s-{etapa}"
    mock.set_table_data("pipeline_stages", list(estagios))
    mock.set_table_data("pipeline_movimentos", [])
    mock.set_table_data("atendimentos", [row])
    seed_titular(mock, apto=apto)
    return mock


def _etapa(mock):
    return mock.table("atendimentos").select("*").execute().data[0]["etapa_id"]


class TestRoteiroCriado:
    def test_moves_forward_and_records_etapa_auto(self):
        mock = _db("qualificacao")
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert (r["moveu"], r["de"], r["para"], r["motivo"]) == (True, "qualificacao", "visitas", None)
        assert _etapa(mock) == "s-visitas"
        mov = mock.table("pipeline_movimentos").select("*").execute().data
        assert [m["motivo"] for m in mov] == ["etapa_auto:roteiro_criado"]

    def test_never_moves_backwards(self):
        mock = _db("proposta_decisao")
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert r["moveu"] is False and r["motivo"] == "ja_adiante"
        assert _etapa(mock) == "s-proposta_decisao"
        assert mock.table("pipeline_movimentos").select("*").execute().data == []

    def test_already_on_the_stage_is_not_a_move(self):
        mock = _db("visitas")
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert r["moveu"] is False and r["motivo"] == "ja_na_etapa"

    def test_gate_refusal_is_returned_not_raised(self):
        mock = _db("qualificacao", apto=False)
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert r["moveu"] is False and r["motivo"] and r["pendencias"]
        assert _etapa(mock) == "s-qualificacao"

    def test_removed_stage_chave_is_reported(self):
        mock = _db("qualificacao", estagios=[e for e in ESTAGIOS if e["slug"] != "visitas"])
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert r["moveu"] is False and r["motivo"] == "etapa_inexistente"

    def test_closed_atendimento_is_left_alone(self):
        mock = _db("qualificacao", status="fechada")
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "roteiro_criado", "user-1")
        assert r["moveu"] is False and "fechada" in r["motivo"]


def test_unknown_event_is_a_programming_error():
    with pytest.raises(ValueError):
        funil_eventos.mover_por_evento(_db(), ORG_A, "neg-1", "inventado", "u")


def test_lead_criado_is_a_noop():
    r = funil_eventos.mover_por_evento(_db("qualificacao"), ORG_A, "neg-1", "lead_criado", "u")
    assert r["moveu"] is False and r["motivo"] == "noop"


class TestPropostaAceita:
    def _stub(self, monkeypatch, fn):
        modulo = types.ModuleType("app.modules.pipeline.aceite")
        modulo.aceitar_proposta = fn
        monkeypatch.setitem(sys.modules, "app.modules.pipeline.aceite", modulo)

    def test_moves_then_calls_the_acceptance_boundary(self, monkeypatch):
        chamadas = []

        def aceitar(client, org_id, atendimento_id, actor_id):
            chamadas.append((str(org_id), atendimento_id, actor_id))
            return {"processo": {"id": "p1"}, "already_accepted": False}

        self._stub(monkeypatch, aceitar)
        mock = _db("proposta_recebida")
        r = funil_eventos.mover_por_evento(mock, ORG_A, "neg-1", "proposta_aceita", "user-1")
        assert r["moveu"] is True and r["para"] == "proposta_decisao"
        assert r["aceite"]["already_accepted"] is False
        assert chamadas == [(ORG_A, "neg-1", "user-1")]

    def test_gate_refusal_skips_acceptance(self, monkeypatch):
        def aceitar(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("aceite must not run when the move was refused")

        self._stub(monkeypatch, aceitar)
        r = funil_eventos.mover_por_evento(_db("proposta_recebida", apto=False), ORG_A, "neg-1", "proposta_aceita", "u")
        assert r["moveu"] is False and "aceite" not in r

    def test_missing_acceptance_module_is_reported_not_skipped(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "app.modules.pipeline.aceite", None)  # import -> ImportError
        r = funil_eventos.mover_por_evento(_db("proposta_recebida"), ORG_A, "neg-1", "proposta_aceita", "u")
        assert r["moveu"] is True and r["motivo"] == "aceite_indisponivel"

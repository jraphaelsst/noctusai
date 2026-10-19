"""Handoff ledger (maya-blocks CONTRACT §2): T1 `novo_lead` sink, T2 block-boundary hook (+ the aceite movement),
the emitido -> assumido | expirado machine. Off = nothing written; replays are no-ops; failures never block.
Mock DB of `tests.support.julia_world`; the sink runs through the real `julia_eventos_service.emitir`."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from app.modules.atendimento_blocos import handoffs as h
from app.modules.atendimento_blocos import repository as repo
from app.modules.pipeline.aceite import aceitar_proposta
from app.services import julia_eventos_service as eventos

from tests.support.julia_world import ORG_ID, OWNER_ID
from .conftest import atendimento, handoffs, movimento, processo, stage_id, supervisao_on

CONTATO = "00000000-0000-4000-8000-00000000c0c0"
T0 = "2026-10-19T12:00:00+00:00"


def _novo_lead(world, *, lead_id="lead-1", eid="ev-1", tipo="novo_lead"):
    return {"id": eid, "org_id": ORG_ID, "tipo": tipo, "contato_id": CONTATO, "created_at": T0,
            "payload": {"lead_id": lead_id, "gatilho": "qualificado", "criado": True}}


# ── bloco_atual (§1.1) ──────────────────────────────────────────────────────
class TestBlocoAtual:
    def test_contato_without_lead_is_sdr(self, world):
        assert repo.bloco_atual(world.sw, ORG_ID, contato={"id": CONTATO, "lead_id": None}) == "sdr"

    def test_funil_card_then_processos_card_wins(self, world):
        atendimento(world, etapa="negociacao")
        assert repo.bloco_atual(world.sw, ORG_ID, lead_id="lead-1") == "negociacao"
        processo(world, etapa="financiamento_escritura")
        assert repo.bloco_atual(world.sw, ORG_ID, lead_id="lead-1") == "financeiro"

    def test_no_card_or_unowned_stage_is_none(self, world):
        assert repo.bloco_atual(world.sw, ORG_ID, lead_id="lead-x") is None
        world.sw.table("pipeline_stages").insert({"id": "pv", "org_id": ORG_ID, "pipeline": "funil", "slug": "pos_venda",
                                                   "label": "P", "posicao": 9, "ativo": True}).execute()
        atendimento(world, "a2", lead_id="lead-2", etapa_id="pv")
        assert repo.bloco_atual(world.sw, ORG_ID, lead_id="lead-2") is None

    def test_a_folded_card_is_never_the_card(self, world):
        atendimento(world, "old", etapa="negociacao", substituida_por="a1")
        atendimento(world, "a1", etapa="visitas")
        assert repo.bloco_atual(world.sw, ORG_ID, lead_id="lead-1") == "atendimento"


# ── T1 ──────────────────────────────────────────────────────────────────────
class TestSinkNovoLead:
    def test_supervision_off_writes_nothing(self, world):
        atendimento(world)
        assert h.sink_novo_lead(world.sw, _novo_lead(world)) is None and handoffs(world) == []

    def test_writes_sdr_to_atendimento_with_references_only(self, world):
        supervisao_on(world)
        atendimento(world)
        world.sw.table("julia_atribuicoes").insert({"id": "atr-1", "org_id": ORG_ID, "contato_id": CONTATO, "created_at": T0}).execute()
        world.sw.table("julia_envio_entregas").insert({"id": "ent-err", "org_id": ORG_ID, "contato_id": CONTATO, "status": "erro", "erro": "x", "created_at": T0}).execute()
        world.sw.table("julia_envio_entregas").insert({"id": "ent-ok", "org_id": ORG_ID, "contato_id": CONTATO, "status": "ok", "created_at": T0}).execute()
        h.sink_novo_lead(world.sw, _novo_lead(world))
        (row,) = handoffs(world)
        assert {k: row[k] for k in ("de_bloco", "para_bloco", "de_agent_key", "para_agent_key", "gatilho", "origem_evento",
                                    "contato_id", "lead_id", "atendimento_id", "atribuicao_id", "entrega_id", "status")} == {
            "de_bloco": "sdr", "para_bloco": "atendimento", "de_agent_key": "julia", "para_agent_key": None,
            "gatilho": "novo_lead", "origem_evento": "ev-1", "contato_id": CONTATO, "lead_id": "lead-1",
            "atendimento_id": "a1", "atribuicao_id": "atr-1", "entrega_id": "ent-ok", "status": "emitido",
        }
        assert row["created_at"] == T0

    def test_replay_is_a_no_op(self, world):
        supervisao_on(world)
        atendimento(world)
        h.sink_novo_lead(world.sw, _novo_lead(world))
        assert h.sink_novo_lead(world.sw, _novo_lead(world)) is None
        assert len(handoffs(world)) == 1

    def test_existing_lead_already_in_negociacao_targets_that_block(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        h.sink_novo_lead(world.sw, _novo_lead(world))
        assert handoffs(world)[0]["para_bloco"] == "negociacao"

    def test_no_card_or_sem_bloco_writes_nothing_and_warns(self, world, caplog):
        supervisao_on(world)
        with caplog.at_level(logging.WARNING):
            h.sink_novo_lead(world.sw, _novo_lead(world, lead_id="lead-sem-card"))
        assert handoffs(world) == [] and "sem_card" in caplog.text

    def test_other_event_types_are_ignored(self, world):
        supervisao_on(world)
        atendimento(world)
        assert h.sink_novo_lead(world.sw, _novo_lead(world, tipo="handoff")) is None and handoffs(world) == []

    def test_registered_on_the_event_bus_and_fired_by_emitir(self, world):
        h.registrar()
        supervisao_on(world)
        atendimento(world)
        ev = eventos.emitir(world.sw, ORG_ID, "novo_lead", CONTATO, {"lead_id": "lead-1", "gatilho": "qualificado", "criado": True})
        (row,) = handoffs(world)
        assert row["origem_evento"] == str(ev["id"])

    def test_a_failure_never_raises_into_the_send(self, world, caplog):
        supervisao_on(world)

        class Quebrado:
            def table(self, name):
                if name == "atendimentos":
                    raise RuntimeError("db down")
                return world.sw.table(name)

        with caplog.at_level(logging.ERROR):
            assert h.sink_novo_lead(Quebrado(), _novo_lead(world)) is None
        assert "the send stands" in caplog.text


# ── T2 ──────────────────────────────────────────────────────────────────────
class TestBoundaryHook:
    def test_crossing_atendimento_to_negociacao_is_a_handoff(self, world):
        supervisao_on(world)
        atendimento(world, etapa="negociacao")
        m = movimento(world, "m1", "a1", "proposta_recebida", "negociacao")
        row = h.ao_movimento(world.sw, ORG_ID, m)
        assert row and row["de_bloco"] == "atendimento" and row["para_bloco"] == "negociacao"
        assert row["gatilho"] == "movimento_etapa" and row["origem_evento"] == "m1" and row["lead_id"] == "lead-1"
        assert row["created_at"] == T0

    def test_a_move_inside_one_block_is_not_a_handoff(self, world):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        assert h.ao_movimento(world.sw, ORG_ID, movimento(world, "m1", "a1", "qualificacao", "visitas")) is None
        assert handoffs(world) == []

    def test_replay_is_a_no_op_and_off_writes_nothing(self, world):
        atendimento(world, etapa="negociacao")
        m = movimento(world, "m1", "a1", "proposta_recebida", "negociacao")
        assert h.ao_movimento(world.sw, ORG_ID, m) is None and handoffs(world) == []  # off
        supervisao_on(world)
        h.ao_movimento(world.sw, ORG_ID, m)
        h.ao_movimento(world.sw, ORG_ID, m)
        assert len(handoffs(world)) == 1

    def test_processos_move_juridico_to_financeiro_points_at_the_atendimento(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        processo(world, etapa="financiamento_escritura")
        row = h.ao_movimento(world.sw, ORG_ID, movimento(world, "m1", "p1", "assinatura", "financiamento_escritura", pipeline="processos_venda"))
        assert (row["de_bloco"], row["para_bloco"], row["atendimento_id"]) == ("juridico", "financeiro", "a1")

    def test_apos_mover_finds_the_movement_move_card_wrote(self, world):
        supervisao_on(world)
        atendimento(world, etapa="negociacao")
        movimento(world, "m1", "a1", "proposta_recebida", "negociacao")
        row = h.apos_mover(world.sw, ORG_ID, "funil", "a1", stage_id("negociacao"))
        assert row["origem_evento"] == "m1"
        assert h.apos_mover(world.sw, ORG_ID, "funil", "a1", stage_id("visitas")) is None  # no movement = a reorder


class TestAceiteMovement:
    def test_accept_writes_the_entry_movement_and_the_juridico_handoff(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        out = aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)
        (mov,) = world.sw.table("pipeline_movimentos").inserted_payloads
        assert mov == {"org_id": ORG_ID, "pipeline": "processos_venda", "entidade_id": out["processo"]["id"],
                       "de_etapa_id": None, "para_etapa_id": stage_id("elaboracao_contrato", "processos_venda"),
                       "responsavel_id": OWNER_ID, "motivo": "aceite_proposta"}
        (row,) = handoffs(world)
        assert (row["de_bloco"], row["para_bloco"], row["atendimento_id"]) == ("negociacao", "juridico", "a1")

    def test_accept_with_supervision_off_still_writes_the_movement_only(self, world):
        atendimento(world, etapa="proposta_decisao")
        aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)
        assert len(world.sw.table("pipeline_movimentos").inserted_payloads) == 1 and handoffs(world) == []

    def test_accept_without_actor_still_accepts_and_logs_the_missing_movement(self, world, caplog):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        with caplog.at_level(logging.ERROR):
            out = aceitar_proposta(world.sw, ORG_ID, "a1", None)
        assert out["already_accepted"] is False
        assert world.sw.table("pipeline_movimentos").inserted_payloads == [] and "without an actor" in caplog.text

    def test_a_repeat_accept_writes_no_second_movement(self, world):
        atendimento(world, etapa="proposta_decisao")
        aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)
        assert aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)["already_accepted"] is True
        assert len(world.sw.table("pipeline_movimentos").inserted_payloads) == 1


# ── status machine (§2.3) ───────────────────────────────────────────────────
def _handoff(world, hid="h1", *, created_at=T0, atendimento_id="a1", status="emitido"):
    world.sw.table("atendimento_handoffs").insert({
        "id": hid, "org_id": ORG_ID, "de_bloco": "sdr", "para_bloco": "atendimento", "gatilho": "novo_lead",
        "origem_evento": f"ev-{hid}", "atendimento_id": atendimento_id, "status": status, "created_at": created_at,
        "assumido_at": None, "expirado_at": None}).execute()


def _status(world, hid="h1"):
    return next(r for r in handoffs(world) if r["id"] == hid)


class TestStatusMachine:
    def test_the_next_move_on_the_card_assumes_the_open_handoff(self, world):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world)
        h.ao_movimento(world.sw, ORG_ID, movimento(world, "m2", "a1", "qualificacao", "visitas", created_at="2026-10-19T13:00:00+00:00"))
        row = _status(world)
        assert row["status"] == "assumido" and row["assumido_at"] == "2026-10-19T13:00:00+00:00"

    def test_the_move_that_creates_a_handoff_does_not_assume_it(self, world):
        supervisao_on(world)
        atendimento(world, etapa="negociacao")
        h.ao_movimento(world.sw, ORG_ID, movimento(world, "m1", "a1", "proposta_recebida", "negociacao"))
        assert handoffs(world)[0]["status"] == "emitido"

    def test_a_late_signal_is_not_back_filled(self, world):
        supervisao_on(world, horas=2)
        atendimento(world, etapa="visitas")
        _handoff(world)
        h.ao_movimento(world.sw, ORG_ID, movimento(world, "m2", "a1", "qualificacao", "visitas", created_at="2026-10-19T15:00:00+00:00"))
        assert _status(world)["status"] == "emitido"
        assert h.expirar_vencidos(world.sw, ORG_ID, agora=datetime(2026, 10, 19, 15, 1, tzinfo=timezone.utc)) == 1
        row = _status(world)
        assert row["status"] == "expirado" and row["assumido_at"] is None and row["expirado_at"].startswith("2026-10-19T15:01")

    def test_sweep_detects_a_human_note_and_ignores_julias_notes(self, world):
        supervisao_on(world)
        atendimento(world)
        _handoff(world)
        world.sw.table("cliente_notas").insert({"id": "n0", "org_id": ORG_ID, "cliente_id": "cli-a1", "autor_id": None,
                                                 "tipo": "comentario", "corpo": "julia", "created_at": "2026-10-19T12:30:00+00:00"}).execute()
        assert h.detectar_assumidos(world.sw, ORG_ID) == 0
        world.sw.table("cliente_notas").insert({"id": "n1", "org_id": ORG_ID, "cliente_id": "cli-a1", "autor_id": OWNER_ID,
                                                 "tipo": "comentario", "corpo": "liguei", "created_at": "2026-10-19T14:00:00+00:00"}).execute()
        assert h.detectar_assumidos(world.sw, ORG_ID) == 1
        assert _status(world)["assumido_at"] == "2026-10-19T14:00:00+00:00"

    def test_sweep_detects_a_move_on_the_processo_card(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        processo(world)
        _handoff(world)
        movimento(world, "m9", "p1", "elaboracao_contrato", "analise_partes", pipeline="processos_venda", created_at="2026-10-19T12:10:00+00:00")
        assert h.varrer(world.sw, ORG_ID, agora=datetime(2026, 10, 19, 13, tzinfo=timezone.utc)) == {"assumidos": 1, "expirados": 0}

    def test_terminal_states_never_change_and_off_is_a_no_op(self, world):
        atendimento(world)
        _handoff(world, status="emitido")
        late = datetime(2026, 10, 25, tzinfo=timezone.utc)
        assert h.varrer(world.sw, ORG_ID, agora=late) == {"assumidos": 0, "expirados": 0}  # supervision off
        supervisao_on(world)
        assert h.varrer(world.sw, ORG_ID, agora=late)["expirados"] == 1
        h.ao_movimento(world.sw, ORG_ID, movimento(world, "m3", "a1", "qualificacao", "visitas", created_at="2026-10-19T13:00:00+00:00"))
        assert _status(world)["status"] == "expirado"


# ── T2 through the funnel events (`pipeline.funil_eventos`) ─────────────────
def _titular(world, cliente_id="cli-a1"):
    world.sw.set_table_data("clientes", [{
        "id": cliente_id, "org_id": ORG_ID, "nome": "Luciano", "nome_completo": "Luciano Mauricio", "nome_oficial": None,
        "celular": "+5511999998888", "chave_canonica": None, "chave_tipo": None, "email": None,
        "data_nascimento": None, "profissao": None, "genero": None}])
    world.sw.set_table_data("cliente_documentos", [])
    world.sw.set_table_data("cliente_documento_checklist", [])


def test_proposta_aceita_event_records_both_boundaries(world):
    from app.modules.pipeline.funil_eventos import mover_por_evento

    supervisao_on(world)
    _titular(world)
    atendimento(world, etapa="proposta_recebida")
    out = mover_por_evento(world.sw, ORG_ID, "a1", "proposta_aceita", OWNER_ID)
    assert out["moveu"] is True and out["aceite"]["already_accepted"] is False
    pares = sorted((r["de_bloco"], r["para_bloco"]) for r in handoffs(world))
    assert pares == [("atendimento", "negociacao"), ("negociacao", "juridico")]

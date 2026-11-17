"""Lais study S3 + S4: the lead card note carries temperature, listings of interest and intent; the reengage cadence defaults
to 15 min then 240 min. Seams are the mock DB the other Julia suites use; nothing of ours is patched. No personal data."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services import julia_contatos_service as contatos
from app.services import julia_envio_service as envio
from app.services import julia_nota_lead as nota
from app.services import julia_reengajamento_service as reeng

from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID as ORG, World

FONE = "+5511988887777"


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in ("julia_eventos", "julia_interacoes"):
        w.sw.set_table_data(t, [])
    return w


def _contato(world: World, **over) -> dict:
    c = contatos.obter_ou_criar_contato(world.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
                                        telefone_e164=FONE, nome="Ana Exemplo")
    if over:
        contatos.atualizar_contato(world.sw, c["id"], over)
    return world.contato(LEAD_CHAT)


def _evento(world: World, contato: dict, tipo: str, payload: dict, ts: str) -> None:
    world.sw.table("julia_eventos").insert({
        "id": str(uuid4()), "org_id": ORG, "tipo": tipo, "contato_id": contato["id"], "payload": payload, "created_at": ts,
    }).execute()


class TestTemperatura:
    def test_agent_value_wins(self):
        assert nota.temperatura({"slots": {"temperatura": "Quente"}}, "frio", None) == "quente"

    def test_intent_is_hot(self):
        assert nota.temperatura({"slots": {}}, "qualificado", "visita") == "quente"

    @pytest.mark.parametrize("gatilho,esperado", [("frio", "frio"), ("invalido", "frio"), ("qualificado", "morno"), ("manual", "morno")])
    def test_derived_from_the_trigger(self, gatilho, esperado):
        assert nota.temperatura({"slots": {}}, gatilho, None) == esperado

    def test_an_unknown_agent_value_is_ignored(self):
        assert nota.temperatura({"slots": {"temperatura": "fervendo"}}, "qualificado", None) == "morno"


class TestIntencaoEImoveis:
    def test_visit_trigger_and_event_both_mean_visit(self):
        assert nota.intencao({"slots": {}}, "visita", []) == "visita"
        assert nota.intencao({"slots": {}}, "qualificado", [{"tipo": "intencao_visita", "payload": {}}]) == "visita"

    def test_handoff_motive_codes_map_to_an_intent(self):
        ev = [{"tipo": "handoff", "payload": {"motivo_codigo": "proposta"}}]
        assert nota.intencao({"slots": {}}, "qualificado", ev) == "proposta"
        assert nota.intencao({"slots": {}}, "qualificado", [{"tipo": "handoff", "payload": {"motivo_codigo": "outro"}}]) is None

    def test_listings_are_distinct_ordered_and_capped(self):
        c = {"slots": {"codigo_imovel": "ap1"}, "codigo_imovel_campanha": "AP1"}
        ev = [{"tipo": "imovel_consultado", "payload": {"codigos": [f"AP{i}" for i in range(2, 9)]}}]
        assert nota.imoveis_de_interesse(c, ev) == ["AP1", "AP2", "AP3", "AP4", "AP5"]


class TestNotaNoCartao:
    def test_the_note_has_temperature_listings_and_intent(self, world):
        c = _contato(world, operacao="compra", slots={"orcamento": "500000", "codigo_imovel": "AP0042"})
        _evento(world, c, "imovel_consultado", {"ferramenta": "buscar_imoveis", "codigos": ["AP0100"]}, "2026-11-17T10:00:00+00:00")
        _evento(world, c, "intencao_visita", {"codigo": "AP0042"}, "2026-11-17T10:05:00+00:00")
        texto = envio.montar_nota(world.sw, c, "qualificado")
        assert "- temperatura: quente" in texto
        assert "- imóveis de interesse: AP0042, AP0100" in texto
        assert "- intenção: quer visitar o imóvel" in texto
        assert "orcamento: 500000" in texto

    def test_a_plain_lead_is_morno_without_listing_or_intent_lines(self, world):
        c = _contato(world)
        texto = envio.montar_nota(world.sw, c, "qualificado")
        assert "- temperatura: morno" in texto and "imóveis de interesse" not in texto and "intenção" not in texto

    def test_an_unreadable_event_log_never_blocks_the_note(self, world):
        class Quebrado:
            def table(self, nome):
                if nome == "julia_eventos":
                    raise RuntimeError("down")
                return world.sw.table(nome)

        c = _contato(world)
        assert "- temperatura: morno" in envio.montar_nota(Quebrado(), c, "qualificado")


class TestReengajamentoPadrao:
    def test_default_cadence_is_15_minutes_then_240_inside_08_to_20(self, world):
        cfg = reeng.obter_config(world.sw, ORG)
        assert (cfg["minutos_intervalo"], cfg["horas_intervalo"] * 60) == (15, 240)
        assert reeng.HORA_ABERTURA == 8 and reeng.HORA_FECHAMENTO == 20
        assert 15 in reeng.MINUTOS_VALIDOS and cfg["horas_intervalo"] in reeng.HORAS_VALIDAS

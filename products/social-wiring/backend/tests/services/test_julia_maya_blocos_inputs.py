"""maya-blocks S2 data gaps closed for Maya's sdr scorecard (CONTRACT §3.2):

  * `julia_interacoes.primeira_resposta_at` -- stamped ONCE per episode, on the first reply (Julia's reply turn, or a
    human from the inbox); a re-engagement is not a response.
  * the `handoff` Julia event -- payload `{motivo_codigo}`, a CLOSED code, never the model's free text; it does not
    double-notify (outside the fan-out).

Every external seam is a Fake (mock DB, FakeWahaClient, FakeAgentsClient, fakeredis); nothing of ours is patched."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.clients.agents import FakeAgentsClient, HandoffAction, TurnResult
from app.services import julia_agente_service as julia
from app.services import julia_contatos_service as contatos
from app.services.julia_lead_turn_service import process_lead_batch

from tests.support.julia_world import LEAD_CHAT, ORG_ID, World, buffer_lead

CID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")  # the privacy disclosure's link


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    return w


def _ok(*partes, status="respondido", actions=()):
    return TurnResult(conversation_id=CID, partes=tuple(partes), status=status, actions=tuple(actions))


async def _turno(world: World, texto: str, mid: str) -> None:
    key = buffer_lead(world, LEAD_CHAT, [texto], ids=[mid])
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps())


class TestPrimeiraResposta:
    @pytest.mark.asyncio
    async def test_the_first_reply_stamps_the_episode_once(self, world):
        world.agents = FakeAgentsClient([_ok("oi!"), _ok("de novo")])
        await _turno(world, "oi", "m1")
        (ep,) = world.rows("julia_interacoes")
        primeira = ep["primeira_resposta_at"]
        assert primeira and primeira >= ep["iniciada_at"]
        # G1: Julia's reply is stamped on the AGENT column (the sdr.v2 TPR input), never on the human one
        assert ep["primeira_resposta_agente_at"] == primeira and not ep.get("primeira_resposta_humana_at")
        await _turno(world, "e ai", "m2")
        (ep,) = world.rows("julia_interacoes")
        assert ep["primeira_resposta_at"] == primeira and ep["primeira_resposta_agente_at"] == primeira

    @pytest.mark.asyncio
    async def test_a_silent_turn_stamps_nothing(self, world):
        world.agents = FakeAgentsClient([_ok(status="silencio")])
        await _turno(world, "...", "m1")
        (ep,) = world.rows("julia_interacoes")
        assert ep.get("primeira_resposta_at") is None

    def test_the_service_writes_once_per_kind_and_needs_an_open_episode(self, world):
        contato = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=world.seed_connection()["id"], chat_id="x@c.us")
        assert contatos.registrar_primeira_resposta(world.sw, ORG_ID, contato["id"], por="agente") is False  # no episode yet
        contatos.abrir_interacao(world.sw, ORG_ID, contato, agora=datetime(2026, 10, 19, 12, tzinfo=timezone.utc))
        # G1: a human reply is stamped on ITS column, never on Julia's
        assert contatos.registrar_primeira_resposta(world.sw, ORG_ID, contato["id"], por="humano",
                                                    agora=datetime(2026, 10, 19, 12, 1, tzinfo=timezone.utc))
        (ep,) = world.rows("julia_interacoes", contato_id=contato["id"])
        assert ep["primeira_resposta_humana_at"].startswith("2026-10-19T12:01") and not ep.get("primeira_resposta_agente_at")
        assert contatos.registrar_primeira_resposta(world.sw, ORG_ID, contato["id"], por="humano") is False
        # ...and Julia's own reply, later, still stamps the agent column (the human one did not use it up)
        assert contatos.registrar_primeira_resposta(world.sw, ORG_ID, contato["id"], por="agente",
                                                    agora=datetime(2026, 10, 19, 12, 5, tzinfo=timezone.utc))
        assert contatos.registrar_primeira_resposta(world.sw, ORG_ID, contato["id"], por="agente") is False
        (ep,) = world.rows("julia_interacoes", contato_id=contato["id"])
        assert ep["primeira_resposta_agente_at"].startswith("2026-10-19T12:05")
        assert ep["primeira_resposta_at"].startswith("2026-10-19T12:01")  # legacy column: first of either kind

    def test_an_unknown_kind_is_refused(self, world):
        with pytest.raises(ValueError):
            contatos.registrar_primeira_resposta(world.sw, ORG_ID, "c", por="bot")


class TestFalhaDeRegistro:
    """G4: a first-response stamp that fails does not undo the reply, and is no longer a quiet log line."""

    def test_a_failing_agent_stamp_raises_a_visible_alert_and_never_raises(self, world, caplog):
        import logging

        from app.services import julia_lead_turn_service as lead
        from tests.support.falha_injetada import ClienteQueFalha
        from tests.support.julia_world import OWNER_ID

        world.notificar_via_sink()
        contato = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=world.seed_connection()["id"], chat_id="x@c.us")
        deps = world.deps(scoped=ClienteQueFalha(world.sw, {"julia_interacoes"}))
        with caplog.at_level(logging.ERROR):
            lead._registrar_primeira_resposta(deps, ORG_ID, contato)  # does not raise
        (alerta,) = world.rows("julia_eventos", tipo="supervisao_falha")
        assert alerta["payload"]["codigo"] == "primeira_resposta_agente" and alerta["payload"]["ids"] == {"contato_id": contato["id"]}
        assert [n["user_id"] for n in world.notifications()] == [OWNER_ID]
        assert "the reply IS out" in caplog.text


class TestHandoffEvent:
    @pytest.mark.asyncio
    async def test_a_handoff_emits_the_closed_motivo_code_and_only_one_notification(self, world):
        world.agents = FakeAgentsClient([_ok("Vou chamar um corretor.", status="handoff",
                                             actions=[HandoffAction(motivo="O lead pediu para falar com um corretor")])])
        await _turno(world, "quero falar com humano", "m1")
        evs = world.rows("julia_eventos", tipo="handoff")
        assert len(evs) == 1 and evs[0]["payload"] == {"motivo_codigo": "pedido_do_lead"}
        assert evs[0]["contato_id"] == world.contato()["id"]
        assert len(world.notifications()) == 1  # the handoff's own notification; the event is not fanned out


@pytest.mark.parametrize("texto,codigo", [
    ("O lead pediu para falar com um humano", "pedido_do_lead"),
    ("Cliente RECLAMOU do atendimento, quer falar com alguém", "reclamacao"),
    ("Pergunta fora do escopo (financiamento rural)", "fora_do_escopo"),
    ("Não sei responder sobre o condomínio", "fora_do_escopo"),
    ("", "outro"),
    (None, "outro"),
    ("assunto diverso", "outro"),
])
def test_motivo_codigo_is_a_closed_vocabulary(texto, codigo):
    assert julia.motivo_codigo_do_handoff(texto) == codigo
    assert codigo in julia.MOTIVOS_HANDOFF

"""Julia v2 A-RT2 for the Studio UI: the channel conversation list carries ``resultado`` + participant states, and a
Studio-JWT-readable thread read says pause vs resume correctly. Strict 401/403."""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.integrations.llm import FakeProvider

from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import call, say, step
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, seed_org_role

LIST = "/api/conversations/channel?agent_key=julia"


def _um_turno(chan):
    chan.seed_agent()
    chan.use_provider(FakeProvider(tool_responses=[
        step(call("registrar_perfil", itens=[{"criterio": "operacao", "valor": "compra", "trecho": "quero comprar"}])),
        say("Entendi! Que tipo de imóvel você procura?"),
    ]))
    body = chan.turn(turn_body("quero comprar um imóvel")).json()
    assert body["status"] == "respondido", body
    return UUID(body["thread_id"])


def _usuario(chan, org_role: str, platform: bool = False):
    chan.rt.client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": org_role,
        "role": "admin" if platform else "user"}])


class TestChannelListResultado:
    def test_items_carry_stage_score_violation_count_and_participants(self, chan):
        tid = _um_turno(chan)
        _usuario(chan, "owner")
        r = chan.rt.client.get(LIST)
        assert r.status_code == 200, r.text
        [item] = r.json()["items"]
        assert item["id"] == str(tid)
        assert set(item["resultado"]) == {"estagio", "score", "violacoes_count"}
        assert item["resultado"]["estagio"] and item["resultado"]["violacoes_count"] >= 0
        assert item["participantes"] == [{"agent_key": "julia", "estado": "ativo"}]

    def test_items_carry_the_leads_latest_opt_out_event_so_the_thread_view_can_banner_it(self, chan):
        tid = _um_turno(chan)
        _usuario(chan, "owner")
        [item] = chan.rt.client.get(LIST).json()["items"]
        assert item["opt_out_evento"] is None
        thread = chan.rt.stores.conversations.get(DEFAULT_ORG_ID, tid)
        ref = chan.threads.get_lead_ref(DEFAULT_ORG_ID, thread.lead_ref_id).ref_externa
        chan.threads.registrar_opt_out_evento(DEFAULT_ORG_ID, ref, motivo="pediu para parar", origem="operador")
        [item] = chan.rt.client.get(LIST).json()["items"]
        assert item["opt_out_evento"]["motivo"] == "pediu para parar" and item["opt_out_evento"]["origem"] == "operador"

    def test_user_conversations_keep_both_fields_null(self, chan):
        chan.seed_agent()
        chan.rt.stores.agents.seed_legacy_chat_agent(DEFAULT_ORG_ID)
        _usuario(chan, "owner")
        r = chan.rt.client.post("/api/conversations", json={"agent_key": "bia"})
        assert r.status_code in (200, 201), r.text
        assert r.json()["resultado"] is None and r.json()["participantes"] is None

    def test_auth_boundary_stays_admin_only(self, chan):
        chan.seed_agent()
        assert chan.client.raw().get(LIST).status_code == 401
        _usuario(chan, "member")
        assert chan.rt.client.get(LIST).status_code == 403


class TestStudioThread:
    def test_participant_states_for_the_pause_resume_toggle(self, chan):
        tid = _um_turno(chan)
        _usuario(chan, "owner")
        r = chan.rt.client.get(f"/api/studio/threads/{tid}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {
            "thread_id", "channel", "participantes", "ultimo_turno_em", "ultima_mensagem_lead_em", "criado_em"}
        assert [(p["agent_key"], p["estado"]) for p in body["participantes"]] == [("julia", "ativo")]
        # pause it (as SW would) and read again: the FE must show "resume"
        agent = chan.agent
        chan.threads.transicionar(DEFAULT_ORG_ID, tid, agent.id, de=("ativo",), para="pausado", ator_tipo="usuario", motivo="x")
        body = chan.rt.client.get(f"/api/studio/threads/{tid}").json()
        assert body["participantes"][0]["estado"] == "pausado"

    def test_boundaries(self, chan):
        tid = _um_turno(chan)
        assert chan.client.raw().get(f"/api/studio/threads/{tid}").status_code == 401
        _usuario(chan, "member")
        assert chan.rt.client.get(f"/api/studio/threads/{tid}").status_code == 403
        _usuario(chan, "owner")
        assert chan.rt.client.get(f"/api/studio/threads/{UUID(int=99)}").status_code == 404

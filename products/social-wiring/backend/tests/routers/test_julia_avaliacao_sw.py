"""Owner 2026-11-05: the testing phase is AGENTS' evaluation mode only (SW has no allowlist). SW reads `modo_avaliacao` +
`avaliacao_usuarios` (user ids) from `GET /api/channels/agents/{key}/controle` for ONE reason: the owner's own number is an org
member's, so SW's `equipe` filter would stop it before it reached agents' gate. A member on the list WHILE the mode is ON is a lead;
every other member stays staff; an unreadable controle keeps staff (fail closed). Seams: the shared `Rt` scene + `FakeAgentsClient`
(its `controle` / `_controle` are the real client's shape)."""
from __future__ import annotations

import asyncio

import pytest

from app.clients.agents import AgentsTimeout, ControleInfo, FakeAgentsClient, parse_controle
from app.services import julia_avaliacao_service as aval
from app.services import julia_staff_service as staff
from tests.routers.test_julia_agente_routing import (  # noqa: F401  (fixtures + builders of the shared scene)
    LEAD_CHAT, ORG_ID, OWNER_ID, Rt, _julia_scene, _msg, override_settings_factory, rt,
)
from tests.routers.test_julia_linha_roteamento import MEMBER_CHAT, STAFF_CHAT, STAFF_PHONE
from tests.support.julia_world import ADMIN_ID


def _controle(*usuarios, modo_avaliacao=True) -> ControleInfo:
    return ControleInfo(agent_key="julia", modo="ligado", aceita_novos_leads=True,
                        modo_avaliacao=modo_avaliacao, avaliacao_usuarios=tuple(str(u) for u in usuarios))


class TestParse:
    def test_the_controle_body_carries_the_evaluation_fields(self):
        c = parse_controle({"agent_key": "julia", "modo": "ligado", "aceita_novos_leads": True,
                            "modo_avaliacao": True, "avaliacao_usuarios": ["u1", "u2"]})
        assert c.modo_avaliacao is True and c.avaliacao_usuarios == ("u1", "u2")

    def test_an_older_agents_without_the_fields_means_mode_off(self):
        c = parse_controle({"agent_key": "julia", "modo": "ligado", "aceita_novos_leads": True})
        assert c.modo_avaliacao is False and c.avaliacao_usuarios == ()

    @pytest.mark.parametrize("bruto", ["true", 1, None])
    def test_only_a_real_true_turns_the_mode_on(self, bruto):
        c = parse_controle({"agent_key": "julia", "modo": "ligado", "aceita_novos_leads": True,
                            "modo_avaliacao": bruto, "avaliacao_usuarios": ["u1"]})
        assert c.modo_avaliacao is False


class TestServico:
    def test_mode_on_returns_the_listed_ids_mode_off_returns_none(self):
        on = FakeAgentsClient(controle=_controle("u1"))
        assert asyncio.run(aval.usuarios_em_avaliacao(on, ORG_ID, "julia")) == {"u1"}
        off = FakeAgentsClient(controle=_controle("u1", modo_avaliacao=False))
        assert asyncio.run(aval.usuarios_em_avaliacao(off, ORG_ID, "julia")) == frozenset()

    def test_a_read_failure_is_no_bypass_logged_and_never_cached(self, caplog):
        c = FakeAgentsClient(controle=AgentsTimeout("t"))
        with caplog.at_level("ERROR"):
            assert asyncio.run(aval.usuarios_em_avaliacao(c, ORG_ID, "julia")) == frozenset()
        assert "no evaluation bypass" in caplog.text
        c._controle = _controle("u1")  # agents is back: the very next read must see it (a failure was not cached)
        assert asyncio.run(aval.usuarios_em_avaliacao(c, ORG_ID, "julia")) == {"u1"}

    def test_no_client_is_no_bypass_logged(self, caplog):
        with caplog.at_level("ERROR"):
            assert asyncio.run(aval.usuarios_em_avaliacao(None, ORG_ID, "julia")) == frozenset()
        assert "no evaluation bypass" in caplog.text

    def test_the_state_is_read_on_every_call_never_cached_never_latched(self):
        c = FakeAgentsClient(controle=_controle("u1"))
        lidas = []
        original = c.controle

        async def contado(key):
            lidas.append(key)
            return await original(key)

        c.controle = contado
        run = lambda: asyncio.run(aval.usuarios_em_avaliacao(c, ORG_ID, "julia"))
        assert run() == {"u1"}
        c._controle = _controle("u1", modo_avaliacao=False)   # OFF: nobody is restricted / bypassed
        assert run() == frozenset()
        c._controle = _controle("u1")                         # ON again: effective at once
        assert run() == {"u1"}
        assert len(lidas) == 3

    def test_a_julia_staff_number_is_never_an_evaluation_member(self):
        r = staff.Remetente("julia_staff", "Bia", "corretor", "staff:u1")
        assert asyncio.run(aval.membro_em_avaliacao(FakeAgentsClient(controle=_controle("u1")), ORG_ID, "julia", r)) is False


class TestThroughTheWebhook:
    def test_a_member_on_the_evaluation_list_is_a_lead_and_reaches_julia(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=MEMBER_CHAT, mid="av1", body="teste"), signed=True)
        assert len(rt.lead_memory(MEMBER_CHAT)) == 1
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "lead"

    def test_a_member_NOT_on_the_list_stays_staff_even_with_the_mode_on(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(ADMIN_ID)
        rt.post(_msg(chat=MEMBER_CHAT, mid="av2", body="teste"), signed=True)
        assert rt.lead_memory(MEMBER_CHAT) == [] and rt.w.agents.turns == []
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "equipe"

    def test_a_listed_member_with_the_mode_OFF_stays_staff(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID, modo_avaliacao=False)
        rt.post(_msg(chat=MEMBER_CHAT, mid="av3", body="teste"), signed=True)
        assert rt.lead_memory(MEMBER_CHAT) == [] and rt.w.chat_row(MEMBER_CHAT)["categoria"] == "equipe"

    def test_an_unreadable_controle_keeps_the_member_staff(self, rt, caplog):
        _julia_scene(rt)
        rt.w.agents._controle = AgentsTimeout("down")
        with caplog.at_level("ERROR"):
            rt.post(_msg(chat=MEMBER_CHAT, mid="av4", body="teste"), signed=True)
        assert rt.lead_memory(MEMBER_CHAT) == [] and rt.w.agents.turns == []
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "equipe"
        assert "no evaluation bypass" in caplog.text

    def test_a_julia_staff_row_is_never_let_through_by_the_list(self, rt):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.w.agents._controle = _controle(OWNER_ID, ADMIN_ID)
        rt.post(_msg(chat=STAFF_CHAT, mid="av5", body="oi"), signed=True)
        assert rt.lead_memory(STAFF_CHAT) == [] and rt.w.chat_row(STAFF_CHAT)["categoria"] == "equipe"

    def test_flipping_the_mode_is_live_for_the_next_message(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=MEMBER_CHAT, mid="fl1", body="a"), signed=True)
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "lead"
        rt.w.agents._controle = _controle(OWNER_ID, modo_avaliacao=False)
        rt.post(_msg(chat=MEMBER_CHAT, mid="fl2", body="b"), signed=True)
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "equipe"
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=MEMBER_CHAT, mid="fl3", body="c"), signed=True)
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "lead"

    def test_each_lead_inbound_reads_the_state_live_once_never_cached(self, rt):
        _julia_scene(rt)
        lidas = []
        original = rt.w.agents.controle

        async def contado(key):
            lidas.append(key)
            return await original(key)

        rt.w.agents.controle = contado
        rt.post(_msg(chat=LEAD_CHAT, mid="av6"), signed=True)
        rt.post(_msg(chat=LEAD_CHAT, mid="av7"), signed=True)
        assert lidas == ["julia", "julia"] and len(rt.lead_memory()) == 2


class TestBlockedAtIntake:
    """Owner 2026-11-05: with testing ON a non-listed contact's message never reaches Julia -- blocked at SW's intake, before agents."""

    def _zero_para_o_agents(self, rt):
        a = rt.w.agents
        assert a.turns == [] and a.appended == [] and a.opt_ins == [] and a.decisoes == []
        assert rt.w.waha.sent_messages == [], "zero outbound to ANY number, the owner's included"
        assert rt.lead_memory() == [] and not rt.lead_keys_buffered(), "nothing buffered for a turn (so no LLM)"
        assert rt.w.rows("julia_contatos") == [] and rt.w.rows("julia_interacoes") == []

    def test_a_non_listed_inbound_with_testing_on_makes_no_agents_turn_no_send_no_thread(self, rt, caplog):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID)
        with caplog.at_level("INFO"):
            assert rt.post(_msg(chat=LEAD_CHAT, mid="bk1", body="segredo do estranho"), signed=True).status_code == 200
        self._zero_para_o_agents(rt)
        assert len(rt.w.messages()) == 1, "the SW inbox still shows what WAHA shows"
        assert "reason=restrito_avaliacao" in caplog.text and "segredo" not in caplog.text  # metadata only

    def test_an_unreadable_state_blocks_the_inbound(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = AgentsTimeout("down")
        rt.post(_msg(chat=LEAD_CHAT, mid="bk2"), signed=True)
        self._zero_para_o_agents(rt)

    def test_no_agents_client_blocks_the_inbound(self, rt):
        from app.main import app
        from app.routers.julia_agente_router import get_agents_client_factory

        _julia_scene(rt)
        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: None)
        rt.post(_msg(chat=LEAD_CHAT, mid="bk3"), signed=True)
        self._zero_para_o_agents(rt)

    def test_a_blocked_message_is_not_in_her_context_after_testing_goes_off(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=LEAD_CHAT, mid="bk4", body="mensagem bloqueada"), signed=True)
        self._zero_para_o_agents(rt)
        rt.w.agents._controle = _controle(OWNER_ID, modo_avaliacao=False)        # testing ends
        rt.post(_msg(chat=LEAD_CHAT, mid="bk5", body="agora sim"), signed=True)
        buffered = rt.lead_memory()
        assert [m["text"] for m in buffered] == ["agora sim"], "the earlier blocked message never surfaces"

    def test_off_then_on_again_the_same_stranger_is_blocked_again(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID, modo_avaliacao=False)
        rt.post(_msg(chat=LEAD_CHAT, mid="fp1", body="primeira"), signed=True)
        assert len(rt.lead_memory()) == 1
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=LEAD_CHAT, mid="fp2", body="segunda"), signed=True)
        assert [m["text"] for m in rt.lead_memory()] == ["primeira"], "restricted again at once"

    def test_the_listed_owner_still_gets_through(self, rt):
        _julia_scene(rt)
        rt.w.agents._controle = _controle(OWNER_ID)
        rt.post(_msg(chat=MEMBER_CHAT, mid="ok1", body="sou eu"), signed=True)
        assert len(rt.lead_memory(MEMBER_CHAT)) == 1

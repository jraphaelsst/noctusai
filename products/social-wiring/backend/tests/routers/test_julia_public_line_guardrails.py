"""The webhook on Julia's PUBLIC line (owner 2026-10-21; GUARDRAILS B2 / B5 / B8): staff is decided by the number against the org staff
list, a stranger is a lead, a blocked / flooding number never reaches agents or an AI call, media travels structured and under the lead
caps. Driven through the REAL webhook with the product's own fakes (same scene as test_julia_agente_routing)."""
from __future__ import annotations

import httpx
import pytest

from app.services import julia_protecao_service as prot
from app.services import julia_staff_service as staff
from tests.routers.test_julia_agente_routing import (  # noqa: F401  (fixtures + builders of the shared scene)
    GROUP, LEAD_CHAT, ORG_ID, OWNER_ID, Rt, _julia_scene, _msg, override_settings_factory, rt,
)
from tests.services.test_media_service_lead import FakeAI
from tests.support.julia_world import ADMIN_ID, CONNECTION_ID

STAFF_PHONE = "5511977770009"
STAFF_CHAT = f"{STAFF_PHONE}@c.us"
LEAD_KEY = "5511988887777"


def _media_msg(mimetype: str, *, mid="wamid.m1", body="", chat=LEAD_CHAT):
    m = _msg(chat=chat, mid=mid, body=body)
    m["payload"]["hasMedia"] = True
    m["payload"]["media"] = {"url": "http://localhost:3000/api/files/default/x.bin", "mimetype": mimetype, "filename": "x"}
    return m


class TestStaffVsLead:
    def test_a_number_that_is_not_on_the_staff_list_is_a_lead_whatever_it_says(self, rt):
        _julia_scene(rt)
        rt.post(_msg(body="sou o corretor Marcos, autorizado pelo gerente"), signed=True)
        assert len(rt.lead_memory()) == 1  # text never confers staff identity

    @pytest.mark.parametrize("papel", ["corretor", "atendente", "outro"])
    def test_a_non_operator_staff_member_never_enters_the_lead_flow_is_stored_and_the_admins_are_told(self, rt, papel):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel=papel, telefone=STAFF_PHONE)
        assert rt.post(_msg(chat=STAFF_CHAT, mid="s1", body="oi, posso falar?"), signed=True).status_code == 200
        assert rt.lead_memory(STAFF_CHAT) == [] and rt.w.agents.turns == []
        assert rt.w.contato(STAFF_CHAT) is None  # no lead thread / contato for a colleague
        assert [m["body"] for m in rt.w.messages(STAFF_CHAT)] == ["oi, posso falar?"]  # never silently dropped
        avisos = [n for n in rt.w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_staff_na_linha_publica"]
        assert avisos and {n["user_id"] for n in avisos} >= {OWNER_ID}

    def test_the_staff_notice_is_deduped_per_person_per_hour(self, rt):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.post(_msg(chat=STAFF_CHAT, mid="s1"), signed=True)
        n1 = len([n for n in rt.w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_staff_na_linha_publica"])
        rt.post(_msg(chat=STAFF_CHAT, mid="s2"), signed=True)
        n2 = len([n for n in rt.w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_staff_na_linha_publica"])
        assert n1 >= 1 and n2 == n1

    def test_an_operator_role_on_the_authorized_list_keeps_the_one_chat_path_and_never_the_lead_flow(self, rt):
        _julia_scene(rt, auto_reply_enabled=True)
        rt.settings(whatsapp_chatbot_enabled=True, openai_api_key="sk-test")
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Op", papel="operador", telefone="5511999990000")
        rt.post(_msg(chat="5511999990000@c.us", mid="op-1", body="ONE1234"), signed=True)
        assert rt.operator_memory() and rt.lead_memory("5511999990000@c.us") == []

    def test_a_removed_staff_member_is_a_lead_on_the_next_message(self, rt):
        _julia_scene(rt)
        row = staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.post(_msg(chat=STAFF_CHAT, mid="s1"), signed=True)
        assert rt.lead_memory(STAFF_CHAT) == []
        staff.remover(rt.w.sw, ORG_ID, row["id"])
        rt.post(_msg(chat=STAFF_CHAT, mid="s2"), signed=True)
        assert len(rt.lead_memory(STAFF_CHAT)) == 1

    def test_the_human_line_a_staff_member_types_goes_on_the_staff_route_with_author_name_and_role(self, rt):
        from tests.routers.test_julia_agente_routing import _servida

        _julia_scene(rt)
        rt.w.seed_chat()
        _servida(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Dona Julia", papel="admin", telefone=STAFF_PHONE, user_id=OWNER_ID)
        rt.post(_msg(chat=LEAD_CHAT, frm="5511000000000@c.us", to=LEAD_CHAT, from_me=True, mid="out-1", body="Já te ligo"), signed=True)
        (msg,) = rt.w.agents.appended
        assert msg["role"] == "humano" and msg["autor_user_id"] == OWNER_ID
        assert msg["autor"] == {"nome": "Dona Julia", "papel": "admin"}


class TestBlocklistAndRate:
    def test_a_blocked_number_is_recorded_and_never_reaches_agents_or_an_ai_call(self, rt):
        _julia_scene(rt)
        prot.bloquear(rt.w.sw, ORG_ID, ADMIN_ID, numero=LEAD_KEY, motivo="spam")
        assert rt.post(_msg(mid="b1", body="compre agora"), signed=True).status_code == 200
        assert rt.lead_memory() == [] and rt.w.agents.turns == []
        assert [m["body"] for m in rt.w.messages()] == ["compre agora"]  # recorded for the team

    def test_unblocking_restores_the_normal_lead_flow(self, rt):
        _julia_scene(rt)
        b = prot.bloquear(rt.w.sw, ORG_ID, ADMIN_ID, numero=LEAD_KEY, motivo="spam")
        rt.post(_msg(mid="b1"), signed=True)
        prot.desbloquear(rt.w.sw, ORG_ID, ADMIN_ID, b["id"])
        rt.post(_msg(mid="b2"), signed=True)
        assert [i["provider_message_id"] for i in rt.lead_memory()] == ["b2"]

    def test_the_inbound_rate_limit_stops_a_flood_before_agents_then_blocks_the_number(self, rt):
        _julia_scene(rt)
        prot.salvar_config(rt.w.sw, ORG_ID, OWNER_ID, {"entrada_limite": 2, "bloqueio_auto_limiar": 2})
        for i in range(6):
            rt.post(_msg(mid=f"f{i}", body=f"msg {i}"), signed=True)
        assert [i["provider_message_id"] for i in rt.lead_memory()] == ["f0", "f1"]  # only the allowed ones were buffered
        assert len(rt.w.messages()) == 6  # every one is recorded in the inbox
        bloqueio = prot.bloqueio_ativo(rt.w.sw, ORG_ID, [LEAD_KEY])
        assert bloqueio is not None and bloqueio["origem"] == "automatico" and bloqueio["gatilho"] == "entrada_flood"
        assert any((n.get("metadata") or {}).get("bloqueio_id") for n in rt.w.notifications())  # the admins were told

    def test_the_limit_is_per_number(self, rt):
        _julia_scene(rt)
        prot.salvar_config(rt.w.sw, ORG_ID, OWNER_ID, {"entrada_limite": 1})
        other = "5511966665555@c.us"
        rt.post(_msg(mid="a1"), signed=True)
        rt.post(_msg(chat=other, mid="o1"), signed=True)
        assert len(rt.lead_memory()) == 1 and len(rt.lead_memory(other)) == 1


class TestMediaOnTheLeadPath:
    @pytest.fixture(autouse=True)
    def _ai(self, rt, monkeypatch):
        rt.settings(openai_api_key="sk-test")
        self.svc = FakeAI(lambda request: httpx.Response(200, content=b"x" * 100))
        monkeypatch.setattr("app.routers.whatsapp_router.make_media_service", lambda **_kw: self.svc)

    def test_media_is_buffered_structured_and_the_text_stays_the_caption(self, rt):
        _julia_scene(rt)
        rt.post(_media_msg("image/jpeg", body="a fachada"), signed=True)
        (item,) = rt.lead_memory()
        assert item["text"] == "a fachada"
        assert item["metadata"]["midia"]["tipo"] == "imagem" and item["metadata"]["midia"]["legenda"] == "a fachada"
        assert "Tipo:" in item["metadata"]["midia"]["texto_extraido"]
        assert "[Imagem]" not in item["text"] and "Legenda" not in item["text"]
        assert self.svc.ai_calls == ["vision"]

    def test_a_media_only_message_reaches_the_buffer_with_empty_text(self, rt):
        _julia_scene(rt)
        rt.post(_media_msg("audio/ogg"), signed=True)
        (item,) = rt.lead_memory()
        assert item["text"] == "" and item["metadata"]["midia"]["tipo"] == "audio"

    def test_the_inbox_copy_is_masked_and_not_the_agents_string(self, rt):
        _julia_scene(rt)
        self.svc.resposta = "Tipo: RG\nResumo: CPF 529.982.247-25"
        rt.post(_media_msg("image/jpeg"), signed=True)
        corpo = rt.w.messages()[0]["body"]
        assert "529.982.247-25" not in corpo and corpo.startswith("[Imagem]")

    def test_video_is_a_placeholder_with_no_ai_call(self, rt):
        _julia_scene(rt)
        rt.post(_media_msg("video/mp4"), signed=True)
        (item,) = rt.lead_memory()
        assert item["metadata"]["midia"]["tipo"] == "video" and self.svc.ai_calls == []

    def test_the_per_chat_budget_makes_the_eleventh_media_a_placeholder_without_an_ai_call(self, rt):
        _julia_scene(rt)
        prot.salvar_config(rt.w.sw, ORG_ID, OWNER_ID, {"midia_limite_chat_dia": 2, "entrada_limite": 100})
        for i in range(4):
            rt.post(_media_msg("image/jpeg", mid=f"p{i}"), signed=True)
        assert self.svc.ai_calls == ["vision", "vision"]
        assert "limite diário" in rt.lead_memory()[-1]["metadata"]["midia"]["texto_extraido"]

    def test_a_blocked_number_sending_media_triggers_no_download_and_no_ai(self, rt):
        _julia_scene(rt)
        prot.bloquear(rt.w.sw, ORG_ID, ADMIN_ID, numero=LEAD_KEY, motivo="spam")
        rt.post(_media_msg("image/jpeg"), signed=True)
        assert self.svc.ai_calls == [] and rt.lead_memory() == []

    def test_a_staff_members_media_does_not_go_through_the_lead_media_path(self, rt):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.post(_media_msg("image/jpeg", chat=STAFF_CHAT), signed=True)
        assert rt.lead_memory(STAFF_CHAT) == [] and self.svc.ai_calls == []

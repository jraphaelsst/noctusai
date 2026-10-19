"""Meta lead-form lead -> Julia intake (`julia_primeiro_contato_service`) and its leadgen webhook leg.

Seams only: the mock DB, the seed `FakeWahaClient` / `FakeMetaCloudClient` behind the REAL transport factory, the real
connection store over the mock, and `LeadgenWebhookService`'s own DI seam. Fixtures carry no personal data."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.whatsapp import FakeMetaCloudClient
from noctusai_lib.testing import MockSupabaseClient

from app.clients.agents import AgentsTimeout, DecisaoResult, FakeAgentsClient
from app.modules.meta_ads.services.leadgen_webhook_service import (
    STATUS_PROCESSED,
    LeadgenWebhookService,
    ProcessResult,
)
from app.services import julia_primeiro_contato_service as svc
from app.services import julia_transporte as tr
from app.services.whatsapp_connection_store import build_whatsapp_connection_store
from tests.support.julia_world import CONNECTION_ID, ENCRYPTION_KEY, ORG_ID, World

TEL = "+5511988887777"
LEAD = {"id": "lead-1", "full_name": "Ana Teste", "phone": TEL, "answers": {}}


class Cena:
    def __init__(self, world: World, meta: FakeMetaCloudClient):
        self.w, self.meta = world, meta
        self.store = build_whatsapp_connection_store(world.admin, encryption_key=ENCRYPTION_KEY)

    def cloud(self):
        row = {"transporte": "cloud", "cloud_phone_number_id": "999", "cloud_waba_id": "W1",
               "encrypted_api_key": Fernet(ENCRYPTION_KEY.encode()).encrypt(b"meta-token").decode("ascii")}
        self.w._connections = [{**c, **row} for c in self.w._connections]
        self.w.sw.set_table_data("whatsapp_connections", self.w._connections)

    def modelo(self, nome="Abordagem neutra"):
        self.w.sw.table("julia_modelos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "nome": nome, "categoria": "primeiro_contato", "status": "aprovado",
            "corpo": "Oi {{nome_pessoa}}, é a {{nome_julia}}.", "idioma": "pt_BR"}).execute()

    def factory(self, conn):
        return tr.transporte_da_conexao(conn, waha_factory=lambda **kw: self.w.waha, cloud_client_factory=lambda **kw: self.meta)

    def rodar(self, lead=LEAD, agents="padrao", escolha="neutra"):
        """`agents="padrao"` = an agents whose decision (its DB rule, julia-v2 D13) is `escolha`; `None` = not configured."""
        if agents == "padrao":
            agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha=escolha, regra="versao")])
        self.agents = agents
        return asyncio.run(svc.iniciar(
            self.w.sw, ORG_ID, lead, store=self.store, transporte_factory=self.factory,
            contexto={"nome_julia": "Aurora", "nome_imobiliaria": "Imob"}, agents=agents))

    def eventos(self):
        return self.w.sw.table("julia_eventos").select("*").execute().data or []

    def contatos(self):
        return self.w.sw.table("julia_contatos").select("*").execute().data or []


@pytest.fixture
def cena():
    w = World()
    w.seed_connection()
    w.sw.set_table_data("julia_modelos", [])
    yield Cena(w, FakeMetaCloudClient(phone_number_id="999"))


class TestIniciar:
    def test_an_org_with_julia_off_takes_nothing_in(self, cena):
        cena.w._connections = [{**c, "agente_leads_ativo": False} for c in cena.w._connections]
        cena.w.sw.set_table_data("whatsapp_connections", cena.w._connections)
        assert cena.rodar() == {"status": "julia_desligada"}
        assert cena.contatos() == [] and cena.eventos() == [] and cena.meta.sent_templates == []

    def test_cloud_ready_sends_the_approved_template_and_creates_contato_and_interacao(self, cena):
        cena.cloud()
        cena.modelo("Abordagem neutra")
        r = cena.rodar()
        assert r["status"] == "enviado"
        assert cena.meta.sent_templates[0]["phone"] == "5511988887777"
        assert cena.meta.sent_templates[0]["body_params"] == ["Ana Teste", "Aurora"]
        (c,) = cena.contatos()
        assert c["telefone_e164"] == TEL and c["chat_id"] == "5511988887777@c.us" and c["ultimo_outbound_at"]
        assert len(cena.w.sw.table("julia_interacoes").select("*").eq("contato_id", c["id"]).execute().data) == 1
        (ev,) = cena.eventos()
        assert ev["tipo"] == "primeiro_contato_meta" and ev["payload"]["status"] == "enviado" and ev["contato_id"] == c["id"]
        assert cena.w.waha.sent_messages == []  # never WAHA free text

    def test_the_commercial_template_is_picked_when_the_lead_references_a_listing(self, cena):
        cena.cloud()
        cena.modelo("Abordagem neutra")
        assert cena.rodar({**LEAD, "answers": {"REF": "AP10"}}, escolha="comercial")["status"] == "modelo_nao_aprovado"  # wants comercial
        cena.modelo("Abordagem comercial")
        r = cena.rodar({**LEAD, "answers": {"REF": "AP10"}}, escolha="comercial")
        assert r["status"] == "enviado"
        assert cena.agents.decisoes[0][2].dados["codigo_imovel"] == "AP10"  # the listing code is DATA for agents' rule

    def test_while_waiting_for_meta_verification_nothing_is_sent_but_the_lead_enters_julia(self, cena):
        cena.modelo()
        r = cena.rodar()  # the seeded line is WAHA
        assert r["status"] == "transporte_indisponivel"
        assert cena.w.waha.sent_messages == [] and cena.meta.sent_templates == []
        (c,) = cena.contatos()
        assert c["ultimo_outbound_at"] is None
        assert [e["payload"]["status"] for e in cena.eventos()] == ["transporte_indisponivel"]

    def test_no_approved_template_is_reported_not_sent(self, cena):
        cena.cloud()
        assert cena.rodar()["status"] == "modelo_nao_aprovado" and cena.meta.sent_templates == []

    def test_a_second_delivery_never_messages_the_phone_twice(self, cena):
        cena.cloud()
        cena.modelo()
        assert cena.rodar()["status"] == "enviado"
        assert cena.rodar()["status"] == "ja_em_atendimento"
        assert len(cena.meta.sent_templates) == 1 and len(cena.contatos()) == 1

    def test_a_phone_already_talking_to_julia_is_not_contacted(self, cena):
        cena.cloud()
        cena.modelo()
        cena.w.sw.table("julia_contatos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": "5511988887777@c.us",
            "gen": 0, "slots": {}, "status_envio": "nao_pronto", "ultimo_inbound_at": "2026-10-16T10:00:00+00:00"}).execute()
        assert cena.rodar()["status"] == "ja_em_atendimento" and cena.meta.sent_templates == []

    def test_a_lead_without_a_usable_phone_is_recorded(self, cena):
        cena.cloud()
        assert cena.rodar({**LEAD, "phone": "não informado"})["status"] == "sem_telefone"
        assert [e["payload"]["status"] for e in cena.eventos()] == ["sem_telefone"] and cena.contatos() == []

    def test_a_failure_never_raises(self, cena):
        class Quebrada:
            def list_connections(self, **kw):
                raise RuntimeError("boom")

        r = asyncio.run(svc.iniciar(cena.w.sw, ORG_ID, LEAD, store=Quebrada(), transporte_factory=cena.factory))
        assert r == {"status": "erro"}


class TestAbordagem:
    def test_sw_holds_no_local_rule_any_more(self):
        """julia-v2 D13: the rule lives in agents' DB (`agent_version_decisoes`); SW keeps neither a default rule text nor a
        local fallback decision."""
        for gone in ("REGRA_PADRAO", "regra_local"):
            assert not hasattr(svc, gone)

    def test_the_agents_rule_decides_and_the_event_says_which_rule(self, cena):
        cena.cloud()
        cena.modelo("Abordagem comercial")
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="comercial", motivo="campanha de lançamento", regra="versao")])
        lead = {**LEAD, "campaign_name": "Lançamento Granja", "form_name": "Form 1"}
        assert cena.rodar(lead, agents=agents)["status"] == "enviado"  # no listing code, yet the owner's rule said comercial
        ((chave_agente, chave, req),) = agents.decisoes
        assert (chave_agente, chave) == ("julia", "abordagem-meta")
        assert req.opcoes == ("comercial", "neutra")
        assert not hasattr(req, "regra_padrao") and "regra" not in req.to_wire()  # SW sends options + data, never a rule
        assert req.dados == {"codigo_imovel": None, "campanha": "Lançamento Granja", "formulario": "Form 1", "anuncio": None}
        assert "Ana" not in str(req.dados) and "98888" not in str(req.dados)  # never the lead's name or phone
        (ev,) = cena.eventos()
        assert ev["payload"]["abordagem"] == {"escolha": "comercial", "regra": "versao", "motivo": "campanha de lançamento"}

    def test_the_flagged_default_of_the_version_is_reported_as_such(self, cena):
        cena.cloud()
        cena.modelo("Abordagem neutra")
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="neutra", regra="padrao_da_versao")])
        assert cena.rodar(agents=agents)["status"] == "enviado"
        (ev,) = cena.eventos()
        assert ev["payload"]["abordagem"]["regra"] == "padrao_da_versao"

    def test_agents_unreachable_sends_nothing_and_says_so(self, cena):
        """No local rule to fall back on: the lead is stored (and the owner sees why), not contacted by a guess."""
        cena.cloud()
        cena.modelo("Abordagem neutra")
        agents = FakeAgentsClient(decisao_script=[AgentsTimeout("down")])
        r = cena.rodar(agents=agents)
        assert r["status"] == "decisao_indisponivel" and cena.meta.sent_templates == []
        (ev,) = cena.eventos()
        assert ev["payload"]["status"] == "decisao_indisponivel"
        assert ev["payload"]["abordagem"] == {"escolha": None, "regra": "indisponivel", "motivo": "AgentsTimeout"}
        assert len(cena.contatos()) == 1

    def test_agents_not_configured_sends_nothing_either(self, cena):
        cena.cloud()
        cena.modelo("Abordagem neutra")
        assert cena.rodar(agents=None)["status"] == "decisao_indisponivel" and cena.meta.sent_templates == []

    def test_no_model_call_while_the_line_is_not_cloud(self, cena):
        cena.modelo()
        agents = FakeAgentsClient()
        assert cena.rodar(agents=agents)["status"] == "transporte_indisponivel"
        assert agents.decisoes == []
        (ev,) = cena.eventos()
        assert ev["payload"]["abordagem"]["regra"] == "indisponivel" and ev["payload"]["abordagem"]["motivo"] == "sem_cloud"

    def test_the_lead_form_is_recorded_as_the_opt_in_and_the_campaign_listing_as_data(self, cena):
        cena.cloud()
        cena.modelo("Abordagem comercial")
        cena.rodar({**LEAD, "answers": {"REF": "AP10"}}, escolha="comercial")
        (c,) = cena.contatos()
        assert cena.agents.opt_ins == [(c["id"], "formulario_meta")]
        assert c["codigo_imovel_campanha"] == "AP10"


class TestLeadgenLeg:
    def _processado(self):
        return ProcessResult(STATUS_PROCESSED, org_id=ORG_ID, lead_row=dict(LEAD))

    def test_a_processed_lead_is_handed_to_julia_after_the_announcement(self):
        chamadas = []

        async def intake(org_id, lead):
            chamadas.append((str(org_id), lead["id"]))
            return {"status": "enviado"}

        s = LeadgenWebhookService(admin_supabase=MockSupabaseClient(), notifier_factory=lambda **kw: None,
                                  publisher=_noop_publisher, julia_primeiro_contato=intake)
        asyncio.run(s.fan_out(self._processado()))
        assert chamadas == [(str(ORG_ID), "lead-1")]

    def test_a_failing_julia_leg_never_breaks_the_fan_out(self):
        async def intake(org_id, lead):
            raise RuntimeError("boom")

        s = LeadgenWebhookService(admin_supabase=MockSupabaseClient(), notifier_factory=lambda **kw: None,
                                  publisher=_noop_publisher, julia_primeiro_contato=intake)
        assert asyncio.run(s.fan_out(self._processado())) == {"notified": False, "published": True}

    def test_a_non_announceable_result_does_not_reach_julia(self):
        chamadas = []

        async def intake(org_id, lead):
            chamadas.append(1)

        s = LeadgenWebhookService(admin_supabase=MockSupabaseClient(), julia_primeiro_contato=intake)
        asyncio.run(s.fan_out(ProcessResult("error", org_id=ORG_ID)))
        assert chamadas == []


async def _noop_publisher(**kw):
    return None

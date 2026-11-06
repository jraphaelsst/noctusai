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

from app.clients.agents import AgentsTimeout, ControleInfo, DecisaoResult, FakeAgentsClient
from app.modules.meta_ads.services.leadgen_webhook_service import (
    STATUS_PROCESSED,
    LeadgenWebhookService,
    ProcessResult,
)
from app.services import julia_primeiro_contato_service as svc
from app.services import julia_transporte as tr
from app.services.whatsapp_connection_store import build_whatsapp_connection_store
from tests.support.julia_world import ADMIN_ID, CONNECTION_ID, ENCRYPTION_KEY, ORG_ID, OWNER_ID, OWNER_TELEFONE, World

TEL = "+5511988887777"
LEAD = {"id": "lead-1", "full_name": "Ana Teste", "phone": TEL, "answers": {}, "created_time": "2026-10-10T12:00:00+00:00"}  # after go-live


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
            contexto={"nome_julia": "Aurora", "nome_imobiliaria": "Imob"}, agents=agents, core=self.w.core))

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


def _teste(*usuarios, ligado=True):
    return ControleInfo(agent_key="julia", modo="ligado", aceita_novos_leads=True, modo_avaliacao=ligado,
                        avaliacao_usuarios=tuple(str(u) for u in usuarios))


class TestPrimeiroContatoSoParaLeadsNovos:
    """Owner 2026-11-05: Julia DOES open conversations -- but only with leads that arrive (a lead-form event) after go-live."""

    def _pronta(self, cena):
        cena.cloud()
        cena.modelo()

    def test_a_form_submitted_before_go_live_is_never_contacted(self, cena):
        self._pronta(cena)
        r = cena.rodar({**LEAD, "created_time": "2026-09-30T23:59:59+00:00"})
        assert r == {"status": "anterior_ao_golive"}
        assert cena.meta.sent_templates == [] and cena.w.waha.sent_messages == [] and cena.contatos() == []
        assert [e["payload"]["status"] for e in cena.eventos()] == ["anterior_ao_golive"]

    @pytest.mark.parametrize("quando", [None, "lixo"])
    def test_an_unreadable_submission_time_fails_closed(self, cena, quando):
        self._pronta(cena)
        assert cena.rodar({**LEAD, "created_time": quando})["status"] == "anterior_ao_golive"
        assert cena.meta.sent_templates == []

    def test_switching_julia_on_contacts_nobody_the_first_contact_only_runs_per_incoming_lead(self, cena):
        self._pronta(cena)
        # the lead base already holds contacts/leads from before go-live; nothing in the activation path calls `iniciar`
        assert cena.meta.sent_templates == [] and cena.w.waha.sent_messages == [] and cena.eventos() == []


class TestModoDeTeste:
    """Testing mode = agents' evaluation mode (the only switch): first contact goes ONLY to a listed number; OFF = everybody."""

    def _rodar(self, cena, controle, lead=LEAD):
        cena.cloud()
        cena.modelo()
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="neutra", regra="versao")], controle=controle)
        return cena.rodar(lead, agents=agents)

    def test_testing_off_contacts_everybody(self, cena):
        assert self._rodar(cena, _teste(OWNER_ID, ligado=False))["status"] == "enviado"

    def test_the_mode_is_a_live_state_off_contacts_the_stranger_on_again_refuses_the_same_stranger(self, cena):
        cena.cloud()
        cena.modelo()
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="neutra", regra="versao")] * 3, controle=_teste(OWNER_ID, ligado=False))

        def lead(n):
            return {**LEAD, "id": f"lead-{n}", "phone": f"+551197000000{n}"}

        assert cena.rodar(lead(1), agents=agents)["status"] == "enviado"                    # OFF: new lead contacted
        agents._controle = _teste(OWNER_ID)                                                 # flipped back ON
        r = cena.rodar(lead(2), agents=agents)
        assert r["status"] == "restrito_avaliacao"                                          # restricted at once
        agents._controle = _teste(OWNER_ID, ligado=False)                                   # OFF again
        assert cena.rodar(lead(3), agents=agents)["status"] == "enviado"
        assert len(cena.meta.sent_templates) == 2

    def test_testing_on_a_number_not_on_the_list_gets_no_first_contact(self, cena):
        r = self._rodar(cena, _teste(OWNER_ID))
        assert r["status"] == "restrito_avaliacao"
        assert cena.meta.sent_templates == [] and cena.w.waha.sent_messages == []
        assert [e["payload"]["status"] for e in cena.eventos()] == ["restrito_avaliacao"]

    def test_testing_on_a_stranger_lead_sends_nothing_to_anyone_not_even_the_greeting_to_the_owner(self, cena):
        r = self._rodar(cena, _teste(OWNER_ID))
        assert r["status"] == "restrito_avaliacao"
        assert cena.meta.sent_templates == [] and cena.w.waha.sent_messages == []
        assert len(cena.contatos()) == 1, "the lead is still registered in Julia's list"
        assert cena.agents.decisoes == [], "no approach decision is asked for a withheld greeting"

    def test_testing_on_the_listed_number_gets_it(self, cena):
        lead = {**LEAD, "phone": OWNER_TELEFONE}
        assert self._rodar(cena, _teste(OWNER_ID), lead)["status"] == "enviado"
        assert len(cena.meta.sent_templates) == 1

    def test_testing_on_a_member_who_is_not_listed_gets_none(self, cena):
        lead = {**LEAD, "phone": OWNER_TELEFONE}
        assert self._rodar(cena, _teste(ADMIN_ID), lead)["status"] == "restrito_avaliacao"
        assert cena.meta.sent_templates == []

    def test_testing_on_with_an_empty_list_contacts_nobody(self, cena):
        assert self._rodar(cena, _teste())["status"] == "restrito_avaliacao"

    def test_an_unreadable_controle_fails_closed_and_is_logged(self, cena, caplog):
        with caplog.at_level("ERROR"):
            r = self._rodar(cena, AgentsTimeout("down"))
        assert r["status"] == "avaliacao_indisponivel" and cena.meta.sent_templates == []
        assert "no evaluation bypass" in caplog.text

    def test_testing_on_without_a_core_client_fails_closed(self, cena):
        cena.cloud()
        cena.modelo()
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="neutra", regra="versao")], controle=_teste(OWNER_ID))
        r = asyncio.run(svc.iniciar(cena.w.sw, ORG_ID, {**LEAD, "phone": OWNER_TELEFONE}, store=cena.store,
                                    transporte_factory=cena.factory, agents=agents))
        assert r["status"] == "avaliacao_indisponivel" and cena.meta.sent_templates == []


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
        # no agents client: the testing-mode state cannot be read, so the greeting is withheld (fail closed) before the decision is asked
        assert cena.rodar(agents=None)["status"] == "avaliacao_indisponivel" and cena.meta.sent_templates == []

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

    @pytest.mark.parametrize("testando", [False, True])
    def test_testing_mode_withholds_only_the_greeting_registration_and_notification_always_run(self, cena, testando):
        """Owner 2026-11-05: testing mode NEVER blocks lead intake. With it ON and a non-listed Meta-form lead the lead is registered
        in Julia's list and the team is notified exactly as with it OFF; only the greeting to the lead is withheld."""
        cena.cloud()
        cena.modelo()
        agents = FakeAgentsClient(decisao_script=[DecisaoResult(escolha="neutra", regra="versao")],
                                  controle=_teste(OWNER_ID, ligado=testando))

        class Notificador:
            def __init__(self):
                self.calls = []

            async def notify_new_lead(self, *, org_id, lead, marca_id=None):
                self.calls.append((org_id, lead["id"]))

        publicados = []

        async def publisher(**kw):
            publicados.append(kw["lead"]["id"])

        async def intake(org_id, lead):
            return await svc.iniciar(cena.w.sw, org_id, lead, store=cena.store, transporte_factory=cena.factory,
                                     contexto={"nome_julia": "Aurora", "nome_imobiliaria": "Imob"}, agents=agents, core=cena.w.core)

        notifier = Notificador()
        s = LeadgenWebhookService(admin_supabase=MockSupabaseClient(), notifier_factory=lambda **kw: notifier,
                                  publisher=publisher, julia_primeiro_contato=intake)
        out = asyncio.run(s.fan_out(self._processado()))
        assert out == {"notified": True, "published": True}   # identical with testing ON and OFF
        assert publicados == ["lead-1"] and notifier.calls == [(ORG_ID, "lead-1")]
        assert len(cena.contatos()) == 1                       # registered in Julia's list either way
        assert len(cena.meta.sent_templates) == (0 if testando else 1)
        assert cena.w.waha.sent_messages == []
        assert [e["payload"]["status"] for e in cena.eventos()] == (["restrito_avaliacao"] if testando else ["enviado"])

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

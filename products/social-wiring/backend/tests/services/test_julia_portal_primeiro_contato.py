"""Portal lead (OLX / ImovelWeb) -> Julia speaks first (`julia_portal_primeiro_contato_service`) and the two portal webhook legs.

Seams only: the mock DB, the seed `FakeWahaClient` behind the REAL transport factory, the real connection store over the
mock, the gate (real), and the webhook services' own DI seam. Fixtures carry no personal data."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.integrations.olx import OlxLead
from noctusai_lib.testing import MockSupabaseClient

from app.clients.agents import ConsentInfo, FakeAgentsClient
from app.modules.portal_leads.services.imovelweb_webhook_service import ImovelWebWebhookService
from app.modules.portal_leads.services.olx_webhook_service import OlxWebhookService
from app.services import julia_envio_gate, julia_reengajamento_service as reeng
from app.services import julia_portal_primeiro_contato_service as svc
from app.services import julia_transporte as tr
from app.services.whatsapp_connection_store import build_whatsapp_connection_store
from tests.support.julia_world import CONNECTION_ID, ENCRYPTION_KEY, ORG_ID, World

TEL = "+5511977776666"
# 2026-11-17 is a Tuesday; 15:00 UTC = 12:00 America/Sao_Paulo (inside 08:00-19:59). 02:00 UTC = 23:00 (outside).
DIA = datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)
NOITE = datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc)
TEXTO = "Oi, sou uma assistente virtual (IA). Aviso de privacidade: https://x.example/privacidade/imob"


def _lead(**over):
    return {"origem": "olx", "origem_lead_id": "olx-1", "phone": TEL, "name": "Ana Teste",
            "chegou_em": (DIA - timedelta(minutes=2)).isoformat(), **over}


class _MsgStore:
    def __init__(self):
        self.rows = []

    def record(self, **kw):
        self.rows.append(kw)


class Cena:
    def __init__(self, world: World):
        self.w = world
        self.store = build_whatsapp_connection_store(world.admin, encryption_key=ENCRYPTION_KEY)
        self.msgs = _MsgStore()

    def ligar(self, ativo=True):
        self.w.sw.table("julia_reengajamento_config").insert({"org_id": ORG_ID, "portal_primeiro_contato_ativo": ativo}).execute()

    def factory(self, conn):
        return tr.transporte_da_conexao(conn, waha_factory=lambda **kw: self.w.waha)

    def rodar(self, lead=None, agora=DIA, agents="padrao", mensagem=lambda: TEXTO):
        agents = FakeAgentsClient() if agents == "padrao" else agents
        return asyncio.run(svc.iniciar(
            self.w.sw, ORG_ID, lead or _lead(), store=self.store, transporte_factory=self.factory, mensagem_inicial=mensagem,
            message_store_factory=lambda org: self.msgs, agents=agents, core=self.w.core, agora=agora))

    def eventos(self):
        return self.w.sw.table("julia_eventos").select("*").execute().data or []

    def status(self):
        return [e["payload"]["status"] for e in self.eventos() if e["tipo"] == "primeiro_contato_portal"]


@pytest.fixture
def cena():
    w = World()
    w.seed_connection()
    yield Cena(w)


class TestIniciar:
    def test_switch_defaults_off_nothing_is_sent_and_it_is_recorded(self, cena):
        assert cena.rodar() == {"status": "desativado"}
        assert cena.w.waha.sent_messages == [] and cena.status() == ["desativado"]

    def test_an_org_with_julia_off_takes_nothing_in(self, cena):
        cena.ligar()
        cena.w._connections = [{**c, "agente_leads_ativo": False} for c in cena.w._connections]
        cena.w.sw.set_table_data("whatsapp_connections", cena.w._connections)
        assert cena.rodar() == {"status": "julia_desligada"} and cena.eventos() == []

    def test_sends_the_disclosure_as_plain_waha_text_and_records_everything(self, cena):
        cena.ligar()
        r = cena.rodar()
        assert r["status"] == "enviado"
        assert [m["text"] for m in cena.w.waha.sent_messages] == [TEXTO]
        (c,) = cena.w.sw.table("julia_contatos").select("*").execute().data
        assert c["telefone_e164"] == TEL and c["ultimo_outbound_at"]
        assert len(cena.w.sw.table("julia_interacoes").select("*").eq("contato_id", c["id"]).execute().data) == 1
        (m,) = cena.msgs.rows
        assert m["origem"] == "julia" and m["direction"] == "outbound" and m["body"] == TEXTO
        (ev,) = cena.eventos()
        assert ev["tipo"] == "primeiro_contato_portal" and ev["contato_id"] == c["id"]
        assert ev["payload"] == {"status": "enviado", "motivo": None, "origem": "olx", "origem_lead_id": "olx-1"}

    def test_a_portal_re_entry_of_the_same_phone_never_opens_twice(self, cena):
        cena.ligar()
        assert cena.rodar()["status"] == "enviado"
        r = cena.rodar(_lead(origem_lead_id="olx-2"))
        assert r["status"] == "reentrada"
        assert len(cena.w.waha.sent_messages) == 1
        assert cena.status() == ["enviado", "reentrada"]

    def test_a_phone_already_talking_to_julia_is_a_reentry(self, cena):
        cena.ligar()
        cena.w.sw.table("julia_contatos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": "5511977776666@c.us",
            "gen": 0, "slots": {}, "status_envio": "nao_pronto", "ultimo_inbound_at": "2026-11-16T10:00:00+00:00"}).execute()
        assert cena.rodar()["status"] == "reentrada" and cena.w.waha.sent_messages == []

    def test_a_recorded_opener_blocks_another_even_if_the_activity_stamps_are_clear(self, cena):
        cena.ligar()
        assert cena.rodar()["status"] == "enviado"
        cena.w.sw.table("julia_contatos").update({"ultimo_outbound_at": None}).execute()
        assert cena.rodar(_lead(origem_lead_id="olx-3"))["status"] == "reentrada"
        assert len(cena.w.waha.sent_messages) == 1

    def test_outside_business_hours_nothing_is_sent_and_it_is_recorded(self, cena):
        cena.ligar()
        r = cena.rodar(agora=NOITE, lead=_lead(chegou_em=(NOITE - timedelta(minutes=1)).isoformat()))
        assert r["status"] == "fora_do_horario" and cena.w.waha.sent_messages == [] and cena.status() == ["fora_do_horario"]

    def test_an_old_lead_is_not_new(self, cena):
        cena.ligar()
        r = cena.rodar(_lead(chegou_em=(DIA - timedelta(hours=7)).isoformat()))
        assert r["status"] == "lead_antigo" and cena.w.waha.sent_messages == []

    def test_a_lead_from_before_go_live_or_unreadable_is_refused(self, cena):
        cena.ligar()
        assert cena.rodar(_lead(chegou_em="2020-01-01T00:00:00+00:00"))["status"] == "anterior_ao_golive"
        assert cena.rodar(_lead(chegou_em="ontem"))["status"] == "anterior_ao_golive"
        assert cena.w.waha.sent_messages == []

    def test_a_lead_without_a_usable_phone_is_recorded(self, cena):
        cena.ligar()
        assert cena.rodar(_lead(phone="nao informado"))["status"] == "sem_telefone"
        assert cena.status() == ["sem_telefone"] and cena.w.sw.table("julia_contatos").select("*").execute().data == []

    def test_an_opted_out_lead_is_not_contacted(self, cena):
        cena.ligar()
        class OptOut(FakeAgentsClient):
            async def consentimento(self, lead_ref):
                return ConsentInfo(lead_ref=lead_ref, opt_out_ativo=True)  # the lead asked to stop

        agents = OptOut()
        r = cena.rodar(agents=agents)
        assert r == {"status": "bloqueado", "motivo": julia_envio_gate.MOTIVO_OPT_OUT, "contato_id": r["contato_id"]}
        assert cena.w.waha.sent_messages == []

    def test_without_agents_nothing_is_sent_fail_closed(self, cena):
        cena.ligar()
        r = cena.rodar(agents=None)  # agents unreadable: the evaluation-mode read refuses first, the opt-out leg would too
        assert r["status"] == "avaliacao_indisponivel" and cena.w.waha.sent_messages == []

    def test_a_line_that_refuses_the_send_is_recorded_not_raised(self, cena):
        cena.ligar()

        class Recusa:
            async def enviar_texto(self, *_a):
                raise RuntimeError("linha somente leitura")

        cena.factory = lambda conn: Recusa()
        assert cena.rodar()["status"] == "envio_recusado"
        assert cena.status() == ["envio_recusado"] and cena.msgs.rows == []

    def test_a_missing_disclosure_blocks_the_send(self, cena):
        cena.ligar()

        def quebrada():
            raise RuntimeError("aviso")

        assert cena.rodar(mensagem=quebrada)["status"] == "aviso_indisponivel"
        assert cena.w.waha.sent_messages == []

    def test_a_cloud_only_julia_line_sends_nothing(self, cena):
        cena.ligar()
        cena.w._connections = [{**c, "transporte": "cloud"} for c in cena.w._connections]
        cena.w.sw.set_table_data("whatsapp_connections", cena.w._connections)
        assert cena.rodar()["status"] == "sem_linha_waha" and cena.w.waha.sent_messages == []

    def test_a_failure_never_raises(self, cena):
        class Quebrada:
            def list_connections(self, **kw):
                raise RuntimeError("boom")

        r = asyncio.run(svc.iniciar(
            cena.w.sw, ORG_ID, _lead(), store=Quebrada(), mensagem_inicial=lambda: TEXTO,
            message_store_factory=lambda o: cena.msgs, agora=DIA))
        assert r == {"status": "erro"}


class TestGate:
    def test_the_flow_follows_the_org_switch(self, cena):
        db = cena.w.sw
        assert julia_envio_gate.motivo_do_bloqueio(db, ORG_ID, CONNECTION_ID, julia_envio_gate.Fluxo.PRIMEIRO_CONTATO_PORTAL) \
            == "portal_primeiro_contato_desativado"
        cena.ligar()
        assert julia_envio_gate.motivo_do_bloqueio(db, ORG_ID, CONNECTION_ID, julia_envio_gate.Fluxo.PRIMEIRO_CONTATO_PORTAL) is None

    def test_the_switch_is_off_by_default_in_the_config(self):
        assert reeng.CONFIG_PADRAO["portal_primeiro_contato_ativo"] is False


class TestWebhookLegs:
    """The portal webhook services call the opener only for a NEWLY created lead, through their DI seam."""

    def _olx(self, created: bool, calls: list):
        client = MockSupabaseClient()
        lead = OlxLead(origin_lead_id="olx-9", name="Ana Teste", phone_number="+5511977776666", client_listing_id="AP1",
                       lead_origin="x", timestamp="2026-11-17T12:00:00Z", raw={})
        s = OlxWebhookService(
            client=client, org_resolver=lambda c, l: UUID(ORG_ID), ingest_fn=lambda c, o, l: {"created": created, "lead": {"id": "1"}},
            julia_portal_intake=lambda org, d: calls.append((org, d)) or _async({"status": "enviado"}))
        s._enqueue_forwards = lambda *a, **k: None
        s._update_event = lambda *a, **k: None
        s._get_event = lambda *_: {"attempts": 0, "received_at": "2026-11-17T12:00:00+00:00"}
        return s, lead

    def test_olx_opener_runs_for_a_new_lead_only(self):
        calls: list = []
        s, lead = self._olx(True, calls)
        s.process_lead(lead)
        assert len(calls) == 1
        assert calls[0][1] == {"origem": "olx", "origem_lead_id": "olx-9", "phone": "+5511977776666", "name": "Ana Teste",
                               "chegou_em": "2026-11-17T12:00:00+00:00"}
        calls.clear()
        s, lead = self._olx(False, calls)
        s.process_lead(lead)
        assert calls == []

    def test_a_failing_opener_never_breaks_the_ingest(self):
        client = MockSupabaseClient()
        lead = OlxLead(origin_lead_id="olx-8", lead_origin="x", name="A", phone_number="+5511977776666", timestamp="2026-11-17T12:00:00Z", raw={})

        def explode(org, d):
            raise RuntimeError("boom")

        s = OlxWebhookService(client=client, org_resolver=lambda c, l: UUID(ORG_ID),
                              ingest_fn=lambda c, o, l: {"created": True, "lead": {"id": "1"}}, julia_portal_intake=explode)
        s._enqueue_forwards = lambda *a, **k: None
        s._update_event = lambda *a, **k: None
        s._get_event = lambda *_: None
        assert s.process_lead(lead).created is True

    def test_imovelweb_wiring_exists(self):
        assert "julia_portal_intake" in ImovelWebWebhookService.__init__.__code__.co_varnames


async def _async(v):
    return v

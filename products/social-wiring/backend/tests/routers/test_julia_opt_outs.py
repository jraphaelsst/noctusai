"""Julia > Opt-outs routes (owner decisions 2026-10-21): the per-org history, "Reenviar notificação", "Reativar atendimento",
"Marcar como não contatar", the operator composer's state read and the data-subject requests.

Seams: mock DB + `FakeAgentsClient` injected through the route's own `Depends(get_agents_client_factory)`; nothing of ours is
patched. Every route is strict `== 401` without a session; member reads, org admin writes."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import handler_status, TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import AgentsTimeout, FakeAgentsClient
from app.services import julia_solicitacoes_titular_service as sol

from tests.support.julia_world import (
    InsertFailingClient,
    ADMIN_ID, CONNECTION_ID, CORRETOR_ID, ENCRYPTION_KEY, LEAD_CHAT, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World,
)

H = {"Authorization": "Bearer test-token"}
BASE = "/api/julia/opt-outs"
OUTRO_CHAT = "5511977770000@c.us"


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, url, json=None, **kw):
        return getattr(self.tc, m)(url, headers=H, **({"json": json} if json is not None else {}), **kw)

    def lead(self, chat=LEAD_CHAT, nome="Ana"):
        """A contato with a real UUID id (the route's path params are typed `UUID`; the mock's ids are not)."""
        row = {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": chat, "gen": 0, "slots": {},
               "canal": "whatsapp", "status_envio": "nao_pronto", "nome": nome, "telefone_e164": "+5511988887777"}
        self.w.sw.table("julia_contatos").insert(row).execute()
        return row

    def opt_out(self, contato, origem="agente", motivo="lead_pediu_parar", ator=None):
        asyncio.run(self.w.agents.opt_out(str(contato["id"]), origem=origem, motivo=motivo, mensagem_lead="para de mandar", ator_user_id=ator))


def _scene(role):
    w = World()
    w.seed_connection(user_id=OWNER_ID)
    w.seed_chat()
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Dono"},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin", "nome": "Adriana"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor", "nome": "Carla"},
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role, "nome": "Chefe"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member", "nome": "Marcos"},
    ])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.julia_opt_outs_router import get_opt_outs_client
        from app.routers.whatsapp_connections_router import get_agents_client_factory

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_opt_outs_client] = lambda: w.sw
        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: w.agents)
        yield Scene(TestClient(app), w)
        app.dependency_overrides.pop(get_opt_outs_client, None)
        app.dependency_overrides.pop(get_agents_client_factory, None)


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: _settings.model_copy(update={"encryption_key": ENCRYPTION_KEY})
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def admin(override_settings_factory):
    yield from _scene("owner")


@pytest.fixture
def member(override_settings_factory):
    yield from _scene("member")


# ── strict 401 ──────────────────────────────────────────────────────────────
class TestAuth:
    @pytest.mark.parametrize("metodo,url,corpo", [
        ("get", BASE, None),
        ("post", f"{BASE}/{uuid4()}/notificar", None),
        ("get", f"{BASE}/leads/{uuid4()}/estado", None),
        ("post", f"{BASE}/leads/{uuid4()}/nao-contatar", {"motivo": "x"}),
        ("post", f"{BASE}/leads/{uuid4()}/reativar", {"motivo": "x"}),
        ("get", f"{BASE}/conversas/{CONNECTION_ID}/{LEAD_CHAT}/estado", None),
        ("get", f"{BASE}/solicitacoes", None),
        ("patch", f"{BASE}/solicitacoes/{uuid4()}", {"status": "concluido"}),
    ])
    def test_no_token_is_401(self, admin, metodo, url, corpo):
        r = getattr(admin.tc, metodo)(url, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 401


# ── the history ─────────────────────────────────────────────────────────────
class TestHistorico:
    def test_lists_newest_first_with_actor_name_and_the_active_flag(self, admin):
        c = admin.lead()
        admin.opt_out(c, origem="operador", motivo="pediu por telefone", ator=ADMIN_ID)
        admin.opt_out(admin.lead(OUTRO_CHAT, "Beto"))
        itens = admin.req("get", BASE).json()["data"]["items"]
        assert [i["lead_ref"] for i in itens][0] != str(c["id"]) and len(itens) == 2
        mais_antigo = itens[1]
        assert mais_antigo["origem"] == "operador" and mais_antigo["ator_nome"] == "Adriana" and mais_antigo["ativo"] is True
        assert mais_antigo["motivo"] == "pediu por telefone" and mais_antigo["mensagem_lead"] == "para de mandar"

    def test_a_reactivated_optout_is_not_active_and_the_reactivation_is_listed(self, admin):
        c = admin.lead()
        admin.opt_out(c)
        assert admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "pediu para voltar"}).status_code == 200
        itens = admin.req("get", BASE).json()["data"]["items"]
        assert [(i["tipo"], i["ativo"]) for i in itens] == [("reativacao", False), ("opt_out", False)]
        assert itens[0]["ator_user_id"] == TEST_USER_ID and itens[0]["motivo"] == "pediu para voltar"

    def test_pagination_cursor_and_lead_filter(self, admin):
        for k in range(3):
            admin.opt_out(admin.lead(f"55119000000{k}@c.us", f"L{k}"))
        p1 = admin.req("get", f"{BASE}?limit=2").json()["data"]
        assert len(p1["items"]) == 2 and p1["next_cursor"]
        p2 = admin.req("get", f"{BASE}?limit=2&cursor={p1['next_cursor']}").json()["data"]
        assert len(p2["items"]) == 1 and p2["next_cursor"] is None
        so_um = admin.req("get", f"{BASE}?lead_ref={p1['items'][0]['lead_ref']}").json()["data"]["items"]
        assert len(so_um) == 1
        assert admin.req("get", f"{BASE}?limit=0").status_code == 422

    def test_a_member_reads(self, member):
        member.opt_out(member.lead())
        assert member.req("get", BASE).status_code == 200

    def test_agents_down_is_a_typed_502_not_an_empty_list(self, admin):
        admin.w.agents.errors["listar_opt_outs"] = AgentsTimeout()
        r = admin.req("get", BASE)
        assert handler_status(r) == 502 and r.json()["code"] == "agents_indisponivel" if "code" in r.json() else handler_status(r) == 502

    def test_a_failed_notice_shows_its_error_and_renotify_resends_it(self, admin):
        c = admin.lead()
        admin.opt_out(c)
        [e] = admin.w.agents.opt_out_eventos
        admin.w.agents.opt_out_eventos[0] = type(e)(**{**e.__dict__, "notificacao_status": "falhou", "notificacao_erro": "sem destinatarios"})
        item = admin.req("get", BASE).json()["data"]["items"][0]
        assert item["notificacao_status"] == "falhou" and item["notificacao_erro"] == "sem destinatarios"
        r = admin.req("post", f"{BASE}/{e.id}/notificar")
        assert r.status_code == 200 and r.json()["data"]["notificacao_status"] == "enviada"
        assert admin.w.agents.renotificacoes == [(e.id, TEST_USER_ID)]
        assert admin.req("post", f"{BASE}/{uuid4()}/notificar").status_code == 404


# ── reactivation + do-not-contact ───────────────────────────────────────────
class TestEscritas:
    def test_reactivation_requires_a_motivo_and_records_the_actor(self, admin):
        c = admin.lead()
        admin.opt_out(c)
        assert admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "  "}).status_code == 422
        assert admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {}).status_code == 422
        assert admin.w.agents.reativacoes == []
        r = admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "o lead pediu para voltar"})
        assert r.status_code == 200 and r.json()["data"]["opt_out_ativo"] is False
        assert admin.w.agents.reativacoes == [{"lead_ref": str(c["id"]), "motivo": "o lead pediu para voltar", "ator_user_id": TEST_USER_ID}]

    def test_reactivating_a_lead_without_an_active_optout_is_409(self, admin):
        c = admin.lead()
        admin.opt_out(c)
        admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "volta"})
        assert admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "volta"}).status_code == 409

    def test_reactivating_a_lead_agents_never_saw_is_404(self, admin):
        c = admin.lead()
        r = admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "volta"})
        assert r.status_code == 404

    def test_marcar_nao_contatar_is_an_operator_optout_by_the_caller(self, admin):
        c = admin.lead()
        assert admin.req("post", f"{BASE}/leads/{c['id']}/nao-contatar", {"motivo": ""}).status_code == 422
        r = admin.req("post", f"{BASE}/leads/{c['id']}/nao-contatar", {"motivo": "ligou pedindo para parar"})
        assert r.status_code == 200 and r.json()["data"]["opt_out_ativo"] is True
        [call] = admin.w.agents.opt_out_calls
        assert call["origem"] == "operador" and call["motivo"] == "ligou pedindo para parar" and call["ator_user_id"] == TEST_USER_ID
        assert call["lead_ref"] == str(c["id"])
        gen_depois = admin.w.contato()["gen"]
        assert gen_depois >= 1, "queued re-engagement jobs of the lead are stale"
        tipos = [e["tipo"] for e in admin.w.rows("julia_eventos")]
        assert "lead_opt_out" in tipos

    def test_a_member_never_writes(self, member):
        c = member.lead()
        member.opt_out(c)
        for url, body in [
            (f"{BASE}/leads/{c['id']}/nao-contatar", {"motivo": "x"}),
            (f"{BASE}/leads/{c['id']}/reativar", {"motivo": "x"}),
            (f"{BASE}/{uuid4()}/notificar", None),
        ]:
            assert member.req("post", url, body).status_code == 403, url
        assert member.w.agents.reativacoes == [] and member.w.agents.renotificacoes == []

    def test_another_orgs_contato_is_404(self, admin):
        fora = admin.w.sw.table("julia_contatos").insert({
            "id": str(uuid4()), "org_id": OTHER_ORG_ID, "connection_id": CONNECTION_ID, "chat_id": "5500@c.us", "gen": 0,
        }).execute().data[0]
        assert admin.req("post", f"{BASE}/leads/{fora['id']}/reativar", {"motivo": "x"}).status_code == 404
        assert admin.req("post", f"{BASE}/leads/{fora['id']}/nao-contatar", {"motivo": "x"}).status_code == 404
        assert admin.req("get", f"{BASE}/leads/{fora['id']}/estado").status_code == 404

    def test_agents_not_configured_is_503(self, admin):
        from app.main import app
        from app.routers.whatsapp_connections_router import get_agents_client_factory

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: None)
        c = admin.lead()
        assert admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "x"}).status_code == 503


# ── the operator composer's warning ─────────────────────────────────────────
class TestEstadoDaConversa:
    URL = f"{BASE}/conversas/{CONNECTION_ID}/{LEAD_CHAT}/estado"

    def test_an_active_optout_carries_the_date_and_the_motivo(self, admin):
        admin.opt_out(admin.lead(), motivo="lead_pediu_parar")
        d = admin.req("get", self.URL).json()["data"]
        assert d["verificado"] is True and d["opt_out_ativo"] is True and d["motivo"] == "lead_pediu_parar" and d["opt_out_em"]

    def test_no_optout_and_no_lead_are_both_clean(self, admin):
        assert admin.req("get", self.URL).json()["data"]["opt_out_ativo"] is False
        admin.lead()
        d = admin.req("get", self.URL).json()["data"]
        assert d["opt_out_ativo"] is False and d["verificado"] is True

    def test_a_reactivated_lead_has_no_warning(self, admin):
        c = admin.lead()
        admin.opt_out(c)
        admin.req("post", f"{BASE}/leads/{c['id']}/reativar", {"motivo": "volta"})
        assert admin.req("get", self.URL).json()["data"]["opt_out_ativo"] is False

    def test_an_unreadable_state_is_reported_unverified_never_as_clean(self, admin):
        admin.lead()
        admin.w.agents.errors["consentimento"] = AgentsTimeout()
        r = admin.req("get", self.URL)
        assert r.status_code == 200 and r.json()["data"]["verificado"] is False

    def test_the_phone_alias_of_the_chat_is_found(self, admin):
        admin.opt_out(admin.lead())
        d = admin.req("get", f"{BASE}/conversas/{CONNECTION_ID}/5511988887777@s.whatsapp.net/estado").json()["data"]
        assert d["opt_out_ativo"] is True


# ── data-subject requests ───────────────────────────────────────────────────
class TestSolicitacoes:
    def _pedido(self, s, tipo="eliminacao", trecho="quero que apaguem meus dados"):
        c = s.lead()
        return sol.registrar(s.w.sw, s.w.core, org_id=ORG_ID, lead_ref=str(c["id"]), tipo=tipo, trecho=trecho, chat_id=LEAD_CHAT)

    def test_registrar_sets_a_15_day_deadline_and_notifies_the_admins(self, admin):
        p = self._pedido(admin)
        from datetime import datetime
        assert (datetime.fromisoformat(p["prazo_em"]) - datetime.fromisoformat(p["recebida_em"])).days == 15
        assert p["status"] == "aberta" and p["notificacao_status"] == "enviada"
        avisos = [n for n in admin.w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_solicitacao_titular"]
        assert {n["user_id"] for n in avisos} == {OWNER_ID, ADMIN_ID, TEST_USER_ID}  # the caller is an owner here
        assert all(n["metadata"]["product"] == "social-wiring" and n["metadata"]["link"].startswith("/julia/opt-outs") for n in avisos)
        assert admin.w.agents.leads_apagados == [] and admin.w.contato() is not None  # nothing is deleted

    def test_a_failed_notice_is_recorded_on_the_row(self, admin):
        c = admin.lead()
        p = sol.registrar(
            admin.w.sw, InsertFailingClient(admin.w.core, "notifications"), org_id=ORG_ID,
            lead_ref=str(c["id"]), tipo="eliminacao", trecho="quero que apaguem meus dados", chat_id=LEAD_CHAT,
        )
        assert p["notificacao_status"] == "falhou" and "notifications down" in p["notificacao_erro"]
        assert admin.w.rows("julia_solicitacoes_titular")[0]["notificacao_status"] == "falhou"

    def test_no_admin_in_the_org_records_the_failure(self, admin):
        admin.w.core.set_table_data("noctus_users", [{"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"}])
        p = self._pedido(admin)
        assert p["notificacao_status"] == "falhou" and "sem_destinatarios" in p["notificacao_erro"]

    def test_the_excerpt_is_capped_and_an_unknown_lead_or_tipo_is_refused(self, admin):
        p = self._pedido(admin, trecho="x" * 900)
        assert len(p["trecho_lead"]) == 500
        with pytest.raises(Exception) as e:
            sol.registrar(admin.w.sw, admin.w.core, org_id=ORG_ID, lead_ref=str(uuid4()), tipo="acesso", trecho="t")
        assert getattr(e.value, "status_code", None) == 404
        with pytest.raises(Exception) as e:
            sol.registrar(admin.w.sw, admin.w.core, org_id=ORG_ID, lead_ref=str(admin.lead()["id"]), tipo="apagar", trecho="t")
        assert getattr(e.value, "status_code", None) == 422

    def test_the_deadline_situation_is_vencida_vence_em_breve_or_no_prazo(self, admin):
        from datetime import datetime, timedelta, timezone

        agora = datetime.now(timezone.utc)
        for st, dias in [("aberta", 10), ("aberta", 2), ("em_analise", -1), ("atendida", -1)]:
            admin.w.sw.table("julia_solicitacoes_titular").insert({
                "id": str(uuid4()), "org_id": ORG_ID, "contato_id": str(uuid4()), "tipo": "acesso", "trecho_lead": "t",
                "recebida_em": agora.isoformat(), "prazo_em": (agora + timedelta(days=dias)).isoformat(), "status": st,
            }).execute()
        itens = admin.req("get", f"{BASE}/solicitacoes").json()["data"]["items"]
        assert sorted(i["prazo_situacao"] for i in itens) == ["encerrada", "no_prazo", "vence_em_breve", "vencida"]
        assert [i["prazo_situacao"] for i in itens][0] == "vencida"  # most urgent deadline first

    def test_admin_decides_and_the_decision_is_recorded(self, admin):
        p = self._pedido(admin)
        lista = admin.req("get", f"{BASE}/solicitacoes").json()["data"]
        assert lista["total"] == 1 and lista["items"][0]["status"] == "aberta"
        r = admin.req("patch", f"{BASE}/solicitacoes/{p['id']}", {"status": "em_analise"})
        assert r.status_code == 200 and r.json()["data"]["decidido_por"] == TEST_USER_ID
        assert admin.req("patch", f"{BASE}/solicitacoes/{p['id']}", {"status": "negada"}).status_code == 422  # reason required
        r = admin.req("patch", f"{BASE}/solicitacoes/{p['id']}", {"status": "negada", "motivo": "obrigação legal de guarda"})
        assert r.json()["data"]["motivo_decisao"] == "obrigação legal de guarda" and r.json()["data"]["prazo_situacao"] == "encerrada"
        assert admin.req("get", f"{BASE}/solicitacoes?status=aberta").json()["data"]["items"] == []
        assert admin.req("get", f"{BASE}/solicitacoes?status=xyz").status_code == 422
        assert admin.req("patch", f"{BASE}/solicitacoes/{p['id']}", {"status": "feito"}).status_code == 422
        assert admin.w.agents.leads_apagados == [] and admin.w.contato() is not None  # even `atendida` erases nothing by itself

    def test_a_member_reads_but_cannot_decide(self, member):
        p = self._pedido(member)
        assert member.req("get", f"{BASE}/solicitacoes").status_code == 200
        assert member.req("patch", f"{BASE}/solicitacoes/{p['id']}", {"status": "atendida"}).status_code == 403
        assert member.w.rows("julia_solicitacoes_titular")[0]["status"] == "aberta"

    def test_a_request_of_another_org_is_404_and_invisible(self, admin):
        r = admin.w.sw.table("julia_solicitacoes_titular").insert({
            "id": str(uuid4()), "org_id": OTHER_ORG_ID, "contato_id": str(uuid4()), "tipo": "acesso", "trecho_lead": "t",
            "recebida_em": "2026-10-01T00:00:00+00:00", "prazo_em": "2026-10-16T00:00:00+00:00", "status": "aberta",
        }).execute().data[0]
        assert admin.req("patch", f"{BASE}/solicitacoes/{r['id']}", {"status": "atendida"}).status_code == 404
        assert admin.req("get", f"{BASE}/solicitacoes").json()["data"]["total"] == 0

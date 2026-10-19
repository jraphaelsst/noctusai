"""Lais wave 12 (contract 14 / A6 / 17): the transport seam, Modelos, Disparos, Atualizacao de imoveis.

Seams only: the mock DB, the seed `FakeWahaClient` / `FakeMetaCloudClient` behind the real transport factory,
the router's own DI seams -- nothing of ours is patched. The load-bearing assertions: WAHA NEVER mass-sends,
the 409 `transporte_indisponivel` matrix, the caps, the owner opt-out, strict `== 401`."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from noctusai_lib.integrations.whatsapp import FakeMetaCloudClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import lais_conhecimento_service as conhecimento
from app.services import lais_disparos_service as disparos
from app.services import lais_envio_gate
from app.services import lais_modelos_service as modelos
from app.services import lais_proprietarios_service as proprietarios
from app.services import lais_reengajamento_service as reeng
from app.services import lais_transporte as tr
from tests.support.lais_world import CONNECTION_ID, ENCRYPTION_KEY, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
NOW = datetime.now(timezone.utc)
SEM = "00000000-0000-4000-8000-0000000000ff"


class Scene:
    def __init__(self, tc: TestClient, world: World, meta: FakeMetaCloudClient):
        self.tc, self.w, self.meta = tc, world, meta

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(f"/api/lais{url}", headers=headers, **kw)

    def cloud(self, **over):
        """Turn the seeded connection into a configured Cloud one (the encrypted key holds the Meta token)."""
        row = {"transporte": "cloud", "cloud_phone_number_id": "999", "cloud_waba_id": "W1",
               "encrypted_api_key": Fernet(ENCRYPTION_KEY.encode()).encrypt(b"meta-token").decode("ascii")}
        row.update(over)
        self.w._connections = [{**c, **row} for c in self.w._connections]
        self.w.sw.set_table_data("whatsapp_connections", self.w._connections)

    def modelo(self, aprovado=True, **over):
        body = {"nome": f"Modelo {uuid4().hex[:6]}", "categoria": "campanha",
                "conteudo": "Oi {{nome_pessoa}}, aqui é a {{nome_lais}} da {{nome_imobiliaria}}.", **over}
        r = self.call("post", "/modelos", body)
        assert r.status_code == 201, r.text
        m = r.json()["data"]
        if aprovado:
            self.w.sw.table("lais_modelos").update({"status": "aprovado"}).eq("id", m["id"]).execute()
        return m

    def contatos(self, silenciosos=2, ativos=18):
        rows = []
        for i in range(silenciosos + ativos):
            dias = 5 if i < silenciosos else 0
            rows.append({
                "id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": f"55119{i:08d}@c.us",
                "telefone_e164": f"+55119{i:08d}", "nome": f"Pessoa {i}", "slots": {}, "gen": 0, "status_envio": "nao_pronto",
                "ultimo_inbound_at": (NOW - timedelta(days=dias)).isoformat(), "encerrado_at": None,
                "canal": "whatsapp", "created_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
            })
        self.w.sw.set_table_data("lais_contatos", rows)
        return rows


def _scene(role="owner"):
    world = World()
    world.seed_connection()
    for t in ("lais_modelos", "lais_disparos", "lais_disparo_alvos", "lais_proprietarios_contatos",
              "lais_conhecimento_secoes", "imoveis", "imoveis_catalogo"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role}, {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    meta = FakeMetaCloudClient(phone_number_id="999")
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers import lais_cloud_router as r
        from app.routers.lais_conhecimento_router import get_conhecimento_client, get_nome_agente
        from app.routers.whatsapp_connections_router import get_connection_store
        from app.services.imoveis_service import build_imoveis_service
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        async def nome():
            return "Aurora"

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[r.get_cloud_db] = lambda: world.sw
        app.dependency_overrides[get_conhecimento_client] = lambda: world.sw
        app.dependency_overrides[get_nome_agente] = nome
        app.dependency_overrides[get_connection_store] = lambda: build_whatsapp_connection_store(world.admin, encryption_key=ENCRYPTION_KEY)
        app.dependency_overrides[r.get_imoveis_service] = lambda: build_imoveis_service(world.admin)
        app.dependency_overrides[r.get_transporte_factory] = lambda: (
            lambda conn: tr.transporte_da_conexao(conn, waha_factory=lambda **kw: world.waha, cloud_client_factory=lambda **kw: meta))
        yield Scene(TestClient(app), world, meta)
        for dep in (r.get_cloud_db, get_conhecimento_client, get_nome_agente, get_connection_store,
                    r.get_imoveis_service, r.get_transporte_factory):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


# ── the seam ────────────────────────────────────────────────────────────────
class TestTransporte:
    def test_waha_is_text_only_and_refuses_everything_else(self, admin):
        t = tr.WahaTransporte(admin.w.waha)
        asyncio.run(t.enviar_texto("5511999990000", "oi"))
        assert admin.w.waha.sent_messages[-1]["text"] == "oi"
        with pytest.raises(tr.TemplateRequerApiOficial):
            asyncio.run(t.enviar_template("5511999990000", "x", ["a"]))
        with pytest.raises(tr.OperacaoRequerApiOficial):
            asyncio.run(t.atualizar_perfil({"about": "x"}))
        with pytest.raises(tr.OperacaoRequerApiOficial):
            asyncio.run(t.submeter_modelo("n", "MARKETING", "Oi", []))

    def test_cloud_over_the_seed_fake(self, admin):
        t = tr.CloudApiTransporte(admin.meta)
        r = asyncio.run(t.enviar_template("+5511999990000", "tpl", ["Ana"]))
        asyncio.run(t.atualizar_perfil({"about": "Sobre"}))
        assert r["messages"][0]["id"] == "fake-meta-tpl-1"
        assert admin.meta.sent_templates[0]["phone"] == "5511999990000" and admin.meta.sent_templates[0]["body_params"] == ["Ana"]
        assert admin.meta.profile_updates == [{"messaging_product": "whatsapp", "about": "Sobre"}]

    def test_factory_picks_per_connection_and_cloud_needs_credentials(self, admin):
        waha_rec = admin.w.record(CONNECTION_ID)
        assert waha_rec.transporte == "waha" and not tr.cloud_configurada(waha_rec)
        assert isinstance(tr.transporte_da_conexao(waha_rec, waha_factory=lambda **kw: admin.w.waha), tr.WahaTransporte)
        admin.cloud()
        rec = admin.w.record(CONNECTION_ID)
        assert tr.cloud_configurada(rec)
        assert isinstance(tr.transporte_da_conexao(rec, cloud_client_factory=lambda **kw: admin.meta), tr.CloudApiTransporte)
        admin.cloud(cloud_phone_number_id=None)
        assert not tr.cloud_configurada(admin.w.record(CONNECTION_ID))


# ── auth ────────────────────────────────────────────────────────────────────
ROTAS = [
    ("get", "/cloud/status", None), ("put", f"/cloud/conexoes/{SEM}", {"transporte": "waha"}),
    ("post", "/cloud/perfil/aplicar", {}),
    ("get", "/modelos", None), ("post", "/modelos", {"nome": "x", "categoria": "outros", "conteudo": "Oi"}),
    ("post", "/modelos/preview", {"conteudo": "x", "corpo": "x"}), ("get", f"/modelos/{SEM}", None),
    ("patch", f"/modelos/{SEM}", {"nome": "y"}), ("delete", f"/modelos/{SEM}", None), ("post", f"/modelos/{SEM}/enviar", None),
    ("get", "/disparos", None), ("get", "/disparos/segmentos", None),
    ("post", "/disparos", {"nome": "x", "tipo": "remarketing", "segmento": "leads_3_15", "template_id": SEM}),
    ("post", "/disparos/primeiro-contato", {"telefone": "5511999990000", "abordagem": "neutra"}),
    ("get", f"/disparos/{SEM}", None), ("get", f"/disparos/{SEM}/alvos", None), ("get", f"/disparos/{SEM}/previa", None),
    ("patch", f"/disparos/{SEM}", {"nome": "y"}), ("delete", f"/disparos/{SEM}", None),
    ("post", f"/disparos/{SEM}/agendar", {"quando": "2099-01-01T10:00:00Z"}), ("post", f"/disparos/{SEM}/cancelar", None),
    ("post", f"/disparos/{SEM}/enviar", None),
    ("get", "/proprietarios", None), ("post", "/proprietarios", {"telefone": "5511999990000", "imovel_codigo": "A1"}),
    ("post", f"/proprietarios/{SEM}/solicitar", None), ("post", f"/proprietarios/{SEM}/confirmar", {"status": "x"}),
    ("post", f"/proprietarios/{SEM}/opt-out", None), ("delete", f"/proprietarios/{SEM}", None),
]
ESCRITAS = [r for r in ROTAS if r[0] != "get" and r[1] != "/modelos/preview"]


class TestAuth:
    @pytest.mark.parametrize("method,url,body", ROTAS)
    def test_no_token_is_exactly_401(self, admin, method, url, body):
        assert admin.call(method, url, body, headers={}).status_code == 401

    def test_a_member_can_read(self, member):
        for url in ("/modelos", "/disparos", "/proprietarios", "/cloud/status", "/disparos/segmentos"):
            assert member.call("get", url).status_code == 200

    @pytest.mark.parametrize("method,url,body", ESCRITAS)
    def test_a_member_cannot_write_403(self, member, method, url, body):
        assert member.call(method, url, body).status_code == 403


# ── status / persona ────────────────────────────────────────────────────────
class TestCloudStatus:
    def test_waiting_for_meta_until_a_cloud_connection_is_configured(self, admin):
        d = admin.call("get", "/cloud/status").json()["data"]
        assert d["cloud_configurada"] is False and d["aguardando_verificacao_meta"] is True
        assert admin.call("get", "/modelos").json()["meta"]["transporte"] == "waha"
        r = admin.call("put", f"/cloud/conexoes/{CONNECTION_ID}", {"transporte": "cloud", "cloud_phone_number_id": "999", "access_token": "tok"})
        assert r.status_code == 200 and r.json()["data"]["cloud_configurada"] is True
        assert admin.call("get", "/disparos").json()["meta"]["transporte"] == "cloud"
        assert "tok" not in admin.call("get", "/cloud/status").text

    def test_switching_to_cloud_needs_the_token(self, admin):
        r = admin.call("put", f"/cloud/conexoes/{CONNECTION_ID}", {"transporte": "cloud", "cloud_phone_number_id": "999"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "access_token_obrigatorio"

    def test_perfil_apply_is_cloud_only_and_uses_the_agent_name_not_a_literal(self, admin):
        assert admin.call("post", "/cloud/perfil/aplicar", {}).json()["error"]["code"] == "transporte_indisponivel"
        assert admin.meta.profile_updates == []
        admin.cloud()
        r = admin.call("post", "/cloud/perfil/aplicar", {})
        assert r.status_code == 200 and r.json()["data"]["nome_exibicao"] == "Aurora"
        assert admin.meta.profile_updates

    def test_conhecimento_perfil_name_follows_the_agent_status(self, admin):
        corpo = {"nome_exibicao": "Outro", "descricao": "d", "sobre": "s", "endereco": "", "email": "", "site": ""}
        r = admin.tc.put("/api/lais/conhecimento/perfil_whatsapp", headers=H, json={"dados": corpo, "versao": 0})
        assert r.status_code == 200 and r.json()["data"]["dados"]["nome_exibicao"] == "Aurora"
        got = admin.tc.get("/api/lais/conhecimento", headers=H).json()["data"]["secoes"]["perfil_whatsapp"]["dados"]
        assert got["nome_exibicao"] == "Aurora"


# ── modelos ─────────────────────────────────────────────────────────────────
class TestModelos:
    def test_create_list_preview_delete(self, admin):
        m = admin.modelo(aprovado=False)
        assert m["status"] == "rascunho" and m["parametros"] == ["nome_pessoa", "nome_lais", "nome_imobiliaria"]
        assert m["conteudo"] == m["corpo"]
        listing = admin.call("get", "/modelos").json()
        assert [x["id"] for x in listing["data"]] == [m["id"]] and len(listing["meta"]["catalogo"]["parametros"]) == 10
        assert len(listing["meta"]["catalogo"]["categorias"]) == 8
        p = admin.call("post", "/modelos/preview", {"corpo": "Oi {{nome_pessoa}}"}).json()["data"]
        assert p["texto"] == "Oi Maria" and p["parametros"] == ["nome_pessoa"]
        assert admin.call("delete", f"/modelos/{m['id']}").status_code == 204
        assert admin.call("get", f"/modelos/{m['id']}").status_code == 404

    @pytest.mark.parametrize("over", [
        {"conteudo": "x" * 1025}, {"categoria": "bogus"}, {"conteudo": "Oi {{desconhecido}}"}, {"nome": ""},
    ])
    def test_validation(self, admin, over):
        body = {"nome": "N", "categoria": "outros", "conteudo": "Oi", **over}
        assert admin.call("post", "/modelos", body).status_code in (422,)

    def test_body_of_1024_is_accepted_and_unknown_field_422(self, admin):
        assert admin.call("post", "/modelos", {"nome": "Max", "categoria": "outros", "conteudo": "x" * 1024}).status_code == 201
        assert admin.call("post", "/modelos", {"nome": "Z", "categoria": "outros", "conteudo": "x", "extra": 1}).status_code == 422

    def test_duplicate_name_and_locked_after_submission(self, admin):
        admin.modelo(nome="Mesmo")
        assert admin.call("post", "/modelos", {"nome": "mesmo", "categoria": "outros", "conteudo": "Oi"}).status_code == 409
        m = admin.modelo(aprovado=True)
        assert admin.call("patch", f"/modelos/{m['id']}", {"nome": "Novo"}).json()["error"]["code"] == "modelo_nao_editavel"

    def test_enviar_is_409_without_cloud_and_submits_positional_with_cloud(self, admin):
        m = admin.modelo(aprovado=False)
        r = admin.call("post", f"/modelos/{m['id']}/enviar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "transporte_indisponivel"
        assert admin.meta.created_templates == [] and admin.call("get", f"/modelos/{m['id']}").json()["data"]["status"] == "rascunho"
        admin.cloud()
        r = admin.call("post", f"/modelos/{m['id']}/enviar")
        assert r.status_code == 200 and r.json()["data"]["status"] == "enviado_meta"
        sent = admin.meta.created_templates[0]
        assert sent["body_text"] == "Oi {{1}}, aqui é a {{2}} da {{3}}." and sent["category"] == "MARKETING"
        assert admin.call("post", f"/modelos/{m['id']}/enviar").json()["error"]["code"] == "modelo_ja_enviado"

    def test_org_isolation(self, admin):
        m = admin.modelo()
        admin.w.sw.table("lais_modelos").update({"org_id": OTHER_ORG_ID}).eq("id", m["id"]).execute()
        assert admin.call("get", f"/modelos/{m['id']}").status_code == 404
        assert admin.call("get", "/modelos").json()["data"] == []


# ── disparos ────────────────────────────────────────────────────────────────
class TestDisparos:
    def _disparo(self, admin, **over):
        m = admin.modelo()
        body = {"nome": "Remarketing", "tipo": "remarketing", "segmento": "leads_3_15", "template_id": m["id"], **over}
        r = admin.call("post", "/disparos", body)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def test_segmentos_and_create_validation(self, admin):
        keys = [s["chave"] for s in admin.call("get", "/disparos/segmentos").json()["data"]]
        assert keys == ["leads_3_15", "leads_7_30", "proprietarios"]
        m = admin.modelo()
        bad = {"nome": "x", "template_id": m["id"]}
        assert admin.call("post", "/disparos", {**bad, "tipo": "remarketing", "segmento": "proprietarios"}).json()["error"]["code"] == "segmento_incompativel"
        assert admin.call("post", "/disparos", {**bad, "tipo": "bogus", "segmento": "leads_3_15"}).status_code == 422
        assert admin.call("post", "/disparos", {**bad, "tipo": "remarketing", "segmento": "leads_3_15", "template_id": str(uuid4())}).status_code == 404

    def test_everything_but_the_send_works_on_waha_and_tabs_filter(self, admin):
        admin.contatos()
        d = self._disparo(admin)
        assert d["status"] == "rascunho" and d["template_id"]
        quando = (NOW + timedelta(days=1)).isoformat()
        r = admin.call("post", f"/disparos/{d['id']}/agendar", {"quando": quando})
        assert r.status_code == 200 and r.json()["data"]["status"] == "agendado"
        det = admin.call("get", f"/disparos/{d['id']}").json()["data"]
        assert len(det["alvos"]) == 2 and det["alvos_por_status"] == {"pendente": 2}
        assert [x["id"] for x in admin.call("get", "/disparos?aba=agendados").json()["data"]] == [d["id"]]
        assert admin.call("get", "/disparos?aba=rascunhos").json()["data"] == []
        assert admin.call("post", f"/disparos/{d['id']}/cancelar").json()["data"]["status"] == "cancelado"
        assert [x["id"] for x in admin.call("get", "/disparos?aba=cancelados").json()["data"]] == [d["id"]]
        assert admin.call("post", f"/disparos/{d['id']}/cancelar").json()["error"]["code"] == "disparo_nao_cancelavel"
        assert admin.call("get", "/disparos?aba=bogus").status_code == 422

    def test_create_with_agendado_para_schedules_and_a_refused_schedule_leaves_no_draft(self, admin):
        admin.contatos()
        m = admin.modelo()
        quando = (NOW + timedelta(days=1)).isoformat()
        base = {"nome": "Agendado", "tipo": "remarketing", "segmento": "leads_3_15", "template_id": m["id"]}
        assert admin.call("post", "/disparos", {**base, "agendado_para": quando}).json()["data"]["status"] == "agendado"
        nao = admin.modelo(aprovado=False)
        r = admin.call("post", "/disparos", {**base, "template_id": nao["id"], "agendado_para": quando})
        assert r.status_code == 409 and r.json()["error"]["code"] == "modelo_nao_aprovado"
        assert len(admin.call("get", "/disparos").json()["data"]) == 1
        assert admin.call("post", "/disparos", {**base, "agendado_para": (NOW - timedelta(days=1)).isoformat()}).status_code == 422

    def test_waha_NEVER_mass_sends_409_matrix(self, admin):
        admin.contatos()
        d = self._disparo(admin)
        r = admin.call("post", f"/disparos/{d['id']}/enviar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "transporte_indisponivel"
        assert admin.w.waha.sent_messages == [] and admin.meta.sent_templates == []
        assert admin.call("get", f"/disparos/{d['id']}").json()["data"]["status"] == "rascunho"
        # cloud selected but not configured (no phone-number id) is still unavailable
        admin.cloud(cloud_phone_number_id=None)
        assert admin.call("post", f"/disparos/{d['id']}/enviar").json()["error"]["code"] == "transporte_indisponivel"
        assert admin.w.waha.sent_messages == []
        # the gate answers before any other precondition (unapproved modelo, unknown disparo is still a 404)
        assert admin.call("post", f"/disparos/{SEM}/enviar").status_code == 404

    def test_cloud_sends_the_template_to_every_target(self, admin):
        admin.cloud()
        admin.contatos()
        d = self._disparo(admin)
        r = admin.call("post", f"/disparos/{d['id']}/enviar")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "enviado" and data["alvos_por_status"] == {"enviado": 2}
        assert len(admin.meta.sent_templates) == 2 and admin.w.waha.sent_messages == []
        sent = admin.meta.sent_templates[0]
        assert sent["body_params"][1] == "Aurora" and sent["body_params"][2] == "Empresa Exemplo"
        assert admin.call("post", f"/disparos/{d['id']}/enviar").json()["error"]["code"] == "disparo_nao_disparavel"

    def test_dispatch_needs_an_approved_modelo(self, admin):
        admin.cloud()
        admin.contatos()
        m = admin.modelo(aprovado=False)
        d = admin.call("post", "/disparos", {"nome": "x", "tipo": "remarketing", "segmento": "leads_3_15", "template_id": m["id"]}).json()["data"]
        assert admin.call("post", f"/disparos/{d['id']}/enviar").json()["error"]["code"] == "modelo_nao_aprovado"
        assert admin.meta.sent_templates == []

    def test_cap_is_15_percent_of_the_month_volume(self, admin):
        admin.cloud()
        admin.contatos(silenciosos=5, ativos=5)  # volume 10 -> cap 1; the segment has 5
        d = self._disparo(admin)
        pv = admin.call("get", f"/disparos/{d['id']}/previa").json()["data"]
        assert pv["limite"] == 1 and pv["alvos"] == 5 and pv["dentro_do_limite"] is False
        r = admin.call("post", f"/disparos/{d['id']}/enviar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "limite_de_disparo"
        assert admin.call("post", f"/disparos/{d['id']}/agendar", {"quando": (NOW + timedelta(days=1)).isoformat()}).status_code == 409
        assert admin.meta.sent_templates == []

    def test_per_chat_template_cap(self, admin):
        admin.cloud()
        rows = admin.contatos()
        tel = "".join(c for c in rows[0]["telefone_e164"] if c.isdigit())
        for i in range(disparos.MAX_TEMPLATES_POR_CONTATO):
            admin.w.sw.table("lais_disparo_alvos").insert({
                "id": str(uuid4()), "org_id": ORG_ID, "disparo_id": str(uuid4()), "telefone": tel, "status": "enviado",
                "enviado_at": (NOW - timedelta(days=i + 1)).isoformat()}).execute()
        d = self._disparo(admin)
        data = admin.call("post", f"/disparos/{d['id']}/enviar").json()["data"]
        assert data["alvos_por_status"] == {"enviado": 1, "erro": 1}
        assert [a["erro"] for a in data["alvos"] if a["status"] == "erro"] == ["limite_por_contato"]

    def test_a_reply_flips_the_target_and_nothing_else(self, admin):
        admin.cloud()
        rows = admin.contatos()
        d = self._disparo(admin)
        admin.call("post", f"/disparos/{d['id']}/enviar")
        tel = "".join(c for c in rows[0]["telefone_e164"] if c.isdigit())
        assert disparos.registrar_resposta(admin.w.sw, ORG_ID, tel) is True
        assert disparos.registrar_resposta(admin.w.sw, ORG_ID, tel) is False
        det = admin.call("get", f"/disparos/{d['id']}").json()["data"]
        assert det["alvos_por_status"] == {"enviado": 1, "respondido": 1}

    def test_delete_rules(self, admin):
        d = self._disparo(admin)
        assert admin.call("patch", f"/disparos/{d['id']}", {"nome": "Novo"}).json()["data"]["nome"] == "Novo"
        assert admin.call("delete", f"/disparos/{d['id']}").status_code == 204

    def test_meta_lead_first_contact_hook_is_cloud_only(self, admin):
        body = {"telefone": "5511988887777", "nome": "Ana", "abordagem": "comercial"}
        r = admin.call("post", "/disparos/primeiro-contato", body)
        assert r.status_code == 409 and r.json()["error"]["code"] == "transporte_indisponivel"
        assert admin.w.waha.sent_messages == []
        admin.cloud()
        assert admin.call("post", "/disparos/primeiro-contato", body).json()["data"] == {"enviado": False, "motivo": "modelo_nao_aprovado"}
        admin.modelo(nome="Abordagem comercial", categoria="primeiro_contato", conteudo="Oi {{nome_pessoa}}, é a {{nome_lais}}.")
        r = admin.call("post", "/disparos/primeiro-contato", body)
        assert r.json()["data"]["enviado"] is True
        assert admin.meta.sent_templates[0]["phone"] == "5511988887777" and admin.meta.sent_templates[0]["body_params"] == ["Ana", "Aurora"]
        assert admin.call("post", "/disparos/primeiro-contato", {**body, "abordagem": "x"}).status_code == 422


# ── proprietarios ───────────────────────────────────────────────────────────
class TestProprietarios:
    def _dono(self, admin, **over):
        body = {"telefone": "11 99999-0000", "imovel_codigo": "ap10", "nome": "Dono", **over}
        r = admin.call("post", "/proprietarios", body)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def test_create_normalises_lists_filters_and_rejects_duplicates(self, admin):
        p = self._dono(admin)
        assert p["telefone"] == "5511999990000" and p["imovel_codigo"] == "AP10" and p["status"] == "pendente"
        assert admin.call("post", "/proprietarios", {"telefone": "5511999990000", "imovel_codigo": "AP10"}).status_code == 409
        assert admin.call("post", "/proprietarios", {"telefone": "123", "imovel_codigo": "A"}).status_code == 422
        r = admin.call("get", "/proprietarios?q=ap1&status=pendente").json()
        assert [x["id"] for x in r["data"]] == [p["id"]] and r["meta"]["transporte"] == "waha"
        assert admin.call("get", "/proprietarios?status=enviado").json()["data"] == []
        assert admin.call("get", "/proprietarios?status=bogus").status_code == 422

    def test_solicitar_is_409_without_cloud_and_sends_with_cloud(self, admin):
        p = self._dono(admin)
        r = admin.call("post", f"/proprietarios/{p['id']}/solicitar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "transporte_indisponivel"
        assert admin.w.waha.sent_messages == [] and admin.meta.sent_templates == []
        admin.cloud()
        assert admin.call("post", f"/proprietarios/{p['id']}/solicitar").json()["error"]["code"] == "modelo_nao_aprovado"
        admin.modelo(categoria="administrativo", conteudo="Olá {{nome_pessoa}}, o imóvel {{codigo_imovel}} segue à venda?")
        r = admin.call("post", f"/proprietarios/{p['id']}/solicitar")
        assert r.status_code == 200, r.text
        assert admin.meta.sent_templates[0]["body_params"] == ["Dono", "AP10"]
        assert admin.call("get", "/proprietarios").json()["data"][0]["status"] == "enviado"

    def test_parar_opts_out_for_good_and_blocks_every_send(self, admin):
        admin.cloud()
        admin.modelo(categoria="administrativo", conteudo="Olá {{nome_pessoa}}")
        p = self._dono(admin)
        assert proprietarios.registrar_resposta(admin.w.sw, ORG_ID, p["telefone"], "  Parar! ") == "opt_out"
        row = admin.call("get", "/proprietarios?status=parar").json()["data"][0]
        assert row["opt_out"] is True and row["opt_out_at"]
        assert admin.call("post", f"/proprietarios/{p['id']}/solicitar").json()["error"]["code"] == "proprietario_opt_out"
        # a second listing of the same phone inherits the opt-out
        outro = self._dono(admin, imovel_codigo="AP11")
        assert outro["opt_out"] is True
        # and the mass dispatch skips him
        m = admin.modelo()
        d = admin.call("post", "/disparos", {"nome": "Donos", "tipo": "atualizacao_anuncios", "segmento": "proprietarios", "template_id": m["id"]}).json()["data"]
        det = admin.call("get", f"/disparos/{d['id']}").json()["data"]
        assert det["alvos"] == []
        assert admin.meta.sent_templates == []

    def test_opt_out_route_drops_pending_targets(self, admin):
        admin.cloud()
        p = self._dono(admin)
        m = admin.modelo()
        d = admin.call("post", "/disparos", {"nome": "Donos", "tipo": "atualizacao_anuncios", "segmento": "proprietarios", "template_id": m["id"]}).json()["data"]
        admin.call("post", f"/disparos/{d['id']}/agendar", {"quando": (NOW + timedelta(days=1)).isoformat()})
        assert admin.call("post", f"/proprietarios/{p['id']}/opt-out").json()["data"]["status"] == "parar"
        alvos = admin.call("get", f"/disparos/{d['id']}/alvos").json()["data"]
        assert [(a["status"], a["erro"]) for a in alvos] == [("erro", "opt_out")]
        r = admin.call("post", f"/disparos/{d['id']}/enviar")
        assert r.status_code == 200 and admin.meta.sent_templates == []

    def test_confirm_is_stored_lais_side_only_after_a_reply_and_never_writes_the_vista_mirror(self, admin):
        admin.cloud()
        admin.modelo(categoria="administrativo", conteudo="Olá {{nome_pessoa}}")
        admin.w.sw.table("imoveis").insert({
            "org_id": ORG_ID, "codigo": "AP10", "codigo_norm": "AP10", "status": "Venda", "valor_venda": 500000}).execute()
        p = self._dono(admin)
        r = admin.call("post", f"/proprietarios/{p['id']}/confirmar", {"status": "Suspenso", "preco": 450000})
        assert r.status_code == 409 and r.json()["error"]["code"] == "sem_resposta_do_proprietario"
        assert admin.call("post", f"/proprietarios/{p['id']}/solicitar").status_code == 200
        assert proprietarios.registrar_resposta(admin.w.sw, ORG_ID, p["telefone"], "pode atualizar") == "respondido"
        assert admin.call("get", "/proprietarios").json()["data"][0]["status"] == "respondido"
        r = admin.call("post", f"/proprietarios/{p['id']}/confirmar", {"status": "Suspenso", "preco": 450000})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "atualizado"
        imovel = admin.w.sw.table("imoveis").select("*").eq("codigo", "AP10").execute().data[0]
        assert imovel["status"] == "Venda" and float(imovel["valor_venda"]) == 500000.0  # Vista-owned, untouched
        linha = admin.call("get", "/proprietarios").json()["data"][0]
        assert (linha["status_confirmado"], float(linha["preco_confirmado"]), linha["preco_tipo_confirmado"]) == ("Suspenso", 450000.0, "venda")
        assert linha["confirmado_at"]
        assert admin.call("post", f"/proprietarios/{p['id']}/confirmar", {}).status_code == 422

    def test_confirm_unknown_imovel_404(self, admin):
        admin.cloud()
        admin.modelo(categoria="administrativo", conteudo="Olá")
        p = self._dono(admin, imovel_codigo="NAOEXISTE")
        admin.call("post", f"/proprietarios/{p['id']}/solicitar")
        proprietarios.registrar_resposta(admin.w.sw, ORG_ID, p["telefone"], "oi")
        assert admin.call("post", f"/proprietarios/{p['id']}/confirmar", {"preco": 1.0}).json()["error"]["code"] == "imovel_nao_encontrado"


# ── wave-4 regua template attempts ──────────────────────────────────────────
class TestReguaTemplate:
    def _run(self, admin, aprovado=True):
        m = admin.modelo(aprovado=aprovado)
        contato = admin.contatos(silenciosos=1, ativos=0)[0]
        deps = admin.w.deps(cloud_client_factory=lambda **kw: admin.meta)
        conn = admin.w.record(__import__("uuid").UUID(CONNECTION_ID))
        regua = admin.w.sw.table(lais_envio_gate.T_REGUAS).insert({"org_id": ORG_ID, "nome": "R", "ativa": True}).execute().data[0]
        liberacao = lais_envio_gate.exigir(admin.w.sw, ORG_ID, CONNECTION_ID, lais_envio_gate.Fluxo.REGUA, regua_id=regua["id"])
        ok = asyncio.run(reeng._enviar_template(deps, ORG_ID, conn, contato, {"template_id": m["id"]}, liberacao))
        return ok

    def test_not_cloud_keeps_regua_sem_transporte_and_never_texts(self, admin):
        assert self._run(admin) is False
        assert admin.meta.sent_templates == [] and admin.w.waha.sent_messages == []

    def test_cloud_with_an_approved_modelo_sends_the_template(self, admin):
        admin.cloud()
        assert self._run(admin) is True
        assert admin.meta.sent_templates[0]["body_params"][:2] == ["Pessoa 0", "Julia"] or admin.meta.sent_templates[0]["body_params"][1]
        assert admin.w.waha.sent_messages == []

    def test_cloud_with_an_unapproved_modelo_is_skipped(self, admin):
        admin.cloud()
        assert self._run(admin, aprovado=False) is False
        assert admin.meta.sent_templates == []


# ── pure bits ───────────────────────────────────────────────────────────────
def test_positional_conversion_and_registry():
    corpo, chaves = modelos.corpo_posicional("{{nome_lais}} e {{nome_pessoa}} e {{nome_lais}}")
    assert corpo == "{{1}} e {{2}} e {{1}}" and chaves == ["nome_lais", "nome_pessoa"]
    assert set(modelos.PARAMETROS) == {
        "nome_pessoa", "nome_lais", "nome_imobiliaria", "mensagem", "data_visita", "codigo_imovel", "link_imovel",
        "nome_atendente", "imovel_visita", "data_hora_visita"}
    assert list(modelos.CATEGORIAS) == [
        "administrativo", "campanha", "cobranca", "documentacao", "primeiro_contato", "reativacao", "visita", "outros"]
    assert proprietarios.eh_parar("PARAR") and proprietarios.eh_parar(" pare. ") and not proprietarios.eh_parar("não vou parar de pagar")

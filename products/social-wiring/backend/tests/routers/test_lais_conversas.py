"""Lais wave 7 -- Conversas v2 (contract section 9 + A7): the ownership access matrix on every per-contato
route, list / kanban-by-tag, contato mutations, notes, feedback, tags, archive / block behaviour and the
attendant-name prefix. Strict status codes; every route is strict `== 401` without a session.

Seams: mock DB, seed `FakeWahaClient`, fake buffer / redis / bus -- nothing of ours is patched."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import lais_acesso, lais_conversas_service as svc
from app.services import lais_contatos_service as contatos
from app.services.lais_lead_turn_service import process_lead_batch

from tests.support.lais_world import (
    ADMIN_ID, CONNECTION_ID, ENCRYPTION_KEY, LEAD_CHAT, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World, buffer_lead,
)

H = {"Authorization": "Bearer test-token"}
OUTRO = "00000000-0000-4000-8000-0000000000d9"  # another member of the org


def _novo_contato(w, chat, **over):
    """A contato with a real UUID id (the route's path params are typed `UUID`; the mock's ids are not)."""
    base = {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": chat, "gen": 0, "slots": {},
            "canal": "whatsapp", "status_envio": "nao_pronto", "arquivado": False, "bloqueado": False,
            "responsavel_user_id": None, "operacao": None}
    w.sw.table("lais_contatos").insert({**base, **over}).execute()


def _mundo(*, conn_owner: str = OWNER_ID):
    w = World()
    for t in ("lais_etiquetas", "lais_contato_etiquetas", "lais_notas", "lais_feedback", "lais_visitas",
              "lais_conhecimento_secoes"):
        w.sw.set_table_data(t, [])
    w.seed_connection(user_id=conn_owner)
    _novo_contato(w, LEAD_CHAT, nome="Ana", telefone_e164="+5511988887777")
    return w, w.contato()


class Scene:
    def __init__(self, tc, world, contato):
        self.tc, self.w, self.contato = tc, world, contato
        self.cid = contato["id"]

    def get(self, url, **kw):
        return self.tc.get(url, headers=H, **kw)

    def post(self, url, json=None, **kw):
        return self.tc.post(url, json=json if json is not None else {}, headers=H, **kw)

    def patch(self, url, json=None, **kw):
        return self.tc.patch(url, json=json if json is not None else {}, headers=H, **kw)

    def delete(self, url, **kw):
        return self.tc.delete(url, headers=H, **kw)

    def dono(self, user_id):
        contatos.atualizar_contato(self.w.sw, self.cid, {"responsavel_user_id": user_id})

    def outro_contato(self, chat="5511977776666@c.us", **over):
        _novo_contato(self.w, chat, nome="Bia", **over)
        return self.w.contato(chat)


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    stub = _settings.model_copy(update={"encryption_key": ENCRYPTION_KEY})
    app.dependency_overrides[get_settings] = lambda: stub
    yield
    app.dependency_overrides.pop(get_settings, None)


def _scene(role, *, conn_owner=OWNER_ID, nome="Carla Souza"):
    w, contato = _mundo(conn_owner=conn_owner)
    w.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
        {"id": OUTRO, "org_id": ORG_ID, "org_role": "member"},
    ])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id=ORG_ID, org_role=role, extra_metadata={"full_name": nome} if nome else None)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.lais_conversas_router import get_conversas_client
        from app.routers.whatsapp_connections_router import get_waha_client_factory

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_conversas_client] = lambda: w.sw
        app.dependency_overrides[get_waha_client_factory] = lambda: (lambda **kw: w.waha)
        yield Scene(TestClient(app), w, contato)
        app.dependency_overrides.pop(get_conversas_client, None)
        app.dependency_overrides.pop(get_waha_client_factory, None)


@pytest.fixture
def admin(override_settings_factory):
    yield from _scene("owner")


@pytest.fixture
def org_admin(override_settings_factory):
    yield from _scene("admin")


@pytest.fixture
def member(override_settings_factory):
    yield from _scene("member")


@pytest.fixture
def member_conn_owner(override_settings_factory):
    """A plain member who OWNS the connection the contato came in on."""
    yield from _scene("member", conn_owner=TEST_USER_ID)


def _rotas(cid):
    """Every per-contato route, as (method, url, body)."""
    return [
        ("get", f"/api/lais/historico/{cid}", None),
        ("patch", f"/api/lais/contatos/{cid}", {"arquivado": False}),
        ("get", f"/api/lais/contatos/{cid}/notas", None),
        ("post", f"/api/lais/contatos/{cid}/notas", {"texto": "ligar amanhã"}),
        ("post", f"/api/lais/contatos/{cid}/feedback", {"nota": "like"}),
        ("get", f"/api/lais/contatos/{CONNECTION_ID}/{LEAD_CHAT}", None),
    ]


def _chamar(s, metodo, url, corpo):
    f = getattr(s, metodo)
    return f(url) if corpo is None else f(url, corpo)


# ── strict 401 ──────────────────────────────────────────────────────────────
class TestAuth:
    @pytest.mark.parametrize("metodo,url,corpo", [
        ("get", "/api/lais/conversas", None),
        ("get", "/api/lais/conversas?view=kanban", None),
        ("get", "/api/lais/etiquetas", None),
        ("post", "/api/lais/etiquetas", {"nome": "x"}),
        ("patch", f"/api/lais/etiquetas/{uuid4()}", {"nome": "x"}),
        ("delete", f"/api/lais/etiquetas/{uuid4()}", None),
        ("delete", f"/api/lais/contatos/{uuid4()}/notas/{uuid4()}", None),
        *_rotas(uuid4()),
    ])
    def test_no_token_is_401(self, admin, metodo, url, corpo):
        r = getattr(admin.tc, metodo)(url, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 401


# ── A7: the ownership matrix ────────────────────────────────────────────────
class TestMatrizDeAcesso:
    @pytest.mark.parametrize("idx", range(6))
    def test_owner_sees_every_contato(self, admin, idx):
        m, u, b = _rotas(admin.cid)[idx]
        assert _chamar(admin, m, u, b).status_code in (200, 201)

    @pytest.mark.parametrize("idx", range(6))
    def test_admin_sees_every_contato(self, org_admin, idx):
        m, u, b = _rotas(org_admin.cid)[idx]
        assert _chamar(org_admin, m, u, b).status_code in (200, 201)

    @pytest.mark.parametrize("idx", range(6))
    def test_the_responsavel_member_has_access(self, member, idx):
        member.dono(TEST_USER_ID)
        m, u, b = _rotas(member.cid)[idx]
        assert _chamar(member, m, u, b).status_code in (200, 201)

    @pytest.mark.parametrize("idx", range(6))
    def test_the_connection_owner_has_access_when_nobody_is_responsavel(self, member_conn_owner, idx):
        m, u, b = _rotas(member_conn_owner.cid)[idx]
        assert _chamar(member_conn_owner, m, u, b).status_code in (200, 201)

    @pytest.mark.parametrize("idx", range(6))
    def test_another_member_of_the_org_is_403_sem_acesso(self, member, idx):
        member.dono(OUTRO)
        m, u, b = _rotas(member.cid)[idx]
        r = _chamar(member, m, u, b)
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"

    @pytest.mark.parametrize("idx", range(6))
    def test_a_member_who_is_not_responsavel_nor_connection_owner_is_403(self, member, idx):
        m, u, b = _rotas(member.cid)[idx]  # no responsavel, connection owned by OWNER_ID
        r = _chamar(member, m, u, b)
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"

    def test_a_responsavel_elsewhere_beats_connection_ownership(self, member_conn_owner):
        member_conn_owner.dono(OUTRO)
        r = member_conn_owner.get(f"/api/lais/historico/{member_conn_owner.cid}")
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"

    @pytest.mark.parametrize("papel", ["owner", "member"])
    def test_another_orgs_contato_is_404_never_403(self, override_settings_factory, papel):
        for s in _scene(papel):
            s.w.sw.table("lais_contatos").update({"org_id": OTHER_ORG_ID}).eq("id", s.cid).execute()
            for m, u, b in _rotas(s.cid)[:5]:
                r = _chamar(s, m, u, b)
                assert r.status_code == 404 and r.json()["error"]["code"] == "contato_nao_encontrado", (m, u)

    def test_unknown_contato_is_404_like_another_orgs(self, admin):
        r = admin.get(f"/api/lais/historico/{uuid4()}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "contato_nao_encontrado"

    def test_predicate_unit(self):
        ctx = lais_acesso.AcessoCtx(org_id=ORG_ID, user_id="u1", admin=False)
        c = {"org_id": ORG_ID, "connection_id": "c1", "responsavel_user_id": None}
        assert lais_acesso.pode_ver_contato(ctx, c, {"c1": "u1"})
        assert not lais_acesso.pode_ver_contato(ctx, c, {"c1": "u2"})
        assert not lais_acesso.pode_ver_contato(ctx, c)  # no donos and no client: fail closed
        assert lais_acesso.pode_ver_contato(ctx, {**c, "responsavel_user_id": "u1"}, {"c1": "u2"})
        assert not lais_acesso.pode_ver_contato(ctx, {**c, "org_id": OTHER_ORG_ID}, {"c1": "u1"})
        assert lais_acesso.pode_ver_contato(lais_acesso.AcessoCtx(org_id=ORG_ID, user_id="x", admin=True), c, {})
        assert not lais_acesso.pode_ver_contato(lais_acesso.AcessoCtx(org_id=ORG_ID, user_id="x", admin=True), {**c, "org_id": OTHER_ORG_ID}, {})


class TestVisitasGuardadas:
    def _visita(self, s, contato_id):
        s.w.sw.table("lais_visitas").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "contato_id": contato_id, "operacao": "venda",
            "inicio": "2026-10-20T12:00:00+00:00", "fim": "2026-10-20T12:30:00+00:00", "status": "solicitada"}).execute()

    def test_a_member_lists_only_the_visits_of_contatos_they_own(self, member):
        member.dono(TEST_USER_ID)
        alheio = member.outro_contato(responsavel_user_id=OUTRO)
        self._visita(member, member.cid)
        self._visita(member, alheio["id"])
        member.w.sw.table("lais_visitas").update({"inicio": "2026-10-20T13:00:00+00:00", "fim": "2026-10-20T13:30:00+00:00"}).eq("contato_id", alheio["id"]).execute()
        r = member.get("/api/lais/visitas?view=semana&data=2026-10-20")
        assert r.status_code == 200 and [v["contato_id"] for v in r.json()["data"]] == [member.cid]

    def test_an_admin_lists_every_visit(self, admin):
        alheio = admin.outro_contato(responsavel_user_id=OUTRO)
        self._visita(admin, admin.cid)
        self._visita(admin, alheio["id"])
        admin.w.sw.table("lais_visitas").update({"inicio": "2026-10-20T13:00:00+00:00", "fim": "2026-10-20T13:30:00+00:00"}).eq("contato_id", alheio["id"]).execute()
        assert len(admin.get("/api/lais/visitas?view=semana&data=2026-10-20").json()["data"]) == 2

    def test_acting_on_a_strangers_visit_is_403(self, member):
        member.dono(OUTRO)
        self._visita(member, member.cid)
        vid = member.w.rows("lais_visitas")[0]["id"]
        for acao in ("confirmar", "cancelar"):
            r = member.post(f"/api/lais/visitas/{vid}/{acao}")
            assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"
        assert member.w.rows("lais_visitas")[0]["status"] == "solicitada"


# ── history shape ───────────────────────────────────────────────────────────
class TestHistorico:
    def test_shape_interacoes_and_mensagens_oldest_first(self, admin):
        w = admin.w
        w.sw.table("lais_interacoes").insert({
            "org_id": ORG_ID, "contato_id": admin.cid, "iniciada_at": "2026-10-14T10:00:00+00:00", "tipo": "comercial",
            "resumo": "quer apto", "slots": {}, "intencoes": ["comprar"]}).execute()
        w.sw.table("conversation_messages").insert([
            {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "direction": "inbound",
             "body": "oi", "created_at": "2026-10-14T10:00:00+00:00", "provider_message_id": "a"},
            {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "direction": "outbound",
             "body": "olá", "created_at": "2026-10-14T10:00:05+00:00", "provider_message_id": "b"},
        ]).execute()
        r = admin.get(f"/api/lais/historico/{admin.cid}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert set(d) == {"contato", "interacoes", "mensagens"}
        assert d["contato"]["id"] == admin.cid == d["contato"]["contato_id"] and d["contato"]["nome"] == "Ana"
        assert d["contato"]["visitas"] == [] and "telefone" in d["contato"] and "nao_lidas" in d["contato"]
        assert d["interacoes"][0]["resumo"] == "quer apto"
        assert [m["body"] for m in d["mensagens"]] == ["oi", "olá"]

    def test_the_other_orgs_messages_never_leak(self, admin):
        admin.w.sw.table("conversation_messages").insert({
            "id": str(uuid4()), "org_id": OTHER_ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT,
            "direction": "inbound", "body": "segredo", "created_at": "2026-10-14T10:00:00+00:00", "provider_message_id": "z"}).execute()
        assert admin.get(f"/api/lais/historico/{admin.cid}").json()["data"]["mensagens"] == []


# ── list + kanban ───────────────────────────────────────────────────────────
class TestLista:
    def _chat(self, s, contato, pausado=False):
        s.w.seed_chat(contato["chat_id"], agente_pausado=pausado)

    def test_tabs(self, admin):
        b = admin.outro_contato("5511900000001@c.us", arquivado=True)
        c = admin.outro_contato("5511900000002@c.us", responsavel_user_id=TEST_USER_ID)
        todas = {i["id"] for i in admin.get("/api/lais/conversas").json()["data"]}
        assert todas == {admin.cid, c["id"]}
        minhas = {i["id"] for i in admin.get("/api/lais/conversas?aba=minhas").json()["data"]}
        assert minhas == {c["id"]}
        arq = admin.get("/api/lais/conversas?aba=arquivadas")
        assert {i["id"] for i in arq.json()["data"]} == {b["id"]} and arq.json()["meta"]["total"] == 1

    def test_a_member_only_sees_their_own(self, member):
        member.dono(TEST_USER_ID)
        member.outro_contato("5511900000003@c.us", responsavel_user_id=OUTRO)
        itens = member.get("/api/lais/conversas").json()["data"]
        assert [i["id"] for i in itens] == [member.cid]

    def test_filters(self, admin):
        a = admin.contato
        contatos.atualizar_contato(admin.w.sw, a["id"], {"operacao": "venda", "status_envio": "enviado"})
        b = admin.outro_contato("5511900000004@c.us", operacao="aluguel", responsavel_user_id=MEMBER_ID)
        self._chat(admin, a, pausado=True)
        self._chat(admin, b, pausado=False)
        ids = lambda q: {i["id"] for i in admin.get(f"/api/lais/conversas?{q}").json()["data"]}
        assert ids("operacao=venda") == {a["id"]}
        assert ids("status_sw=enviado") == {a["id"]}
        assert ids("atendimento=manual") == {a["id"]}
        assert ids("atendimento=julia") == {b["id"]}
        assert ids(f"responsavel={MEMBER_ID}") == {b["id"]}
        assert ids("q=bia") == {b["id"]}
        assert ids("operacao=venda,aluguel") == {a["id"], b["id"]}
        assert ids("status_sw=enviado,nao_pronto") == {a["id"], b["id"]}
        assert ids("atendimento=julia,manual") == {a["id"], b["id"]}
        assert ids(f"responsavel=sem,{MEMBER_ID}") == {a["id"], b["id"]}
        assert ids("responsavel=sem") == {a["id"]}

    def test_unknown_equipe_filters_everything_out(self, admin):
        r = admin.get(f"/api/lais/conversas?equipe={uuid4()}")
        assert r.status_code == 200 and "equipe_ignorada" not in r.json()["meta"]
        assert r.json()["data"] == []

    @pytest.mark.parametrize("q", ["aba=outra", "view=grid", "atendimento=robo", "atendimento=julia,robo", "limit=0", "responsavel=nao-uuid"])
    def test_bad_params_are_422(self, admin, q):
        assert admin.get(f"/api/lais/conversas?{q}").status_code == 422

    def test_pagination(self, admin):
        for i in range(4):
            admin.outro_contato(f"55119000001{i}0@c.us")
        r = admin.get("/api/lais/conversas?limit=2&offset=2").json()
        assert len(r["data"]) == 2 and r["meta"]["total"] == 5

    def test_another_orgs_contatos_are_never_listed(self, admin):
        admin.w.sw.table("lais_contatos").insert({
            "id": str(uuid4()), "org_id": OTHER_ORG_ID, "connection_id": CONNECTION_ID, "chat_id": "x@c.us",
            "arquivado": False, "bloqueado": False, "gen": 0, "slots": {}, "canal": "whatsapp", "status_envio": "nao_pronto"}).execute()
        assert len(admin.get("/api/lais/conversas").json()["data"]) == 1


class TestKanban:
    def test_columns_todas_one_per_etiqueta_arquivadas(self, admin):
        s = admin
        e1 = s.post("/api/lais/etiquetas", {"nome": "Quente", "cor": "#ff0000"}).json()["data"]
        e2 = s.post("/api/lais/etiquetas", {"nome": "Frio"}).json()["data"]
        b = s.outro_contato("5511900000005@c.us")
        arq = s.outro_contato("5511900000006@c.us", arquivado=True)
        assert s.patch(f"/api/lais/contatos/{s.cid}", {"etiquetas": [e1["id"]]}).status_code == 200
        assert s.patch(f"/api/lais/contatos/{b['id']}", {"etiquetas": [e1["id"], e2["id"]]}).status_code == 200
        cols = s.get("/api/lais/conversas?view=kanban").json()["data"]["colunas"]
        assert [c["tipo"] for c in cols] == ["todas", "etiqueta", "etiqueta", "arquivadas"]
        por = {c["id"]: {i["id"] for i in c.get("itens", [])} for c in cols}
        assert por["todas"] == {s.cid, b["id"]}
        assert por[e1["id"]] == {s.cid, b["id"]} and por[e2["id"]] == {b["id"]}
        assert cols[-1]["total"] == 1 and "itens" not in cols[-1]
        assert arq["id"] not in por["todas"]

    def test_the_column_picker_limits_the_tag_columns(self, admin):
        e1 = admin.post("/api/lais/etiquetas", {"nome": "A"}).json()["data"]
        admin.post("/api/lais/etiquetas", {"nome": "B"})
        cols = admin.get(f"/api/lais/conversas?view=kanban&etiqueta={e1['id']}").json()["data"]["colunas"]
        assert [c["id"] for c in cols] == ["todas", e1["id"], "arquivadas"]

    def test_a_member_kanban_only_has_their_contatos(self, member):
        member.dono(TEST_USER_ID)
        member.outro_contato("5511900000007@c.us", responsavel_user_id=OUTRO)
        cols = member.get("/api/lais/conversas?view=kanban").json()["data"]["colunas"]
        assert [i["id"] for i in cols[0]["itens"]] == [member.cid]

    def test_filter_by_etiqueta_in_the_list(self, admin):
        e1 = admin.post("/api/lais/etiquetas", {"nome": "VIP"}).json()["data"]
        admin.outro_contato("5511900000008@c.us")
        admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [e1["id"]]})
        itens = admin.get(f"/api/lais/conversas?etiqueta={e1['id']}").json()["data"]
        assert [i["id"] for i in itens] == [admin.cid] and itens[0]["etiquetas"][0]["nome"] == "VIP"
        e2 = admin.post("/api/lais/etiquetas", {"nome": "Outra"}).json()["data"]
        assert len(admin.get(f"/api/lais/conversas?etiqueta={e1['id']},{e2['id']}").json()["data"]) == 1


# ── PATCH contato ───────────────────────────────────────────────────────────
class TestPatchContato:
    def test_assign_responsavel_then_clear(self, admin):
        r = admin.patch(f"/api/lais/contatos/{admin.cid}", {"responsavel_user_id": MEMBER_ID})
        assert r.status_code == 200 and r.json()["data"]["responsavel_user_id"] == MEMBER_ID
        r = admin.patch(f"/api/lais/contatos/{admin.cid}", {"responsavel_user_id": None})
        assert r.status_code == 200 and r.json()["data"]["responsavel_user_id"] is None

    def test_a_responsavel_outside_the_org_is_422(self, admin):
        r = admin.patch(f"/api/lais/contatos/{admin.cid}", {"responsavel_user_id": str(uuid4())})
        assert r.status_code == 422 and r.json()["error"]["code"] == "responsavel_invalido"

    def test_etiquetas_replace_and_unknown_is_422(self, admin):
        e1 = admin.post("/api/lais/etiquetas", {"nome": "A"}).json()["data"]
        e2 = admin.post("/api/lais/etiquetas", {"nome": "B"}).json()["data"]
        admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [e1["id"]]})
        r = admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [e2["id"]]})
        assert [t["id"] for t in r.json()["data"]["etiquetas"]] == [e2["id"]]
        assert admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": []}).json()["data"]["etiquetas"] == []
        r = admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [str(uuid4())]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "etiqueta_invalida"

    def test_another_orgs_etiqueta_is_422(self, admin):
        admin.w.sw.table("lais_etiquetas").insert({"id": str(uuid4()), "org_id": OTHER_ORG_ID, "nome": "x", "cor": "#000000"}).execute()
        alheia = admin.w.rows("lais_etiquetas")[0]["id"]
        assert admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [alheia]}).status_code == 422

    def test_archive_and_block_bump_gen_which_cancels_queued_jobs(self, admin):
        g0 = admin.w.contato()["gen"]
        assert admin.patch(f"/api/lais/contatos/{admin.cid}", {"arquivado": True}).json()["data"]["arquivado"] is True
        g1 = admin.w.contato()["gen"]
        assert admin.patch(f"/api/lais/contatos/{admin.cid}", {"bloqueado": True}).json()["data"]["bloqueado"] is True
        assert g0 < g1 < admin.w.contato()["gen"]

    @pytest.mark.parametrize("corpo", [{"extra": 1}, {"arquivado": "talvez"}, {"responsavel_user_id": "nao-uuid"}])
    def test_bad_bodies_are_422(self, admin, corpo):
        assert admin.patch(f"/api/lais/contatos/{admin.cid}", corpo).status_code == 422


# ── notas / feedback / etiquetas ────────────────────────────────────────────
class TestNotas:
    def test_crud_with_soft_delete(self, admin):
        r = admin.post(f"/api/lais/contatos/{admin.cid}/notas", {"texto": "  retornar sexta  "})
        assert r.status_code == 201
        nota = r.json()["data"]
        assert nota["texto"] == "retornar sexta" and nota["autor_user_id"] == TEST_USER_ID
        assert [n["id"] for n in admin.get(f"/api/lais/contatos/{admin.cid}/notas").json()["data"]] == [nota["id"]]
        assert admin.delete(f"/api/lais/contatos/{admin.cid}/notas/{nota['id']}").status_code == 204
        assert admin.get(f"/api/lais/contatos/{admin.cid}/notas").json()["data"] == []
        (linha,) = admin.w.rows("lais_notas")
        assert linha["deleted_at"]  # soft: the row is still there
        assert admin.delete(f"/api/lais/contatos/{admin.cid}/notas/{nota['id']}").status_code == 404

    @pytest.mark.parametrize("texto", ["", "   ", "x" * 4001])
    def test_text_bounds_are_422(self, admin, texto):
        assert admin.post(f"/api/lais/contatos/{admin.cid}/notas", {"texto": texto}).status_code == 422

    def test_only_the_author_or_an_admin_may_delete(self, member):
        member.dono(TEST_USER_ID)
        member.w.sw.table("lais_notas").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "contato_id": member.cid, "autor_user_id": OUTRO, "texto": "x", "deleted_at": None}).execute()
        nid = member.w.rows("lais_notas")[0]["id"]
        r = member.delete(f"/api/lais/contatos/{member.cid}/notas/{nid}")
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"
        mine = member.post(f"/api/lais/contatos/{member.cid}/notas", {"texto": "minha"}).json()["data"]
        assert member.delete(f"/api/lais/contatos/{member.cid}/notas/{mine['id']}").status_code == 204

    def test_a_note_of_another_contato_is_404(self, admin):
        outro = admin.outro_contato("5511900000009@c.us")
        n = admin.post(f"/api/lais/contatos/{outro['id']}/notas", {"texto": "x"}).json()["data"]
        assert admin.delete(f"/api/lais/contatos/{admin.cid}/notas/{n['id']}").status_code == 404


class TestFeedback:
    def test_stored_against_the_open_interacao_by_default(self, admin):
        it = contatos.abrir_interacao(admin.w.sw, ORG_ID, admin.w.contato())
        r = admin.post(f"/api/lais/contatos/{admin.cid}/feedback", {"nota": "dislike", "comentario": "demorou"})
        assert r.status_code == 201
        (f,) = admin.w.rows("lais_feedback")
        assert f["nota"] == "dislike" and f["comentario"] == "demorou" and f["interacao_id"] == it["id"] and f["user_id"] == TEST_USER_ID

    def test_invalid_nota_extra_field_and_foreign_interacao_are_422(self, admin):
        u = f"/api/lais/contatos/{admin.cid}/feedback"
        assert admin.post(u, {"nota": "meh"}).status_code == 422
        assert admin.post(u, {"nota": "like", "x": 1}).status_code == 422
        assert admin.post(u, {"nota": "like", "interacao_id": str(uuid4())}).status_code == 422
        assert admin.post(u, {"nota": "like", "comentario": "c" * 1001}).status_code == 422


class TestEtiquetas:
    def test_crud_and_duplicates(self, admin):
        e = admin.post("/api/lais/etiquetas", {"nome": " Quente "}).json()["data"]
        assert e["nome"] == "Quente" and e["cor"] == "#6366f1"
        assert admin.post("/api/lais/etiquetas", {"nome": "quente"}).status_code == 409
        r = admin.patch(f"/api/lais/etiquetas/{e['id']}", {"cor": "#00ff00"})
        assert r.status_code == 200 and r.json()["data"]["cor"] == "#00ff00"
        outra = admin.post("/api/lais/etiquetas", {"nome": "Morno"}).json()["data"]
        assert admin.patch(f"/api/lais/etiquetas/{outra['id']}", {"nome": "QUENTE"}).status_code == 409
        assert [x["nome"] for x in admin.get("/api/lais/etiquetas").json()["data"]] == ["Morno", "Quente"]

    def test_delete_detaches_it_from_contatos(self, admin):
        e = admin.post("/api/lais/etiquetas", {"nome": "X"}).json()["data"]
        admin.patch(f"/api/lais/contatos/{admin.cid}", {"etiquetas": [e["id"]]})
        assert admin.delete(f"/api/lais/etiquetas/{e['id']}").status_code == 204
        assert admin.w.rows("lais_contato_etiquetas") == [] and admin.w.rows("lais_etiquetas") == []
        assert admin.delete(f"/api/lais/etiquetas/{e['id']}").status_code == 404

    @pytest.mark.parametrize("corpo", [{"nome": ""}, {"nome": "a" * 41}, {"nome": "ok", "cor": "vermelho"}, {"nome": "ok", "x": 1}])
    def test_validation_is_422(self, admin, corpo):
        assert admin.post("/api/lais/etiquetas", corpo).status_code == 422

    def test_members_create_and_list_but_cannot_edit_or_delete(self, member):
        e = member.post("/api/lais/etiquetas", {"nome": "Minha"}).json()["data"]
        assert member.get("/api/lais/etiquetas").status_code == 200
        assert member.patch(f"/api/lais/etiquetas/{e['id']}", {"nome": "Outra"}).status_code == 403
        assert member.delete(f"/api/lais/etiquetas/{e['id']}").status_code == 403

    def test_tags_are_per_org(self, admin):
        admin.w.sw.table("lais_etiquetas").insert({"id": str(uuid4()), "org_id": OTHER_ORG_ID, "nome": "Alheia", "cor": "#000000"}).execute()
        assert admin.get("/api/lais/etiquetas").json()["data"] == []
        assert admin.post("/api/lais/etiquetas", {"nome": "Alheia"}).status_code == 201


# ── inbound policy: arquivar / bloquear ─────────────────────────────────────
class TestPoliticaInbound:
    def _store(self, w):
        from app.services.whatsapp_chat_store import WhatsAppChatStore

        return WhatsAppChatStore(admin_supabase=w.admin, org_id=ORG_ID)

    def test_a_blocked_number_is_dropped(self):
        w, c = _mundo()
        contatos.atualizar_contato(w.sw, c["id"], {"bloqueado": True})
        assert svc.aplicar_politica_inbound(w.sw, self._store(w), org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) == "bloqueado"

    def test_the_worker_gives_a_blocked_number_no_turn_and_no_reply(self):
        w, c = _mundo()
        w.seed_chat()
        contatos.atualizar_contato(w.sw, c["id"], {"bloqueado": True})
        key = buffer_lead(w, LEAD_CHAT, ["oi, quero um apartamento"])
        asyncio.run(process_lead_batch(key, w.buffer.memory_for(key), deps=w.deps()))
        assert w.agents.turns == [] and w.waha.sent_messages == []

    def test_the_worker_answers_the_same_number_once_unblocked(self):
        w, c = _mundo()
        w.seed_chat()
        key = buffer_lead(w, LEAD_CHAT, ["oi, quero um apartamento"])
        asyncio.run(process_lead_batch(key, w.buffer.memory_for(key), deps=w.deps()))
        assert len(w.agents.turns) == 1

    def test_the_worker_hands_an_archived_paused_chat_back_to_julia(self):
        w, c = _mundo()
        w.seed_chat(agente_pausado=True)
        contatos.atualizar_contato(w.sw, c["id"], {"arquivado": True})
        key = buffer_lead(w, LEAD_CHAT, ["oi"])
        asyncio.run(process_lead_batch(key, w.buffer.memory_for(key), deps=w.deps()))
        assert len(w.agents.turns) == 1 and w.contato()["arquivado"] is False and w.chat_row()["agente_pausado"] is False

    def test_an_archived_contato_goes_back_to_julia_on_the_next_inbound(self):
        w, c = _mundo()
        w.seed_chat(agente_pausado=True)
        contatos.atualizar_contato(w.sw, c["id"], {"arquivado": True})
        assert svc.aplicar_politica_inbound(w.sw, self._store(w), org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) == "devolvido"
        assert w.contato()["arquivado"] is False and w.chat_row()["agente_pausado"] is False
        # and it is a one-shot: the next inbound is a plain `ok`
        assert svc.aplicar_politica_inbound(w.sw, self._store(w), org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) == "ok"

    def test_unknown_chat_and_plain_contato_are_ok(self):
        w, _ = _mundo()
        assert svc.aplicar_politica_inbound(w.sw, self._store(w), org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id="nada@c.us") == "ok"
        assert svc.aplicar_politica_inbound(w.sw, self._store(w), org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) == "ok"


# ── attendant-name prefix ───────────────────────────────────────────────────
class TestPrefixoDoAtendente:
    URL = f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/send"

    def _ligar(self, s, ativo):
        s.w.sw.table("lais_conhecimento_secoes").insert({
            "org_id": ORG_ID, "secao": "exibir_atendente", "dados": {"ativo": ativo}, "versao": 1}).execute()

    def test_on_the_human_text_is_prefixed_everywhere_it_lands(self, admin):
        self._ligar(admin, True)
        r = admin.post(self.URL, {"text": "Olá, aqui é do atendimento"})
        assert r.status_code == 201
        esperado = "*Carla Souza*:\nOlá, aqui é do atendimento"
        assert admin.w.sent_texts() == [esperado] and r.json()["body"] == esperado
        assert [m["body"] for m in admin.w.messages() if m["direction"] == "outbound"] == [esperado]

    def test_off_the_text_goes_untouched(self, admin):
        self._ligar(admin, False)
        assert admin.post(self.URL, {"text": "oi"}).status_code == 201
        assert admin.w.sent_texts() == ["oi"]

    def test_never_configured_defaults_to_off(self, admin):
        assert admin.post(self.URL, {"text": "oi"}).status_code == 201
        assert admin.w.sent_texts() == ["oi"]

    def test_a_non_julia_line_is_never_prefixed(self, admin):
        self._ligar(admin, True)
        admin.w.sw.table("whatsapp_connections").update({"agente_leads_ativo": False, "authorized_numbers": []}).eq("id", CONNECTION_ID).execute()
        assert admin.post(self.URL, {"text": "oi"}).status_code == 201
        assert admin.w.sent_texts() == ["oi"]

    def test_name_falls_back_to_the_email_local_part(self):
        from types import SimpleNamespace

        assert svc.nome_do_atendente(SimpleNamespace(email="joana@x.com", user_metadata={})) == "joana"
        assert svc.nome_do_atendente(SimpleNamespace(email=None, user_metadata={})) is None


# ── maya-blocks: a human's inbox reply can be the episode's first response ──
class TestPrimeiraRespostaHumana:
    URL = f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/send"

    def test_the_first_human_reply_stamps_the_open_episode_once(self, admin):
        contatos.abrir_interacao(admin.w.sw, ORG_ID, admin.contato)
        assert admin.post(self.URL, {"text": "oi, sou a Carla"}).status_code == 201
        (ep,) = admin.w.rows("lais_interacoes", contato_id=admin.cid)
        primeira = ep["primeira_resposta_at"]
        assert primeira
        assert admin.post(self.URL, {"text": "tudo bem?"}).status_code == 201
        assert admin.w.rows("lais_interacoes", contato_id=admin.cid)[0]["primeira_resposta_at"] == primeira

    def test_no_open_episode_or_a_non_julia_line_stamps_nothing_and_still_sends(self, admin):
        assert admin.post(self.URL, {"text": "oi"}).status_code == 201
        assert admin.w.rows("lais_interacoes", contato_id=admin.cid) == []
        contatos.abrir_interacao(admin.w.sw, ORG_ID, admin.contato)
        admin.w.sw.table("whatsapp_connections").update({"agente_leads_ativo": False, "authorized_numbers": []}).eq("id", CONNECTION_ID).execute()
        assert admin.post(self.URL, {"text": "oi"}).status_code == 201
        assert admin.w.rows("lais_interacoes", contato_id=admin.cid)[0].get("primeira_resposta_at") is None

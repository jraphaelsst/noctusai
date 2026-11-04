"""Julia v3 report destination + the lead card's report feed (CONTRACT julia-v2 section 12.5, migration 313).

`GET|PUT /api/julia/relatorio-destino` is an org-admin action; `GET /api/julia/contatos/{id}/relatorios` follows the per-lead access
rule A7. Every route is strict `== 401` without a session. Seams: the mock DB through the route's own `Depends` override."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from tests.support.julia_world import CONNECTION_ID, ENCRYPTION_KEY, LEAD_CHAT, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, OWNER_TELEFONE, World

H = {"Authorization": "Bearer test-token"}
DESTINO = "/api/julia/relatorio-destino"


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, url, json=None):
        return getattr(self.tc, m)(url, headers=H, **({"json": json} if json is not None else {}))

    def contato(self, **over):
        row = {"id": str(uuid4()), "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "gen": 0, "slots": {},
               "canal": "whatsapp", "status_envio": "nao_pronto", "arquivado": False, "bloqueado": False, "responsavel_user_id": None,
               "nome": "Ana", **over}
        self.w.sw.table("julia_contatos").insert(row).execute()
        return row

    def relatorio(self, contato_id, *, tipo="handoff", criado, org=ORG_ID, texto="texto"):
        self.w.sw.table("julia_relatorios").insert({
            "id": str(uuid4()), "org_id": org, "contato_id": contato_id, "tipo": tipo, "texto": texto, "dados": {"k": 1},
            "destino_e164": "+5511900001111", "envio_status": "enviado", "created_at": criado}).execute()


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: _settings.model_copy(update={"encryption_key": ENCRYPTION_KEY})
    yield
    app.dependency_overrides.pop(get_settings, None)


def _scene(role):
    w = World()
    w.seed_connection(user_id=OWNER_ID)
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Dono", "telefone": OWNER_TELEFONE},
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.julia_relatorio_destino_router import get_relatorio_destino_client, get_servicos_internos

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_relatorio_destino_client] = lambda: w.sw
        app.dependency_overrides[get_servicos_internos] = lambda: w.deps()
        yield Scene(TestClient(app), w)
        app.dependency_overrides.pop(get_relatorio_destino_client, None)
        app.dependency_overrides.pop(get_servicos_internos, None)


@pytest.fixture
def admin(override_settings_factory):
    yield from _scene("owner")


@pytest.fixture
def member(override_settings_factory):
    yield from _scene("member")


class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", DESTINO), ("put", DESTINO), ("get", f"/api/julia/contatos/{uuid4()}/relatorios")])
    def test_no_session_is_strictly_401(self, admin, method, url):
        assert getattr(admin.tc, method)(url).status_code == 401

    @pytest.mark.parametrize("method,body", [("get", None), ("put", {"modo": "usuario", "usuario_id": OWNER_ID})])
    def test_a_member_is_403(self, member, method, body):
        assert member.req(method, DESTINO, body).status_code == 403

    def test_a_member_who_does_not_own_the_lead_is_403_on_its_reports(self, member):
        c = member.contato()
        r = member.req("get", f"/api/julia/contatos/{c['id']}/relatorios")
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"

    def test_another_orgs_contato_is_404_never_403(self, admin):
        c = admin.contato(org_id=OTHER_ORG_ID)
        r = admin.req("get", f"/api/julia/contatos/{c['id']}/relatorios")
        assert r.status_code == 404 and r.json()["error"]["code"] == "contato_nao_encontrado"


class TestDestino:
    def test_default_then_put_then_get_roundtrip(self, admin):
        assert admin.req("get", DESTINO).json()["data"] == {
            "modo": "usuario", "usuario_id": None, "usuario_nome": None, "telefone_resolvido": None, "atualizado_em": None}
        r = admin.req("put", DESTINO, {"modo": "usuario", "usuario_id": OWNER_ID})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["modo"] == "usuario" and d["usuario_id"] == OWNER_ID and d["usuario_nome"] == "Dono" and d["telefone_resolvido"] == OWNER_TELEFONE
        assert admin.req("get", DESTINO).json()["data"]["telefone_resolvido"] == OWNER_TELEFONE
        (row,) = admin.w.rows("julia_relatorio_destino")
        assert row["org_id"] == ORG_ID and row["updated_by"] == TEST_USER_ID and "numero_e164" not in row

    def test_a_user_without_a_phone_resolves_to_null(self, admin):
        admin.req("put", DESTINO, {"modo": "usuario", "usuario_id": TEST_USER_ID})
        assert admin.req("get", DESTINO).json()["data"]["telefone_resolvido"] is None

    def test_modo_responsavel_may_carry_a_fallback_user_or_none(self, admin):
        assert admin.req("put", DESTINO, {"modo": "responsavel"}).json()["data"]["modo"] == "responsavel"
        r = admin.req("put", DESTINO, {"modo": "responsavel", "usuario_id": OWNER_ID})
        assert r.json()["data"]["usuario_id"] == OWNER_ID
        assert len(admin.w.rows("julia_relatorio_destino")) == 1  # a full replace of the org's one row

    @pytest.mark.parametrize("body,codigo", [
        ({"modo": "usuario"}, "usuario_obrigatorio"),
        ({"modo": "usuario", "usuario_id": "00000000-0000-4000-8000-00000000dead"}, "usuario_fora_da_org"),
    ])
    def test_typed_errors(self, admin, body, codigo):
        r = admin.req("put", DESTINO, body)
        assert r.status_code == 422 and r.json()["error"]["code"] == codigo

    def test_unknown_modes_numbers_and_keys_are_rejected(self, admin):
        assert admin.req("put", DESTINO, {"modo": "numero"}).status_code == 422
        assert admin.req("put", DESTINO, {"modo": "usuario", "usuario_id": OWNER_ID, "numero_e164": "+5511900001111"}).status_code == 422
        assert admin.req("put", DESTINO, {"modo": "usuario", "usuario_id": OWNER_ID, "org_id": "x"}).status_code == 422

    def test_there_is_no_confirmation_route_any_more(self, admin):
        assert admin.req("post", f"{DESTINO}/confirmar", {"codigo": "123456"}).status_code in (404, 405)


class TestRelatorios:
    def test_newest_first_with_the_card_fields_and_only_this_contato(self, admin):
        c = admin.contato()
        outro = admin.contato(chat_id="5511977776666@c.us")
        admin.relatorio(c["id"], criado="2026-11-03T10:00:00+00:00", texto="antigo")
        admin.relatorio(c["id"], tipo="alerta", criado="2026-11-03T12:00:00+00:00", texto="novo")
        admin.relatorio(outro["id"], criado="2026-11-03T13:00:00+00:00", texto="de outro lead")
        data = admin.req("get", f"/api/julia/contatos/{c['id']}/relatorios").json()["data"]
        assert [r["texto"] for r in data] == ["novo", "antigo"]
        assert set(data[0]) == {"id", "contato_id", "lead_id", "thread_id", "tipo", "texto", "dados", "destino_e164",
                                "envio_status", "envio_erro", "created_at"}
        assert data[0]["tipo"] == "alerta" and data[0]["envio_status"] == "enviado"

"""Julia > Equipe (staff of the org's WhatsApp lines) and Julia > Proteção (limits + blocklist) routes (migration 298; owner 2026-10-21).
Every route is strict `== 401` without a session and an org-admin action (403 for a member). Seams: the mock DB through the routes' own
`Depends` overrides; nothing of ours is patched."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from tests.support.julia_world import (
    ADMIN_ID, CONNECTION_ID, CORRETOR_ID, ENCRYPTION_KEY, MEMBER_ID, ORG_ID, OWNER_ID, World,
)

H = {"Authorization": "Bearer test-token"}
EQUIPE = "/api/julia/equipe-whatsapp"
PROT = "/api/julia/protecao"
TABLES = ("julia_staff", "julia_protecao_config", "julia_numeros_bloqueados")


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, url, json=None, **kw):
        return getattr(self.tc, m)(url, headers=H, **({"json": json} if json is not None else {}), **kw)


def _scene(role):
    w = World()
    w.seed_connection(user_id=OWNER_ID)
    for t in TABLES:
        w.sw.set_table_data(t, [])
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
        from app.routers.julia_equipe_whatsapp_router import get_equipe_client, get_equipe_core
        from app.routers.julia_protecao_router import get_protecao_client, get_protecao_core

        bind_consent_module_to_mock(w.root)
        overrides = {get_equipe_client: lambda: w.sw, get_equipe_core: lambda: w.root,
                     get_protecao_client: lambda: w.sw, get_protecao_core: lambda: w.root}
        app.dependency_overrides.update(overrides)
        yield Scene(TestClient(app), w)
        for k in overrides:
            app.dependency_overrides.pop(k, None)


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


class TestAuth:
    @pytest.mark.parametrize("method,url", [
        ("get", EQUIPE), ("get", f"{EQUIPE}/usuarios"), ("post", EQUIPE), ("patch", f"{EQUIPE}/00000000-0000-4000-8000-000000000001"),
        ("delete", f"{EQUIPE}/00000000-0000-4000-8000-000000000001"), ("get", f"{PROT}/config"), ("put", f"{PROT}/config"),
        ("get", f"{PROT}/bloqueios"), ("post", f"{PROT}/bloqueios"),
        ("post", f"{PROT}/bloqueios/00000000-0000-4000-8000-000000000001/desbloquear"),
    ])
    def test_no_session_is_strictly_401(self, admin, method, url):
        assert getattr(admin.tc, method)(url).status_code == 401

    @pytest.mark.parametrize("method,url,body", [
        ("get", EQUIPE, None), ("post", EQUIPE, {"nome": "X", "papel": "outro", "telefone": "5511977770009"}),
        ("get", f"{PROT}/config", None), ("put", f"{PROT}/config", {"entrada_limite": 5}),
        ("post", f"{PROT}/bloqueios", {"numero": "5511977770001", "motivo": "x"}),
    ])
    def test_a_member_is_403_everywhere(self, member, method, url, body):
        assert member.req(method, url, body).status_code == 403


class TestEquipe:
    def test_create_list_update_delete_roundtrip_and_the_mirror(self, admin):
        r = admin.req("post", EQUIPE, {"nome": "Bia", "papel": "operador", "telefone": "+55 11 97777-0009"})
        assert r.status_code == 201 and r.json()["data"]["telefone"] == "5511977770009"
        sid = r.json()["data"]["id"]
        listado = admin.req("get", EQUIPE).json()["data"]
        assert [i["nome"] for i in listado["items"]] == ["Bia"] and "corretor" in listado["papeis"]
        assert "+5511977770009" in admin.w.rows("whatsapp_connections")[0]["authorized_numbers"]
        admin.req("post", EQUIPE, {"nome": "Op2", "papel": "admin", "telefone": "5511977770008"})
        r = admin.req("patch", f"{EQUIPE}/{sid}", {"papel": "corretor"})
        assert r.status_code == 200 and r.json()["data"]["papel"] == "corretor"
        assert "+5511977770009" not in admin.w.rows("whatsapp_connections")[0]["authorized_numbers"]
        assert admin.req("delete", f"{EQUIPE}/{sid}").status_code == 204

    def test_typed_errors(self, admin):
        r = admin.req("post", EQUIPE, {"nome": "X", "papel": "rei", "telefone": "5511977770009"})
        assert r.status_code == 422
        r = admin.req("post", EQUIPE, {"nome": "X", "papel": "outro"})
        assert r.status_code == 422
        admin.req("post", EQUIPE, {"nome": "Op", "papel": "operador", "telefone": "5511977770009"})
        r = admin.req("post", EQUIPE, {"nome": "Dup", "papel": "outro", "telefone": "5511977770009"})
        assert r.status_code == 409
        sid = admin.req("get", EQUIPE).json()["data"]["items"][0]["id"]
        assert admin.req("delete", f"{EQUIPE}/{sid}").status_code == 409  # the last operator of a Julia-on line
        assert admin.req("patch", f"{EQUIPE}/00000000-0000-4000-8000-000000000001", {"nome": "Y"}).status_code == 404

    def test_unknown_body_keys_are_rejected(self, admin):
        r = admin.req("post", EQUIPE, {"nome": "X", "papel": "outro", "telefone": "5511977770009", "org_id": "x"})
        assert r.status_code == 422

    def test_the_users_list_is_the_orgs_only(self, admin):
        admin.w.core.table("noctus_users").insert({"id": "00000000-0000-4000-8000-00000000f001", "org_id": "other", "org_role": "member",
                                                    "nome": "Outro"}).execute()
        nomes = {u["nome"] for u in admin.req("get", f"{EQUIPE}/usuarios").json()["data"]}
        assert "Outro" not in nomes and {"Adriana", "Carla"} <= nomes


class TestProtecao:
    def test_the_config_shows_every_limit_with_its_default_and_range_then_saves(self, admin):
        d = admin.req("get", f"{PROT}/config").json()["data"]
        assert d["padrao"] is True and d["entrada_limite"] == 20 and d["faixas"]["entrada_limite"] == [1, 500]
        assert d["padroes"]["midia_limite_chat_dia"] == 10 and d["prompt_documento_padrao"]
        r = admin.req("put", f"{PROT}/config", {"entrada_limite": 7, "bloqueio_auto_ativo": False})
        assert r.status_code == 200 and r.json()["data"]["entrada_limite"] == 7 and r.json()["data"]["bloqueio_auto_ativo"] is False
        assert admin.req("put", f"{PROT}/config", {"entrada_limite": 100000}).status_code == 422
        assert admin.req("put", f"{PROT}/config", {"inventado": 1}).status_code == 422

    def test_block_list_unblock_and_history(self, admin):
        r = admin.req("post", f"{PROT}/bloqueios", {"numero": "+55 11 97777-0001", "motivo": "spam de links", "duracao_min": 60})
        assert r.status_code == 201 and r.json()["data"]["expira_em"] and r.json()["data"]["criado_por"] == str(TEST_USER_ID)
        bid = r.json()["data"]["id"]
        assert len(admin.req("get", f"{PROT}/bloqueios").json()["data"]["items"]) == 1
        assert admin.req("post", f"{PROT}/bloqueios", {"numero": "5511977770001", "motivo": "x"}).status_code == 409
        assert admin.req("post", f"{PROT}/bloqueios/{bid}/desbloquear").status_code == 200
        assert admin.req("get", f"{PROT}/bloqueios").json()["data"]["items"] == []
        assert len(admin.req("get", f"{PROT}/bloqueios?historico=true").json()["data"]["items"]) == 1
        assert admin.req("post", f"{PROT}/bloqueios/{bid}/desbloquear").status_code == 409

    def test_a_staff_number_cannot_be_blocked_and_a_reason_is_required(self, admin):
        admin.req("post", EQUIPE, {"nome": "Bia", "papel": "corretor", "telefone": "5511977770009"})
        assert admin.req("post", f"{PROT}/bloqueios", {"numero": "5511977770009", "motivo": "x"}).status_code == 409
        assert admin.req("post", f"{PROT}/bloqueios", {"numero": "5511977770001", "motivo": ""}).status_code == 422
        assert admin.req("post", f"{PROT}/bloqueios", {"numero": "abc", "motivo": "x"}).status_code == 422

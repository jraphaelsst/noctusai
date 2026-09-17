"""Tests for the grupos + sessão router — contract §Grupos, items 1-7.

WAHA-touching endpoints inject a shared `FakeWahaClient` via FastAPI's
`app.dependency_overrides[get_community_waha_client]` — the canonical
override seam (not a monkeypatch of this product's own code).
"""
import asyncio

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient

from app.dependencies import get_community_waha_client
from tests.conftest import ORG_UUID, seed_community_role

GRUPO_1 = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"


def _grupo_row(**over) -> dict:
    base = {
        "id": GRUPO_1, "org_id": ORG_UUID, "nome": "Grupo Oficial", "chat_id": CHAT_ID,
        "descricao": None, "ativo": True, "somente_admin": False,
        "participantes_observados": 0, "sincronizado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _override_waha(client, waha: FakeWahaClient) -> None:
    client.raw().app.dependency_overrides[get_community_waha_client] = lambda: waha


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/whatsapp/grupos").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/whatsapp/grupos", json={}).status_code == 401

    def test_get_without_auth_401(self, client):
        assert client.raw().get(f"/api/whatsapp/grupos/{GRUPO_1}").status_code == 401

    def test_sincronizar_roster_without_auth_401(self, client):
        assert client.raw().post(f"/api/whatsapp/grupos/{GRUPO_1}/sincronizar-roster").status_code == 401

    def test_convite_without_auth_401(self, client):
        assert client.raw().get(f"/api/whatsapp/grupos/{GRUPO_1}/convite").status_code == 401

    def test_sessao_without_auth_401(self, client):
        assert client.raw().get("/api/whatsapp/sessao").status_code == 401


class TestRoleGate:
    def test_moderador_can_list(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/whatsapp/grupos").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/whatsapp/grupos", json={"chat_id": CHAT_ID, "nome": "X"})
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")

    def test_moderador_sincronizar_roster_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/whatsapp/grupos/{GRUPO_1}/sincronizar-roster")
        assert resp.status_code == 403

    def test_moderador_convite_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.get(f"/api/whatsapp/grupos/{GRUPO_1}/convite")
        assert resp.status_code == 403

    def test_moderador_revogar_convite_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/whatsapp/grupos/{GRUPO_1}/convite/revogar")
        assert resp.status_code == 403


class TestGruposCrud:
    def test_create_register_existing_201(self, client):
        seed_community_role(client, org_role="admin")
        _override_waha(client, FakeWahaClient())
        resp = client.post("/api/whatsapp/grupos", json={
            "chat_id": CHAT_ID, "nome": "Grupo Oficial", "criar": False,
        })
        assert resp.status_code == 201
        assert resp.json()["chat_id"] == CHAT_ID

    def test_create_duplicate_chat_id_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        _override_waha(client, FakeWahaClient())
        resp = client.post("/api/whatsapp/grupos", json={
            "chat_id": CHAT_ID, "nome": "Outro", "criar": False,
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Esse grupo já está cadastrado."

    def test_list_200(self, client):
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        resp = client.get("/api/whatsapp/grupos")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_404(self, client):
        resp = client.get(f"/api/whatsapp/grupos/{UNKNOWN_ID}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Grupo não encontrado."

    def test_get_200_includes_roster(self, client):
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data("grupo_membros", [])
        resp = client.get(f"/api/whatsapp/grupos/{GRUPO_1}")
        assert resp.status_code == 200
        assert resp.json()["membros"] == []

    def test_get_200_moderador_masks_roster_phone(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        membro_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        client.mock_supabase.set_table_data("grupo_membros", [{
            "id": "gm1", "org_id": ORG_UUID, "grupo_id": GRUPO_1,
            "participante_jid": "5511974693365@c.us", "membro_id": membro_id,
            "papel": "participante", "visto_em": "2026-01-01T00:00:00+00:00",
        }])
        client.mock_supabase.set_table_data("membros", [
            {"id": membro_id, "org_id": ORG_UUID, "nome": "Ana", "telefone": "+5511974693365"},
        ])
        resp = client.get(f"/api/whatsapp/grupos/{GRUPO_1}")
        assert resp.status_code == 200
        roster = resp.json()["membros"]
        assert roster[0]["telefone_mascarado"] == "***3365"
        assert "telefone" not in roster[0]
        assert "participante_jid" not in roster[0]

    def test_update_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        resp = client.patch(f"/api/whatsapp/grupos/{GRUPO_1}", json={"nome": "Novo Nome"})
        assert resp.status_code == 200
        assert resp.json()["nome"] == "Novo Nome"


class TestSessao:
    def test_get_sessao_200(self, client):
        waha = FakeWahaClient()
        _override_waha(client, waha)
        resp = client.get("/api/whatsapp/sessao")
        assert resp.status_code == 200
        assert resp.json()["estado"] == "SCAN_QR_CODE"


class TestConvite:
    def test_get_convite_200_admin(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        _override_waha(client, waha)
        resp = client.get(f"/api/whatsapp/grupos/{GRUPO_1}/convite")
        assert resp.status_code == 200
        assert resp.json()["link"].startswith("https://chat.whatsapp.com/")

    def test_revogar_convite_200_admin(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        _override_waha(client, waha)
        resp = client.post(f"/api/whatsapp/grupos/{GRUPO_1}/convite/revogar")
        assert resp.status_code == 200

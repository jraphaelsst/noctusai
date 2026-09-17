"""Tests for the transmissões router — contract §Transmissões, items 14-18.

`enviar`'s full send/dedupe/partial-failure behavior is pinned at the
service layer (`tests/services/test_transmissoes_service.py`); this
file covers the HTTP wiring: auth, role gate, and status codes.
"""
import asyncio

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient

from app.dependencies import get_community_waha_client
from tests.conftest import ORG_UUID, seed_community_role

GRUPO_1 = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
TRANSMISSAO_1 = "22222222-2222-2222-2222-222222222222"


def _grupo_row(**over) -> dict:
    base = {"id": GRUPO_1, "org_id": ORG_UUID, "chat_id": CHAT_ID, "nome": "G", "ativo": True}
    base.update(over)
    return base


def _transmissao_row(**over) -> dict:
    base = {
        "id": TRANSMISSAO_1, "org_id": ORG_UUID, "titulo": "Aviso", "corpo": "Olá",
        "tipo": "anuncio", "estado": "rascunho", "agendada_para": None, "enviada_em": None,
        "criada_por": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _override_waha(client, waha: FakeWahaClient) -> None:
    client.raw().app.dependency_overrides[get_community_waha_client] = lambda: waha


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/whatsapp/transmissoes").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/whatsapp/transmissoes", json={}).status_code == 401

    def test_enviar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}/enviar")
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        assert client.raw().delete(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}").status_code == 401


class TestRoleGate:
    def test_moderador_can_list(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/whatsapp/transmissoes").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/whatsapp/transmissoes", json={
            "titulo": "X", "corpo": "Y", "tipo": "anuncio", "grupo_ids": [GRUPO_1],
        })
        assert resp.status_code == 403

    def test_moderador_enviar_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}/enviar")
        assert resp.status_code == 403

    def test_moderador_delete_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.delete(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}")
        assert resp.status_code == 403


class TestCrud:
    def test_create_201(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        resp = client.post("/api/whatsapp/transmissoes", json={
            "titulo": "Aviso", "corpo": "Olá pessoal", "tipo": "anuncio",
            "grupo_ids": [GRUPO_1],
        })
        assert resp.status_code == 201
        assert resp.json()["estado"] == "rascunho"

    def test_create_unknown_grupo_422(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [])
        resp = client.post("/api/whatsapp/transmissoes", json={
            "titulo": "Aviso", "corpo": "Olá", "tipo": "anuncio",
            "grupo_ids": [GRUPO_1],
        })
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Grupo inválido na lista de destinos."

    def test_list_200(self, client):
        client.mock_supabase.set_table_data("transmissoes", [_transmissao_row()])
        client.mock_supabase.set_table_data("transmissao_destinos", [])
        resp = client.get("/api/whatsapp/transmissoes")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch(
            f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}", json={"titulo": "Novo"},
        )
        assert resp.status_code == 404

    def test_update_enviada_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("transmissoes", [_transmissao_row(estado="enviada")])
        client.mock_supabase.set_table_data("transmissao_destinos", [])
        resp = client.patch(
            f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}", json={"titulo": "Novo"},
        )
        assert resp.status_code == 409

    def test_delete_204(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("transmissoes", [_transmissao_row()])
        resp = client.delete(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}")
        assert resp.status_code == 204

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.delete(f"/api/whatsapp/transmissoes/{'0' * 8}")
        assert resp.status_code == 404


class TestEnviar:
    def test_enviar_202(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data("transmissoes", [_transmissao_row()])
        client.mock_supabase.set_table_data("transmissao_destinos", [{
            "id": "d1", "org_id": ORG_UUID, "transmissao_id": TRANSMISSAO_1,
            "grupo_id": GRUPO_1, "estado": "pendente",
        }])
        waha = FakeWahaClient()
        _override_waha(client, waha)

        resp = client.post(f"/api/whatsapp/transmissoes/{TRANSMISSAO_1}/enviar")
        assert resp.status_code == 202
        assert resp.json()["destinos"] == 1
        assert len(waha.sent_messages) == 1

    def test_enviar_missing_404(self, client):
        seed_community_role(client, org_role="admin")
        _override_waha(client, FakeWahaClient())
        resp = client.post(f"/api/whatsapp/transmissoes/{'0' * 8}/enviar")
        assert resp.status_code == 404

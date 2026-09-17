"""Tests for the lotes (sincronização) router — contract §Sincronização,
items 8-13. State-machine edge cases (expiry, partial-apply, idempotent
re-apply, daily cap) are pinned at the service layer
(`tests/services/test_sincronizacao_service.py`); this file covers the
HTTP wiring: auth, role gate + D3 redaction, and status codes.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient

from app.dependencies import get_community_waha_client
from tests.conftest import ORG_UUID, seed_community_role

GRUPO_1 = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
LOTE_1 = "22222222-2222-2222-2222-222222222222"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _grupo_row(**over) -> dict:
    base = {"id": GRUPO_1, "org_id": ORG_UUID, "chat_id": CHAT_ID, "nome": "G", "ativo": True}
    base.update(over)
    return base


def _lote_row(**over) -> dict:
    base = {
        "id": LOTE_1, "org_id": ORG_UUID, "grupo_id": GRUPO_1, "acao": "adicionar",
        "estado": "proposto", "total_itens": 1,
        "proposto_em": datetime.now(timezone.utc).isoformat(),
        "expira_em": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }
    base.update(over)
    return base


ITEM_1 = "33333333-3333-3333-3333-333333333333"


def _item_row(**over) -> dict:
    base = {
        "id": ITEM_1, "org_id": ORG_UUID, "lote_id": LOTE_1,
        "membro_id": MEMBRO_1, "participante_jid": "5511974693365@c.us",
        "resultado": "pendente",
    }
    base.update(over)
    return base


def _override_waha(client, waha: FakeWahaClient) -> None:
    client.raw().app.dependency_overrides[get_community_waha_client] = lambda: waha


class TestAuthBoundary:
    def test_criar_lote_without_auth_401(self, client):
        resp = client.raw().post(f"/api/whatsapp/grupos/{GRUPO_1}/lotes", json={"acao": "adicionar"})
        assert resp.status_code == 401

    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/whatsapp/lotes").status_code == 401

    def test_confirmar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/whatsapp/lotes/{LOTE_1}/confirmar", json={"confirmo": True})
        assert resp.status_code == 401

    def test_aplicar_without_auth_401(self, client):
        assert client.raw().post(f"/api/whatsapp/lotes/{LOTE_1}/aplicar").status_code == 401


class TestRoleGate:
    def test_moderador_criar_lote_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/whatsapp/grupos/{GRUPO_1}/lotes", json={"acao": "adicionar"})
        assert resp.status_code == 403

    def test_moderador_confirmar_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/confirmar", json={"confirmo": True})
        assert resp.status_code == 403

    def test_moderador_aplicar_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.post(f"/api/whatsapp/lotes/{LOTE_1}/aplicar").status_code == 403

    def test_moderador_cancelar_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.post(f"/api/whatsapp/lotes/{LOTE_1}/cancelar").status_code == 403

    def test_moderador_convites_pendentes_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get(f"/api/whatsapp/lotes/{LOTE_1}/convites-pendentes").status_code == 403

    def test_moderador_can_list_and_get(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row()])
        client.mock_supabase.set_table_data("lote_itens", [_item_row()])
        assert client.get("/api/whatsapp/lotes").status_code == 200
        assert client.get(f"/api/whatsapp/lotes/{LOTE_1}").status_code == 200

    def test_moderador_get_redacts_item_phone(self, client):
        seed_community_role(client, org_role="moderador")
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row()])
        client.mock_supabase.set_table_data("lote_itens", [_item_row()])
        client.mock_supabase.set_table_data(
            "membros", [{"id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "telefone": "+5511974693365"}],
        )
        resp = client.get(f"/api/whatsapp/lotes/{LOTE_1}")
        assert resp.status_code == 200
        item = resp.json()["itens"][0]
        assert item["telefone_mascarado"] == "***3365"
        assert "telefone" not in item
        assert "participante_jid" not in item


class TestCriarLote:
    def test_criar_lote_201(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data("membros", [])
        client.mock_supabase.set_table_data("planos", [])
        resp = client.post(f"/api/whatsapp/grupos/{GRUPO_1}/lotes", json={"acao": "adicionar"})
        assert resp.status_code == 201
        assert resp.json()["estado"] == "proposto"

    def test_criar_lote_grupo_not_found_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post(f"/api/whatsapp/grupos/{'x' * 8}/lotes", json={"acao": "adicionar"})
        assert resp.status_code == 404


class TestConfirmarCancelar:
    def test_confirmar_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row()])
        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/confirmar", json={"confirmo": True})
        assert resp.status_code == 200
        assert resp.json()["estado"] == "confirmado"

    def test_confirmar_not_proposto_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row(estado="confirmado")])
        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/confirmar", json={"confirmo": True})
        assert resp.status_code == 409

    def test_cancelar_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row()])
        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/cancelar")
        assert resp.status_code == 200
        assert resp.json()["estado"] == "cancelado"


class TestAplicar:
    def test_aplicar_200_all_added(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data(
            "lotes_sincronizacao", [_lote_row(estado="confirmado")],
        )
        client.mock_supabase.set_table_data("lote_itens", [_item_row()])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        _override_waha(client, waha)

        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/aplicar")
        assert resp.status_code == 200
        assert resp.json()["estado"] == "aplicado"

    def test_aplicar_requires_confirmado_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data("lotes_sincronizacao", [_lote_row(estado="proposto")])
        _override_waha(client, FakeWahaClient())
        resp = client.post(f"/api/whatsapp/lotes/{LOTE_1}/aplicar")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Confirme o lote antes de aplicar."


class TestConvitesPendentes:
    def test_convites_pendentes_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupos", [_grupo_row()])
        client.mock_supabase.set_table_data(
            "lotes_sincronizacao", [_lote_row(estado="aplicado_parcial")],
        )
        client.mock_supabase.set_table_data(
            "lote_itens", [_item_row(resultado="convite_necessario")],
        )
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        _override_waha(client, waha)

        resp = client.get(f"/api/whatsapp/lotes/{LOTE_1}/convites-pendentes")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

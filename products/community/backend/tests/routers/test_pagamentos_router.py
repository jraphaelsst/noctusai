"""Tests for `pagamentos_router` — contract §Manager+member views,
amendment A16/P3 (admin-only).
"""
from tests.conftest import ORG_UUID, seed_community_role

MEMBRO_1 = "11111111-1111-1111-1111-111111111111"
PAGAMENTO_1 = "22222222-2222-2222-2222-222222222222"


def _pagamento_row(**over) -> dict:
    base = {
        "id": PAGAMENTO_1, "org_id": ORG_UUID, "assinatura_id": None, "membro_id": MEMBRO_1,
        "gateway": "asaas", "cobranca_externa_id": "pay_1", "valor_centavos": 9900,
        "metodo": "pix", "estado": "pago", "pago_em": "2026-01-01T00:00:00+00:00",
        "vencimento": None, "url_fatura": "https://asaas.test/inv/pay_1",
        "pix_payload": "0002...", "pix_imagem_base64": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _seed(client):
    client.mock_supabase.set_table_data("pagamentos", [_pagamento_row()])
    client.mock_supabase.set_table_data("membros", [{
        "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }])


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/pagamentos").status_code == 401


class TestAmendmentA16AdminOnly:
    def test_moderador_403(self, client):
        _seed(client)
        seed_community_role(client, org_role="moderador")
        resp = client.get("/api/pagamentos")
        assert resp.status_code == 403

    def test_admin_200_full_shape(self, client):
        _seed(client)
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/pagamentos")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["cobranca_externa_id"] == "pay_1"
        assert item["pix_payload"] == "0002..."

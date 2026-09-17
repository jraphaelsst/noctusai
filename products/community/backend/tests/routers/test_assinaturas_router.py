"""Tests for `assinaturas_router` — contract §Manager+member views,
amendment P3 (moderador redaction) and A14 (cancel ordering).
"""
from tests.conftest import ORG_UUID, seed_community_role

MEMBRO_1 = "11111111-1111-1111-1111-111111111111"
PLANO_1 = "22222222-2222-2222-2222-222222222222"
ASSINATURA_1 = "33333333-3333-3333-3333-333333333333"


def _assinatura_row(**over) -> dict:
    base = {
        "id": ASSINATURA_1, "org_id": ORG_UUID, "membro_id": MEMBRO_1, "plano_id": PLANO_1,
        "gateway": "stripe", "assinatura_externa_id": "sub_1", "cliente_externo_id": "cus_1",
        "estado": "ativa", "metodo": "cartao", "ciclo": "mensal",
        "iniciada_em": "2026-01-01T00:00:00+00:00", "ativa_em": "2026-01-01T00:00:00+00:00",
        "cancelada_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "status": "ativo", "plano_id": PLANO_1,
        "origem": "checkout", "tags": [], "user_id": None, "observacoes": None,
        "entrou_em": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _seed(client, *, assinatura_rows=None, membro_rows=None):
    client.mock_supabase.set_table_data(
        "assinaturas", assinatura_rows if assinatura_rows is not None else [_assinatura_row()],
    )
    client.mock_supabase.set_table_data(
        "membros", membro_rows if membro_rows is not None else [_membro_row()],
    )
    client.mock_supabase.set_table_data("planos", [{
        "id": PLANO_1, "org_id": ORG_UUID, "nome": "Círculo",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }])


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/assinaturas").status_code == 401

    def test_cancelar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/assinaturas/{ASSINATURA_1}/cancelar", json={"motivo": "x"})
        assert resp.status_code == 401


class TestAmendmentP3ModeradorRedaction:
    def test_moderador_gets_redacted_field_set(self, client):
        _seed(client)
        seed_community_role(client, org_role="moderador")
        resp = client.get("/api/assinaturas")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert set(item.keys()) == {
            "estado", "metodo", "ciclo", "plano_nome", "membro_nome", "ativa_em",
        }
        assert "assinatura_externa_id" not in item
        assert "id" not in item

    def test_admin_gets_full_shape(self, client):
        _seed(client)
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/assinaturas")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "assinatura_externa_id" in item
        assert item["assinatura_externa_id"] == "sub_1"

    def test_moderador_cancelar_403(self, client):
        _seed(client)
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/assinaturas/{ASSINATURA_1}/cancelar", json={"motivo": "x"})
        assert resp.status_code == 403


class TestCancelar:
    def test_admin_cancels_ok(self, client):
        # No `assinatura_externa_id` — this row never reached the
        # gateway (mirrors an A2/A10 shortcut row), so `cancelar()`
        # skips the remote call entirely. The gateway-cancel HAPPY PATH
        # itself is covered at the service level
        # (`tests/services/test_assinaturas_service.py`) with an
        # explicit `gateway_factory` DI seam — the DEFAULT factory this
        # router wires resolves a REAL `FakePaymentGateway` instance
        # with no knowledge of a subscription id seeded directly into
        # the mock DB, which would 502 for the wrong reason here.
        _seed(client, assinatura_rows=[_assinatura_row(assinatura_externa_id=None)])
        seed_community_role(client, org_role="admin")
        resp = client.post(f"/api/assinaturas/{ASSINATURA_1}/cancelar", json={"motivo": "Pedido da associada"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "cancelada"

        membro = client.mock_supabase.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "cancelado"

    def test_cancelar_unknown_assinatura_404(self, client):
        _seed(client)
        seed_community_role(client, org_role="admin")
        resp = client.post(
            "/api/assinaturas/99999999-9999-9999-9999-999999999999/cancelar",
            json={"motivo": "x"},
        )
        assert resp.status_code == 404

    def test_cancelar_missing_motivo_422(self, client):
        _seed(client)
        seed_community_role(client, org_role="admin")
        resp = client.post(f"/api/assinaturas/{ASSINATURA_1}/cancelar", json={})
        assert resp.status_code == 422

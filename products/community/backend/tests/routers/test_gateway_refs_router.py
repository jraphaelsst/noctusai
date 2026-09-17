"""Tests for the gateway-refs endpoints on `planos_router` — contract
§Gateway refs (admin).
"""
from tests.conftest import ORG_UUID, seed_community_role

PLANO_1 = "11111111-1111-1111-1111-111111111111"


def _seed_plano(client):
    client.mock_supabase.set_table_data("planos", [{
        "id": PLANO_1, "org_id": ORG_UUID, "nome": "Círculo",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }])
    client.mock_supabase.set_table_data("plano_gateway_refs", [])


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        resp = client.raw().get(f"/api/planos/{PLANO_1}/gateway-refs")
        assert resp.status_code == 401

    def test_put_without_auth_401(self, client):
        resp = client.raw().put(
            f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_1"},
        )
        assert resp.status_code == 401


class TestRoleGate:
    def test_moderador_can_read(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="moderador")
        resp = client.get(f"/api/planos/{PLANO_1}/gateway-refs")
        assert resp.status_code == 200

    def test_moderador_put_403(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="moderador")
        resp = client.put(
            f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_1"},
        )
        assert resp.status_code == 403


class TestUpsert:
    def test_create_returns_200_not_201(self, client):
        """Contract: creating returns 200, not 201, because the key is
        the path (upsert semantics)."""
        _seed_plano(client)
        seed_community_role(client, org_role="admin")
        resp = client.put(
            f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_abc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["plano_id"] == PLANO_1
        assert body["gateway"] == "stripe"
        assert body["ref_externo"] == "price_abc"

    def test_upsert_updates_existing(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="admin")
        client.put(f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_v1"})
        resp = client.put(f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_v2"})
        assert resp.status_code == 200
        assert resp.json()["ref_externo"] == "price_v2"

        listed = client.get(f"/api/planos/{PLANO_1}/gateway-refs")
        assert listed.json()["total"] == 1

    def test_invalid_gateway_404(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="admin")
        resp = client.put(
            f"/api/planos/{PLANO_1}/gateway-refs/paypal", json={"ref_externo": "x"},
        )
        assert resp.status_code == 404

    def test_unknown_plano_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.put(
            "/api/planos/99999999-9999-9999-9999-999999999999/gateway-refs/stripe",
            json={"ref_externo": "x"},
        )
        assert resp.status_code == 404


class TestDelete:
    def test_delete_204(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="admin")
        client.put(f"/api/planos/{PLANO_1}/gateway-refs/stripe", json={"ref_externo": "price_1"})
        resp = client.delete(f"/api/planos/{PLANO_1}/gateway-refs/stripe")
        assert resp.status_code == 204

    def test_delete_unknown_404(self, client):
        _seed_plano(client)
        seed_community_role(client, org_role="admin")
        resp = client.delete(f"/api/planos/{PLANO_1}/gateway-refs/stripe")
        assert resp.status_code == 404

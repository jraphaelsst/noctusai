"""Corretores CRUD + alias map — /api/leads/corretores/*. Mirrors
``test_sources_router.py``; extra coverage for ``lead_count`` (§5.2)."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.leads.conftest import auth_headers


def _create_corretor(client, **overrides):
    body = {"nome": "Fulano"}
    body.update(overrides)
    resp = client.post("/api/leads/corretores", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestCorretoresCRUD:
    def test_list_empty(self, http_client):
        resp = http_client.get("/api/leads/corretores", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create_and_lead_count(self, http_client):
        created = _create_corretor(http_client)
        http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "corretor_id": created["id"]},
            headers=auth_headers(),
        )
        resp = http_client.get("/api/leads/corretores", headers=auth_headers())
        row = resp.json()["data"][0]
        assert row["lead_count"] == 1

    def test_update_nome(self, http_client):
        created = _create_corretor(http_client)
        resp = http_client.patch(
            f"/api/leads/corretores/{created['id']}",
            json={"nome": "Renamed"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "Renamed"
        assert resp.json()["data"]["nome_norm"] == "RENAMED"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/leads/corretores/{uuid4()}", json={"nome": "X"}, headers=auth_headers()
        )
        assert resp.status_code == 404

    def test_delete_referenced_409_then_reassign(self, http_client):
        a = _create_corretor(http_client, nome="A")
        b = _create_corretor(http_client, nome="B")
        lead = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "corretor_id": a["id"]},
            headers=auth_headers(),
        ).json()["data"]

        blocked = http_client.delete(f"/api/leads/corretores/{a['id']}", headers=auth_headers())
        assert blocked.status_code == 409

        reassigned = http_client.delete(
            f"/api/leads/corretores/{a['id']}",
            params={"reassign_to": b["id"]},
            headers=auth_headers(),
        )
        assert reassigned.status_code == 200

        refreshed = http_client.get(f"/api/leads/{lead['id']}", headers=auth_headers()).json()["data"]
        assert refreshed["corretor_id"] == b["id"]


class TestCorretorAliases:
    def test_create_and_list_alias(self, http_client):
        corretor = _create_corretor(http_client)
        resp = http_client.post(
            "/api/leads/corretores/aliases",
            json={"alias": "FULANO TYPO", "corretor_id": corretor["id"]},
            headers=auth_headers(),
        )
        assert resp.status_code == 201
        listed = http_client.get("/api/leads/corretores/aliases", headers=auth_headers())
        assert len(listed.json()["data"]) == 1

    def test_create_alias_unknown_corretor_404(self, http_client):
        resp = http_client.post(
            "/api/leads/corretores/aliases",
            json={"alias": "X", "corretor_id": str(uuid4())},
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    def test_delete_alias_nonexistent_404(self, http_client):
        resp = http_client.delete(
            f"/api/leads/corretores/aliases/{uuid4()}", headers=auth_headers()
        )
        assert resp.status_code == 404

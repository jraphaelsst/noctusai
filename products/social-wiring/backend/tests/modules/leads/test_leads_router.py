"""CRUD round-trip + the canonical filter set (§5.1) — multiple values of
ONE param OR together, different params AND together."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.leads.conftest import ORG_A, ORG_B, auth_headers


def _create_lead(client, **overrides):
    body = {"data_entrada": "2026-07-01", "cliente_nome": "Alice"}
    body.update(overrides)
    resp = client.post("/api/leads", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestCRUD:
    def test_create_returns_201_with_envelope(self, http_client):
        data = _create_lead(http_client, cliente_nome="Bob")
        assert data["cliente_nome"] == "Bob"
        assert data["needs_review"] is False
        assert data["tipo_lead"] == "desconhecido"
        assert "id" in data

    def test_create_forbidden_fields_422(self, http_client):
        resp = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "unknown_field": True},
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    def test_get_by_id(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.get(f"/api/leads/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == created["id"]

    def test_get_nonexistent_404(self, http_client):
        resp = http_client.get(f"/api/leads/{uuid4()}", headers=auth_headers())
        assert resp.status_code == 404

    def test_update_field(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"cliente_nome": "Updated"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cliente_nome"] == "Updated"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/leads/{uuid4()}", json={"cliente_nome": "X"}, headers=auth_headers()
        )
        assert resp.status_code == 404

    def test_delete_existing(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.delete(f"/api/leads/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == created["id"]

    def test_delete_nonexistent_404(self, http_client):
        resp = http_client.delete(f"/api/leads/{uuid4()}", headers=auth_headers())
        assert resp.status_code == 404

    def test_list_paginated_envelope(self, http_client):
        _create_lead(http_client)
        _create_lead(http_client)
        resp = http_client.get("/api/leads", headers=auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body and "pagination" in body
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 50


class TestFilters:
    def test_ano_or_within_dimension(self, http_client):
        _create_lead(http_client, data_entrada="2025-03-01", cliente_nome="OldYear")
        _create_lead(http_client, data_entrada="2026-07-01", cliente_nome="NewYear")
        _create_lead(http_client, data_entrada="2024-01-01", cliente_nome="Ancient")

        resp = http_client.get(
            "/api/leads", params=[("ano", 2025), ("ano", 2026)], headers=auth_headers()
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"OldYear", "NewYear"}

    def test_tipo_and_tier_and_together(self, http_client):
        _create_lead(http_client, tipo_lead="novo", anuncio_tier="simples", cliente_nome="A")
        _create_lead(http_client, tipo_lead="novo", anuncio_tier="destaque", cliente_nome="B")
        _create_lead(http_client, tipo_lead="retorno", anuncio_tier="simples", cliente_nome="C")

        resp = http_client.get(
            "/api/leads",
            params={"tipo": "novo", "tier": "simples"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"A"}

    def test_de_ate_range(self, http_client):
        _create_lead(http_client, data_entrada="2026-01-01", cliente_nome="Before")
        _create_lead(http_client, data_entrada="2026-06-15", cliente_nome="Inside")
        _create_lead(http_client, data_entrada="2026-12-31", cliente_nome="After")

        resp = http_client.get(
            "/api/leads",
            params={"de": "2026-06-01", "ate": "2026-06-30"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Inside"}

    def test_q_free_text_over_multiple_columns(self, http_client):
        _create_lead(http_client, cliente_nome="Zebra Corp", observacoes="nothing special")
        _create_lead(http_client, cliente_nome="Other", observacoes="mentions zebra here")
        _create_lead(http_client, cliente_nome="Unrelated", observacoes="nothing")

        resp = http_client.get("/api/leads", params={"q": "zebra"}, headers=auth_headers())
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Zebra Corp", "Other"}

    def test_needs_review_filter(self, http_client):
        _create_lead(http_client, cliente_nome="Flagged")
        flagged_id = None
        resp = http_client.get("/api/leads", headers=auth_headers())
        for row in resp.json()["data"]:
            if row["cliente_nome"] == "Flagged":
                flagged_id = row["id"]
        http_client.patch(
            f"/api/leads/{flagged_id}", json={"needs_review": True}, headers=auth_headers()
        )
        _create_lead(http_client, cliente_nome="Clean")

        resp = http_client.get(
            "/api/leads", params={"needs_review": True}, headers=auth_headers()
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Flagged"}

    def test_unknown_param_ignored_not_422(self, http_client):
        resp = http_client.get(
            "/api/leads", params={"totally_unknown_param": "x"}, headers=auth_headers()
        )
        assert resp.status_code == 200


class TestOrgIsolation:
    def test_list_only_own_org(self, http_client, mock_db):
        from unittest.mock import MagicMock

        from noctusai_lib.testing import MockUser, MockUserResponse

        mock_db.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=ORG_B))
        )
        resp_b = http_client.post(
            "/api/leads", json={"data_entrada": "2026-07-01", "cliente_nome": "OrgB"},
            headers=auth_headers(),
        )
        assert resp_b.status_code == 201

        mock_db.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=ORG_A))
        )
        resp_a = http_client.get("/api/leads", headers=auth_headers())
        names = {r["cliente_nome"] for r in resp_a.json()["data"]}
        assert "OrgB" not in names

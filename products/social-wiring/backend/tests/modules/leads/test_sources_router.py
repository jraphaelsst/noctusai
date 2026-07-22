"""Sources CRUD + alias map — /api/leads/sources/*."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.leads.conftest import auth_headers


def _create_source(client, **overrides):
    body = {"slug": "custom", "label": "Custom Source"}
    body.update(overrides)
    resp = client.post("/api/leads/sources", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestSourcesCRUD:
    def test_list_empty(self, http_client):
        resp = http_client.get("/api/leads/sources", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create_and_list(self, http_client):
        created = _create_source(http_client)
        assert created["slug"] == "custom"
        resp = http_client.get("/api/leads/sources", headers=auth_headers())
        assert len(resp.json()["data"]) == 1

    def test_create_forbidden_field_422(self, http_client):
        resp = http_client.post(
            "/api/leads/sources",
            json={"slug": "x", "label": "X", "bogus": True},
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    def test_update_label(self, http_client):
        created = _create_source(http_client)
        resp = http_client.patch(
            f"/api/leads/sources/{created['id']}",
            json={"label": "Renamed"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["label"] == "Renamed"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/leads/sources/{uuid4()}", json={"label": "X"}, headers=auth_headers()
        )
        assert resp.status_code == 404

    def test_delete_unreferenced(self, http_client):
        created = _create_source(http_client)
        resp = http_client.delete(f"/api/leads/sources/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200

    def test_delete_referenced_409(self, http_client):
        source = _create_source(http_client)
        lead_resp = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "origem_id": source["id"]},
            headers=auth_headers(),
        )
        assert lead_resp.status_code == 201
        resp = http_client.delete(f"/api/leads/sources/{source['id']}", headers=auth_headers())
        assert resp.status_code == 409

    def test_delete_referenced_with_reassign_succeeds(self, http_client):
        source_a = _create_source(http_client, slug="a", label="A")
        source_b = _create_source(http_client, slug="b", label="B")
        lead_resp = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "origem_id": source_a["id"]},
            headers=auth_headers(),
        )
        lead_id = lead_resp.json()["data"]["id"]

        resp = http_client.delete(
            f"/api/leads/sources/{source_a['id']}",
            params={"reassign_to": source_b["id"]},
            headers=auth_headers(),
        )
        assert resp.status_code == 200

        lead = http_client.get(f"/api/leads/{lead_id}", headers=auth_headers()).json()["data"]
        assert lead["origem_id"] == source_b["id"]


class TestSourceAliases:
    def test_create_alias_and_list(self, http_client):
        source = _create_source(http_client)
        resp = http_client.post(
            "/api/leads/sources/aliases",
            json={"alias": "CUSTOM ALT SPELLING", "source_id": source["id"]},
            headers=auth_headers(),
        )
        assert resp.status_code == 201, resp.text
        alias = resp.json()["data"]
        assert alias["alias_norm"] == "CUSTOM ALT SPELLING"
        assert alias["origem"] == "manual"

        listed = http_client.get("/api/leads/sources/aliases", headers=auth_headers())
        assert len(listed.json()["data"]) == 1

    def test_create_alias_with_zero_matches_does_not_error(self, http_client):
        # `origem_raw` isn't settable via the public LeadCreate body (it's
        # importer-only) — the relink-matching-leads path is exercised at
        # the service level instead (test_dimensions_service.py). This
        # just documents the create-alias call is safe when nothing
        # matches (the common case for a brand-new alias).
        source = _create_source(http_client)
        resp = http_client.post(
            "/api/leads/sources/aliases",
            json={"alias": "NEVER SEEN ORIGEM", "source_id": source["id"]},
            headers=auth_headers(),
        )
        assert resp.status_code == 201

    def test_create_alias_unknown_source_404(self, http_client):
        resp = http_client.post(
            "/api/leads/sources/aliases",
            json={"alias": "X", "source_id": str(uuid4())},
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    def test_unmapped_origens_lists_raw_values_without_alias(self, http_client):
        # No sources/aliases created yet; a manually-created lead has no
        # origem_raw (not settable via LeadCreate), so this just confirms
        # the endpoint returns cleanly with an empty queue.
        resp = http_client.get(
            "/api/leads/sources/aliases", params={"unmapped": True}, headers=auth_headers()
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_delete_alias(self, http_client):
        source = _create_source(http_client)
        created = http_client.post(
            "/api/leads/sources/aliases",
            json={"alias": "TEMP", "source_id": source["id"]},
            headers=auth_headers(),
        ).json()["data"]
        resp = http_client.delete(
            f"/api/leads/sources/aliases/{created['id']}", headers=auth_headers()
        )
        assert resp.status_code == 200

    def test_delete_alias_nonexistent_404(self, http_client):
        resp = http_client.delete(
            f"/api/leads/sources/aliases/{uuid4()}", headers=auth_headers()
        )
        assert resp.status_code == 404

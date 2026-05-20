"""HTTP-boundary tests for the brand-kit endpoints.

Covers: list / create (strict body) / get / patch / delete + the
"can't-delete-when-posts-reference-it" guard.
"""
from __future__ import annotations


class TestBrandKitsRouter:
    def test_list_empty_returns_envelope(self, client):
        resp = client.get("/api/media-creation/brand-kits")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == []

    def test_create_happy_path(self, client):
        resp = client.post(
            "/api/media-creation/brand-kits",
            json={
                "name": "Granja Premium",
                "persona": "Editorial. Calm. Premium.",
                "design_system": "Variant: premium. Palette: warm dark.",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["name"] == "Granja Premium"
        assert body["org_id"] == "test-org-123"

    def test_create_rejects_unknown_field(self, client):
        # StrictHttpModel → extra="forbid".
        resp = client.post(
            "/api/media-creation/brand-kits",
            json={"name": "X", "bogus": 1},
        )
        assert resp.status_code == 422, resp.text

    def test_create_requires_name(self, client):
        resp = client.post("/api/media-creation/brand-kits", json={})
        assert resp.status_code == 422, resp.text

    def test_get_unknown_returns_404(self, client):
        resp = client.get("/api/media-creation/brand-kits/does-not-exist")
        assert resp.status_code == 404, resp.text

    def test_patch_updates_persona(self, client, seeded_kit):
        resp = client.patch(
            f"/api/media-creation/brand-kits/{seeded_kit}",
            json={"persona": "Updated voice"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["persona"] == "Updated voice"

    def test_delete_returns_ok(self, client, seeded_kit):
        resp = client.delete(f"/api/media-creation/brand-kits/{seeded_kit}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True

    def test_delete_refused_when_post_references_kit(self, client, seeded_kit):
        # Drop a post that references the kit; deletion must be refused.
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
            }
        ).execute()
        resp = client.delete(f"/api/media-creation/brand-kits/{seeded_kit}")
        assert resp.status_code == 400, resp.text

    def test_unauthenticated_request_rejected(self, client):
        resp = client.raw().get("/api/media-creation/brand-kits")
        assert resp.status_code in (401, 403), resp.text

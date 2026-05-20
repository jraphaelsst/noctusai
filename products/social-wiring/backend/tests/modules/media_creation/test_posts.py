"""HTTP-boundary tests for the post lifecycle endpoints."""
from __future__ import annotations


class TestPostsRouter:
    def test_list_empty(self, client):
        resp = client.get("/api/media-creation/posts")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == []

    def test_create_requires_brand_kit_id(self, client):
        resp = client.post(
            "/api/media-creation/posts",
            json={"title": "X", "idea": "Y"},  # missing brand_kit_id
        )
        assert resp.status_code == 422, resp.text

    def test_create_rejects_unknown_brand_kit(self, client):
        # No kit seeded; service returns None → 400 from the router.
        resp = client.post(
            "/api/media-creation/posts",
            json={
                "brand_kit_id": "ghost-kit",
                "title": "X",
                "idea": "Y",
            },
        )
        assert resp.status_code == 400, resp.text

    def test_create_happy_path(self, client, seeded_kit):
        resp = client.post(
            "/api/media-creation/posts",
            json={
                "brand_kit_id": seeded_kit,
                "title": "3 condomínios em Cotia",
                "idea": "Mostrar três opções de condomínios em Cotia",
                "format": "carousel",
                "slide_count": 5,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["status"] == "draft"
        assert body["title"] == "3 condomínios em Cotia"

    def test_get_post_detail_aggregates_kit(self, client, seeded_kit):
        # Insert a post directly into the mock.
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
                "status": "draft",
            }
        ).execute()
        resp = client.get("/api/media-creation/posts/post-1")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["brand_kit"] is not None
        assert body["brand_kit"]["id"] == seeded_kit
        assert body["slides"] == []

    def test_delete_published_post_refused(self, client, seeded_kit):
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
                "status": "published",
            }
        ).execute()
        resp = client.delete("/api/media-creation/posts/post-1")
        assert resp.status_code == 400, resp.text

    def test_unauthenticated_request_rejected(self, client):
        resp = client.raw().get("/api/media-creation/posts")
        assert resp.status_code in (401, 403), resp.text

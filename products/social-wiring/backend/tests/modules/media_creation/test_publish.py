"""Tests for the /publish endpoint + PublishService.

Wires the seed ``MetaAdapter`` via constructor injection so the live
Graph isn't touched. The route resolver picks ``FakeMetaAdapter`` when
``META_SYSTEM_USER_TOKEN`` is unset (the default in CI), so the
unconfigured-shape tests don't need an explicit adapter.
"""
from __future__ import annotations

from noctusai_lib.integrations.meta import FakeMetaAdapter, MetaGraphError


def _seed_rendered_post(client, kit_id: str, slide_count: int = 3) -> None:
    client.mock_supabase.from_("mc_posts").insert(
        {
            "id": "post-1",
            "org_id": "test-org-123",
            "brand_kit_id": kit_id,
            "title": "Three condos",
            "idea": "Three premium condos under R$1.5M",
            "format": "carousel",
            "variant": "premium",
            "slide_count": slide_count,
            "status": "draft",
            "copy_caption": "Premium condos under R$1.5M near São Paulo.",
            "copy_hashtags": ["#premium", "#condo", "#cotia"],
        }
    ).execute()
    rows = []
    for n in range(1, slide_count + 1):
        rows.append(
            {
                "id": f"slide-{n}",
                "org_id": "test-org-123",
                "post_id": "post-1",
                "slide_n": n,
                "role": "cover" if n == 1 else "list_item",
                "headline": f"Slide {n}",
                "body": "",
                "visual_brief": "VB",
                "prompt_nano_banana": "P",
                "image_url": f"https://cdn.example.com/post-1/slide-{n}.png",
                "image_renderer": "nano_banana",
            }
        )
    client.mock_supabase.from_("mc_post_slides").insert(rows).execute()


class TestPublish:
    def test_publish_404_when_post_missing(self, client):
        resp = client.post(
            "/api/media-creation/posts/ghost/publish",
            json={"target": "instagram_carousel", "destination_id": "IG1"},
        )
        assert resp.status_code == 404, resp.text

    def test_publish_carousel_with_fake_adapter_persists_state(
        self, client, seeded_kit
    ):
        _seed_rendered_post(client, seeded_kit, slide_count=3)
        # No META_SYSTEM_USER_TOKEN → service resolves FakeMetaAdapter.
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "instagram_carousel", "destination_id": "IG1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["configured"] is False
        assert body["target"] == "instagram_carousel"
        assert body["media_id"].startswith("IG1_carousel_")
        assert body["permalink"].startswith("https://instagram.com/p/IG1_carousel_")
        # Publication state persisted.
        row = (
            client.mock_supabase.from_("mc_posts")
            .select("*")
            .eq("id", "post-1")
            .execute()
        )
        assert row.data[0]["status"] == "published"
        assert row.data[0]["published_target"] == "instagram_carousel"
        assert row.data[0]["published_media_id"] == body["media_id"]
        assert row.data[0]["published_permalink"] == body["permalink"]
        assert row.data[0]["published_at"] is not None

    def test_publish_422_on_unsupported_target(self, client, seeded_kit):
        _seed_rendered_post(client, seeded_kit, slide_count=3)
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "tiktok_reel", "destination_id": "IG1"},
        )
        assert resp.status_code == 422, resp.text
        assert "unsupported_target" in resp.text

    def test_publish_422_when_slides_missing(self, client, seeded_kit):
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
                "format": "carousel",
                "variant": "premium",
                "slide_count": 0,
                "status": "draft",
            }
        ).execute()
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "instagram_carousel", "destination_id": "IG1"},
        )
        assert resp.status_code == 422, resp.text
        assert "slides_missing" in resp.text

    def test_publish_422_when_render_incomplete(self, client, seeded_kit):
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
                "format": "carousel",
                "variant": "premium",
                "slide_count": 2,
                "status": "draft",
            }
        ).execute()
        client.mock_supabase.from_("mc_post_slides").insert(
            [
                {
                    "id": "slide-1",
                    "org_id": "test-org-123",
                    "post_id": "post-1",
                    "slide_n": 1,
                    "role": "cover",
                    "headline": "H",
                    "body": "",
                    "visual_brief": "VB",
                    "image_url": "https://cdn/x.png",
                },
                {
                    "id": "slide-2",
                    "org_id": "test-org-123",
                    "post_id": "post-1",
                    "slide_n": 2,
                    "role": "cta",
                    "headline": "C",
                    "body": "",
                    "visual_brief": "VB",
                    # image_url missing — render incomplete.
                },
            ]
        ).execute()
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "instagram_carousel", "destination_id": "IG1"},
        )
        assert resp.status_code == 422, resp.text
        assert "render_incomplete" in resp.text

    def test_publish_422_carousel_with_single_slide(self, client, seeded_kit):
        _seed_rendered_post(client, seeded_kit, slide_count=1)
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "instagram_carousel", "destination_id": "IG1"},
        )
        assert resp.status_code == 422, resp.text
        assert "carousel_needs_min_two_slides" in resp.text

    def test_publish_422_when_meta_scope_pending_app_review(
        self, client, seeded_kit
    ):
        _seed_rendered_post(client, seeded_kit, slide_count=3)

        class _GatedFakeMetaAdapter(FakeMetaAdapter):
            """Carousel publish is App-Review-gated. A real subclass
            override (DI test-double), not a monkeypatch of our own Fake —
            per KB § PATTERNS/di-test-seam.md."""

            def publish_instagram_carousel(self, *args, **kwargs):
                raise MetaGraphError(
                    "(#10) instagram_content_publish not granted",
                    code=10,
                    error_subcode=None,
                    error_type="OAuthException",
                )

        gated = _GatedFakeMetaAdapter()

        # Inject the gated adapter through the router's DI seam
        # (`app.dependency_overrides`) — no patching of our own class.
        from app.modules.media_creation.routers.generation import (
            get_publish_service,
        )
        from app.modules.media_creation.services.publish_service import (
            PublishService,
        )

        app = client.raw().app
        app.dependency_overrides[get_publish_service] = lambda: PublishService(
            client.mock_supabase, "test-org-123", meta_adapter=gated
        )
        try:
            resp = client.post(
                "/api/media-creation/posts/post-1/publish",
                json={"target": "instagram_carousel", "destination_id": "IG1"},
            )
        finally:
            app.dependency_overrides.pop(get_publish_service, None)
        assert resp.status_code == 422, resp.text
        assert "meta_scope_pending_app_review" in resp.text

    def test_publish_instagram_single_uses_first_slide(self, client, seeded_kit):
        _seed_rendered_post(client, seeded_kit, slide_count=1)
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "instagram_single", "destination_id": "IG1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["target"] == "instagram_single"
        assert body["media_id"].startswith("IG1_media_")

    def test_publish_facebook_photo_uses_first_slide(self, client, seeded_kit):
        _seed_rendered_post(client, seeded_kit, slide_count=1)
        resp = client.post(
            "/api/media-creation/posts/post-1/publish",
            json={"target": "facebook_photo", "destination_id": "P1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["target"] == "facebook_photo"
        assert body["media_id"].startswith("P1_")

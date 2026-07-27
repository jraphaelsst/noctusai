"""Tests for the LLM-driven generation pipeline + the gated /render endpoint.

The LLM call is patched at the seed entry point
(``noctusai_lib.integrations.llm.chat_completion``), not in the product
module — per ``feedback_no_monkeypatching_in_tests``, this is the
sanctioned external-integration boundary.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch


class TestGenerationStoryboard:
    def test_404_when_post_missing(self, client):
        resp = client.post(
            "/api/media-creation/posts/ghost/generate/storyboard"
        )
        assert resp.status_code == 404, resp.text

    def test_happy_path_persists_storyboard_and_slides(self, client, seeded_kit):
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
        canned_storyboard = {
            "title": "X",
            "audience": "investors",
            "key_message": "Buy now",
            "cta": "Visit our site",
            "arc_pattern": "List of N",
            "rationale": "Mirrors premium-tone references.",
            "slides": [
                {
                    "n": 1,
                    "role": "cover",
                    "headline": "Hook in seven words",
                    "body": "",
                    "visual_brief": "Editorial photo of a condo",
                },
                {
                    "n": 2,
                    "role": "cta",
                    "headline": "Talk to us",
                    "body": "DM for details",
                    "visual_brief": "Logo on dark background",
                },
            ],
        }
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(canned_storyboard)),
        ):
            resp = client.post(
                "/api/media-creation/posts/post-1/generate/storyboard"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["cta"] == "Visit our site"
        assert len(body["slides"]) == 2

    def test_llm_error_envelope_surfaces_as_422(self, client, seeded_kit):
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
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps({"error": "input too vague"})),
        ):
            resp = client.post(
                "/api/media-creation/posts/post-1/generate/storyboard"
            )
        assert resp.status_code == 422, resp.text
        assert "input too vague" in resp.text


class TestRender:
    """The render stage exercises the seed image-gen adapter.

    With no GEMINI_API_KEY resolved, ``get_image_gen_adapter`` returns the
    Fake adapter — ``render_post`` then falls back to the deterministic SVG
    render (a visible, brand-locked placeholder as a ``data:`` URL) and flags
    ``configured=False`` + ``mode="svg_fallback"`` (the loud "not configured"
    signal per feedback_gated_capability_honesty), never a broken image or 503.
    """

    def _seed_post_with_slides(self, client, kit_id: str) -> None:
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": kit_id,
                "title": "X",
                "idea": "Y",
                "format": "carousel",
                "variant": "premium",
                "slide_count": 2,
                "status": "draft",
            }
        ).execute()
        client.mock_supabase.from_("mc_post_slides").insert([
            {
                "id": "slide-1",
                "org_id": "test-org-123",
                "post_id": "post-1",
                "slide_n": 1,
                "role": "cover",
                "headline": "Hook",
                "body": "",
                "visual_brief": "Editorial cover photo",
                "prompt_nano_banana": "A premium editorial photo of a condo",
                "prompt_galilai": "GalilAI flavor",
                "prompt_midjourney": "Midjourney flavor",
            },
            {
                "id": "slide-2",
                "org_id": "test-org-123",
                "post_id": "post-1",
                "slide_n": 2,
                "role": "cta",
                "headline": "Talk to us",
                "body": "DM",
                "visual_brief": "Logo on dark background",
                "prompt_nano_banana": "Brand logo on dark background",
                "prompt_galilai": "GalilAI flavor",
                "prompt_midjourney": "Midjourney flavor",
            },
        ]).execute()

    def test_render_404_when_post_missing(self, client):
        resp = client.post("/api/media-creation/posts/ghost/render")
        assert resp.status_code == 404, resp.text

    def test_render_with_no_gemini_key_falls_back_to_svg_and_flags_configured_false(
        self, client, seeded_kit
    ):
        self._seed_post_with_slides(client, seeded_kit)
        resp = client.post("/api/media-creation/posts/post-1/render")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["configured"] is False
        assert body["mode"] == "svg_fallback"
        assert body["placeholder"] is True
        assert body["requested_renderer"] == "nano_banana"
        assert len(body["slides"]) == 2
        for slide in body["slides"]:
            # A visible, inline placeholder — NOT the old broken sentinel URL.
            assert slide["image_url"].startswith("data:image/png;base64,")
            assert slide["renderer"] == "svg"

    def test_render_422_when_slides_missing(self, client, seeded_kit):
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
        resp = client.post("/api/media-creation/posts/post-1/render")
        assert resp.status_code == 422, resp.text
        assert "slides_missing" in resp.text

    def test_render_422_on_unsupported_renderer(self, client, seeded_kit):
        self._seed_post_with_slides(client, seeded_kit)
        resp = client.post(
            "/api/media-creation/posts/post-1/render",
            json={"renderer": "stable_diffusion"},
        )
        assert resp.status_code == 422, resp.text
        assert "unsupported_renderer" in resp.text

    def test_render_persists_image_url_to_slides(self, client, seeded_kit):
        self._seed_post_with_slides(client, seeded_kit)
        resp = client.post("/api/media-creation/posts/post-1/render")
        assert resp.status_code == 200, resp.text
        slides = (
            client.mock_supabase.from_("mc_post_slides")
            .select("*")
            .eq("post_id", "post-1")
            .order("slide_n")
            .execute()
        )
        assert len(slides.data) == 2
        for slide in slides.data:
            assert slide["image_url"].startswith("data:image/png;base64,")
            assert slide["image_renderer"] == "svg"

    def test_render_fake_mode_renders_svg_even_without_prompt(self, client, seeded_kit):
        # The SVG fallback composes slides from headline/body — it does NOT need
        # the per-renderer image prompts, so a slide rendered before generate/
        # prompts still gets a visible placeholder (never skipped/blank).
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
                "format": "carousel",
                "variant": "premium",
                "slide_count": 1,
                "status": "draft",
            }
        ).execute()
        client.mock_supabase.from_("mc_post_slides").insert({
            "id": "slide-1",
            "org_id": "test-org-123",
            "post_id": "post-1",
            "slide_n": 1,
            "role": "capa",
            "headline": "H",
            "body": "",
            "visual_brief": "VB",
            # No prompt_nano_banana — operator hasn't run generate/prompts.
        }).execute()
        resp = client.post("/api/media-creation/posts/post-1/render")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["mode"] == "svg_fallback"
        assert body["slides"][0]["image_url"].startswith("data:image/png;base64,")

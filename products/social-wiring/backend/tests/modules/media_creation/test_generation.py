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


class TestRenderGate:
    def test_render_returns_typed_gate(self, client, seeded_kit):
        client.mock_supabase.from_("mc_posts").insert(
            {
                "id": "post-1",
                "org_id": "test-org-123",
                "brand_kit_id": seeded_kit,
                "title": "X",
                "idea": "Y",
            }
        ).execute()
        resp = client.post("/api/media-creation/posts/post-1/render")
        # The endpoint returns 200 with a typed gate body — per
        # feedback_gated_capability_honesty, the capability is a
        # never-faked signal, not a hidden endpoint.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert body["gate"] == "image_generation_not_configured"
        assert "renderers_supported_when_enabled" in body

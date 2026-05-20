"""Shape-eval harness for the media_creation 3-stage LLM pipeline.

Each JSON case under ``cases/`` pins the LLM output verbatim and asserts
the persisted artifact's shape. The harness auto-skips when ``cases/``
is empty (no JSON files yet — case curation tracked in
``projects/media-creator-evals-cases/PROJECT.md``).

Case schema is documented in ``cases/../README.md``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_CASES_DIR = Path(__file__).parent / "cases"
_CASE_FILES = sorted(_CASES_DIR.glob("*.json"))


def _case_id(path: Path) -> str:
    return path.stem


@pytest.fixture
def kit_id(client, request) -> str:
    case: dict[str, Any] = request.getfixturevalue("case")
    kit = case["brand_kit"]
    client.mock_supabase.from_("mc_brand_kits").insert(
        {
            "id": "eval-kit",
            "org_id": "test-org-123",
            "name": kit["name"],
            "persona": kit["persona"],
            "design_system": kit["design_system"],
            "default_lang": kit.get("default_lang", "pt-BR"),
        }
    ).execute()
    return "eval-kit"


@pytest.fixture
def post_id(client, kit_id, request) -> str:
    case: dict[str, Any] = request.getfixturevalue("case")
    post = case["post"]
    client.mock_supabase.from_("mc_posts").insert(
        {
            "id": "eval-post",
            "org_id": "test-org-123",
            "brand_kit_id": kit_id,
            "title": post.get("title", post["idea"][:80]),
            "idea": post["idea"],
            "format": post["format"],
            "variant": post["variant"],
            "slide_count": post["slide_count"],
            "status": "draft",
        }
    ).execute()
    return "eval-post"


@pytest.mark.skipif(
    not _CASE_FILES,
    reason=(
        "No eval cases under cases/. Curation tracked in "
        "projects/media-creator-evals-cases/PROJECT.md."
    ),
)
@pytest.mark.parametrize(
    "case",
    [json.loads(p.read_text()) for p in _CASE_FILES],
    ids=[_case_id(p) for p in _CASE_FILES],
)
class TestPipelineShapeEval:
    """Runs storyboard → prompts → copy with the case-pinned LLM output."""

    def test_storyboard_shape(self, client, post_id, case):
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(case["expected"]["storyboard"])),
        ):
            resp = client.post(
                f"/api/media-creation/posts/{post_id}/generate/storyboard"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        asserts = case.get("asserts", {})
        if "min_slides" in asserts:
            assert len(body["slides"]) >= asserts["min_slides"]
        if "max_slides" in asserts:
            assert len(body["slides"]) <= asserts["max_slides"]

    def test_prompts_shape(self, client, post_id, case):
        # storyboard first (slides must exist before prompts)
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(case["expected"]["storyboard"])),
        ):
            client.post(f"/api/media-creation/posts/{post_id}/generate/storyboard")
        prompts_payload = {"slides": case["expected"]["image_prompts"]}
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(prompts_payload)),
        ):
            resp = client.post(
                f"/api/media-creation/posts/{post_id}/generate/prompts"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert len(body["slides"]) == len(case["expected"]["image_prompts"])
        for slide in body["slides"]:
            assert slide.get("prompt_nano_banana")

    def test_copy_shape(self, client, post_id, case):
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(case["expected"]["storyboard"])),
        ):
            client.post(f"/api/media-creation/posts/{post_id}/generate/storyboard")
        with patch(
            "app.modules.media_creation.services.generation_service.chat_completion",
            new=AsyncMock(return_value=json.dumps(case["expected"]["copy"])),
        ):
            resp = client.post(
                f"/api/media-creation/posts/{post_id}/generate/copy"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        asserts = case.get("asserts", {})
        if "min_caption_chars" in asserts:
            assert len(body["caption"]) >= asserts["min_caption_chars"]
        if "min_hashtags" in asserts:
            assert len(body["hashtags"]) >= asserts["min_hashtags"]
        if "expect_cta_keyword" in asserts:
            assert asserts["expect_cta_keyword"].lower() in body["caption"].lower()

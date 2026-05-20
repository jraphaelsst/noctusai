"""LLM-driven generation pipeline — storyboard / image prompts / copy.

The three skill stages ported from the sibling ``media-creator/`` repo, run
as idempotent service methods. Each method:

1. Reads the post + brand kit + references from the DB.
2. Calls ``noctusai_lib.integrations.llm.chat_completion`` with the
   per-stage system prompt + tenant context bundled into the user message.
3. Parses the JSON reply.
4. Writes the structured output to the appropriate columns (``mc_posts``
   for storyboard/copy, ``mc_post_slides`` for prompts).
5. Returns the parsed structure for the caller.

The LLM provider + model are inherited from the seed factory — services
do NOT pick a model. ``org_id`` is propagated for per-org key resolution
and budget accounting.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from noctusai_lib.integrations.llm import chat_completion

from app.modules.media_creation.prompts import (
    COPY_SYSTEM_PROMPT,
    IMAGE_PROMPTS_SYSTEM_PROMPT,
    STORYBOARD_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when the LLM returns an unparsable or self-flagged-error reply."""


class GenerationService:
    """Composes the 3-stage LLM pipeline for one post.

    All methods are async (the LLM client is async). Callers are expected to
    await from FastAPI handlers.
    """

    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    # ── Stage 1: storyboard ─────────────────────────────────────────────

    async def generate_storyboard(self, post: dict[str, Any]) -> dict[str, Any]:
        """Idea + brand kit → structured storyboard. Persists to mc_posts +
        replaces mc_post_slides for this post.
        """
        kit = self._load_brand_kit(post["brand_kit_id"])
        if not kit:
            raise GenerationError("brand_kit_not_found")

        references = self._load_references(post["brand_kit_id"])
        user_message = self._compose_storyboard_user_message(post, kit, references)
        reply = await self._call_llm(STORYBOARD_SYSTEM_PROMPT, user_message)
        data = self._parse_json(reply)
        if "error" in data:
            raise GenerationError(data["error"])

        # Persist storyboard JSON + slides table.
        (
            self.db.table("mc_posts")
            .update({"storyboard": data})
            .eq("id", post["id"])
            .eq("org_id", self.org_id)
            .execute()
        )
        slide_rows = [
            {
                "slide_n": s.get("n"),
                "role": s.get("role"),
                "headline": s.get("headline"),
                "body": s.get("body"),
                "visual_brief": s.get("visual_brief"),
            }
            for s in data.get("slides", [])
        ]
        self._replace_slides(post["id"], slide_rows)
        return data

    # ── Stage 2: image prompts ──────────────────────────────────────────

    async def generate_image_prompts(self, post: dict[str, Any]) -> dict[str, Any]:
        """Storyboard → three renderer-flavored prompts per slide. Updates
        mc_post_slides.prompt_* columns.
        """
        if not post.get("storyboard"):
            raise GenerationError("storyboard_missing — run generate_storyboard first")

        kit = self._load_brand_kit(post["brand_kit_id"])
        if not kit:
            raise GenerationError("brand_kit_not_found")

        user_message = self._compose_image_prompts_user_message(post, kit)
        reply = await self._call_llm(IMAGE_PROMPTS_SYSTEM_PROMPT, user_message)
        data = self._parse_json(reply)
        if "error" in data:
            raise GenerationError(data["error"])

        for slide in data.get("slides", []):
            (
                self.db.table("mc_post_slides")
                .update(
                    {
                        "prompt_nano_banana": slide.get("prompt_nano_banana"),
                        "prompt_galilai": slide.get("prompt_galilai"),
                        "prompt_midjourney": slide.get("prompt_midjourney"),
                    }
                )
                .eq("post_id", post["id"])
                .eq("org_id", self.org_id)
                .eq("slide_n", slide.get("n"))
                .execute()
            )
        return data

    # ── Stage 3: copy ───────────────────────────────────────────────────

    async def generate_copy(self, post: dict[str, Any]) -> dict[str, Any]:
        """Storyboard + brand kit → caption / hashtags / alt / first-comment.
        Updates the post's copy_* columns.
        """
        if not post.get("storyboard"):
            raise GenerationError("storyboard_missing — run generate_storyboard first")

        kit = self._load_brand_kit(post["brand_kit_id"])
        if not kit:
            raise GenerationError("brand_kit_not_found")

        user_message = self._compose_copy_user_message(post, kit)
        reply = await self._call_llm(COPY_SYSTEM_PROMPT, user_message)
        data = self._parse_json(reply)
        if "error" in data:
            raise GenerationError(data["error"])

        (
            self.db.table("mc_posts")
            .update(
                {
                    "copy_caption": data.get("caption"),
                    "copy_hashtags": data.get("hashtags") or [],
                    "copy_alt_text": data.get("alt_text"),
                    "copy_first_comment": data.get("first_comment"),
                }
            )
            .eq("id", post["id"])
            .eq("org_id", self.org_id)
            .execute()
        )
        return data

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _call_llm(self, system_prompt: str, user_message: str) -> str:
        return await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            org_id=self.org_id,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

    @staticmethod
    def _parse_json(reply: str) -> dict[str, Any]:
        # Strip possible code fences (some providers wrap JSON in ```json blocks
        # despite response_format). Be liberal in what we accept.
        text = reply.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("media_creation: LLM returned unparsable JSON: %s", exc)
            raise GenerationError(f"invalid_json_from_llm: {exc}") from exc

    def _load_brand_kit(self, kit_id: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def _load_references(self, kit_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("mc_brand_references")
            .select("*")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data or []

    def _replace_slides(self, post_id: str, rows: list[dict[str, Any]]) -> None:
        (
            self.db.table("mc_post_slides")
            .delete()
            .eq("post_id", post_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        if not rows:
            return
        payload = [{**r, "post_id": post_id, "org_id": self.org_id} for r in rows]
        self.db.table("mc_post_slides").insert(payload).execute()

    # ── User-message composers ──────────────────────────────────────────

    @staticmethod
    def _compose_storyboard_user_message(
        post: dict[str, Any], kit: dict[str, Any], references: list[dict[str, Any]]
    ) -> str:
        ref_summary = "\n".join(
            f"- [{r['kind']}] {r['label']}"
            + (f" — {r['notes']}" if r.get("notes") else "")
            for r in references
        ) or "(none provided)"
        return f"""# Brand kit

## Persona
{kit.get('persona') or '(empty — use sensible defaults)'}

## Design system
{kit.get('design_system') or '(empty — use sensible defaults)'}

## References
{ref_summary}

## Language
{kit.get('default_lang') or 'pt-BR'}

# Post request

- Title: {post.get('title')}
- Idea: {post.get('idea')}
- Format: {post.get('format')}
- Variant: {post.get('variant')}
- Slide count: {post.get('slide_count')}
- CTA: {post.get('cta') or '(decide — write something punchy)'}
- Audience: {post.get('audience') or '(decide based on the idea)'}
- Key message: {post.get('key_message') or '(decide — one sentence)'}

Produce the storyboard JSON now."""

    @staticmethod
    def _compose_image_prompts_user_message(
        post: dict[str, Any], kit: dict[str, Any]
    ) -> str:
        storyboard = post.get("storyboard") or {}
        return f"""# Design system
{kit.get('design_system') or '(empty)'}

# Storyboard (already approved)
{json.dumps(storyboard, ensure_ascii=False, indent=2)}

Produce one prompt set per slide. Output the JSON object now."""

    @staticmethod
    def _compose_copy_user_message(
        post: dict[str, Any], kit: dict[str, Any]
    ) -> str:
        storyboard = post.get("storyboard") or {}
        return f"""# Brand persona
{kit.get('persona') or '(empty)'}

# Storyboard
{json.dumps(storyboard, ensure_ascii=False, indent=2)}

# Language
{kit.get('default_lang') or 'pt-BR'}

Produce the JSON copy object now."""

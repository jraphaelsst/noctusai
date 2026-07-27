"""LLM-driven generation pipeline — storyboard / image prompts / copy.

The three generation stages, run as idempotent service methods. Each method:

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

import base64

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.image_gen import (
    FakeImageGenAdapter,
    ImageGenAdapter,
    ImagePromptInput,
    get_image_gen_adapter,
)
from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.svg_render import (
    SvgRenderAdapter,
    SvgRenderInput,
    get_svg_render_adapter,
)

from app.modules.media_creation.design import build_slide_svg, resolve_tokens
from app.modules.media_creation.prompts import (
    COPY_SYSTEM_PROMPT,
    IMAGE_PROMPTS_SYSTEM_PROMPT,
    SCORE_SYSTEM_PROMPT,
    STORYBOARD_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when the LLM returns an unparsable or self-flagged-error reply."""


def _default_gemini_key_provider(org_id: str | None = None) -> str | None:
    return resolve_credential("gemini_api_key", org_id)


def _slide_aspect_ratio(slide: dict[str, Any], post: dict[str, Any]) -> str:
    """Pick the renderer aspect ratio from post format.

    Instagram carousel + single-image → 1:1 (square). Forward-compat
    video → 9:16 (story). Anything else → 1:1 default.
    """
    fmt = (post.get("format") or "carousel").lower()
    if fmt in ("video", "reels"):
        return "9:16"
    return "1:1"


class GenerationService:
    """Composes the 3-stage LLM pipeline for one post + the image-render stage.

    All LLM methods are async (the LLM client is async). Callers are expected
    to await from FastAPI handlers. The image-render path is synchronous (the
    seed image-gen adapter is sync).

    ``image_gen_adapter`` is constructor-injectable for tests. In production
    it defaults to ``get_image_gen_adapter(_default_gemini_key_provider,
    org_id=self.org_id)`` — which returns ``FakeImageGenAdapter`` when no
    Gemini key is resolved for the org. In that Fake case :meth:`render_post`
    routes to the deterministic SVG render (a visible, brand-locked placeholder)
    and flags ``configured=False`` — the loud "not configured" signal per
    ``feedback_gated_capability_honesty`` (never a broken image, never a 503).
    """

    def __init__(
        self,
        db,
        org_id: str,
        *,
        image_gen_adapter: ImageGenAdapter | None = None,
        svg_render_adapter: SvgRenderAdapter | None = None,
    ):
        self.db = db
        self.org_id = org_id
        self._image_gen_adapter = image_gen_adapter
        self._svg_render_adapter = svg_render_adapter

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

    # ── Stage 3b: score (methodology audit) ─────────────────────────────

    async def score_post(self, post: dict[str, Any]) -> dict[str, Any]:
        """Audit a finished post against the Método Audience rubric (8 criteria).

        Returns ``{score, verdict, strengths, corrections, criteria, rationale}``
        and persists it to ``mc_posts.score`` (JSONB) so it survives reload.
        Requires a storyboard (the minimum gradeable artifact); caption is
        graded when present.
        """
        if not post.get("storyboard"):
            raise GenerationError("storyboard_missing — run generate_storyboard first")

        slides = (
            self.db.table("mc_post_slides")
            .select("*")
            .eq("post_id", post["id"])
            .eq("org_id", self.org_id)
            .order("slide_n")
            .execute()
        )
        user_message = self._compose_score_user_message(post, slides.data or [])
        reply = await self._call_llm(SCORE_SYSTEM_PROMPT, user_message)
        data = self._parse_json(reply)
        if "error" in data:
            raise GenerationError(data["error"])

        (
            self.db.table("mc_posts")
            .update({"score": data})
            .eq("id", post["id"])
            .eq("org_id", self.org_id)
            .execute()
        )
        return data

    # ── Stage 4: render (image generation) ──────────────────────────────

    def render_post(
        self,
        post: dict[str, Any],
        *,
        renderer: str = "nano_banana",
        mode: str = "raster",
        variant: str | None = None,
    ) -> dict[str, Any]:
        """Render the post's slides — two modes.

        ``mode="raster"`` (default) — the original path below: each slide's
        renderer-flavored prompt → a full AI image via the seed image-gen
        adapter (Gemini "Nano Banana").

        ``mode="svg"`` — deterministic, brand-locked SVG slides (locked
        palette / typography / layout from the brand kit's design tokens;
        AI is NOT used for the slide text/layout) → rasterized to PNG via
        the seed ``svg_render`` primitive. See :meth:`_render_post_svg`.

        **Raster fallback:** when ``mode="raster"`` but no Gemini key is
        resolved for the org (the adapter is the Fake), we do NOT persist the
        Fake's non-resolvable sentinel URL (it renders as a broken image).
        Instead we fall back to the deterministic SVG render so the pipeline
        always yields a visible, brand-locked placeholder slide — flagged
        ``configured=False`` + ``mode="svg_fallback"`` so the FE can invite the
        operator to configure Gemini for AI imagery.
        """
        if mode == "svg":
            return self._render_post_svg(post, variant=variant)
        # Validate the raster renderer up front so bad input is rejected even
        # when we take the Fake→SVG fallback below.
        if renderer not in ("nano_banana", "galilai", "midjourney"):
            raise GenerationError(
                f"unsupported_renderer: {renderer!r} "
                "(supported: nano_banana, galilai, midjourney)"
            )
        adapter = self._resolve_image_gen_adapter()
        if isinstance(adapter, FakeImageGenAdapter):
            result = self._render_post_svg(post, variant=variant or post.get("variant"))
            result["configured"] = False
            result["mode"] = "svg_fallback"
            result["placeholder"] = True
            result["requested_renderer"] = renderer
            return result
        return self._render_post_raster(post, renderer=renderer, adapter=adapter)

    def _render_post_raster(
        self,
        post: dict[str, Any],
        *,
        renderer: str = "nano_banana",
        adapter: ImageGenAdapter | None = None,
    ) -> dict[str, Any]:
        """Storyboard prompts → real images via the seed image-gen adapter.

        Iterates over the post's slides, picks the renderer-flavored prompt
        (``nano_banana`` by default; ``galilai`` / ``midjourney`` if the
        operator picks a different renderer in the FE), calls the seed
        adapter, persists ``image_url`` + ``image_renderer`` onto each
        slide.

        Returns ``{configured, renderer, slides: [{slide_n, image_url,
        renderer, model}]}``. ``configured`` is ``False`` when the adapter
        is the Fake (no Gemini key resolved for the org) — that flag lets
        the FE surface "configure your Gemini key" UI without inspecting
        URL hosts.

        Per ``feedback_gated_capability_honesty``: the endpoint ALWAYS
        executes. When the resolved adapter is the Fake, :meth:`render_post`
        routes to the SVG fallback instead of calling this method — so this
        path only runs with a real (configured) adapter.
        """
        adapter = adapter or self._resolve_image_gen_adapter()
        configured = not isinstance(adapter, FakeImageGenAdapter)

        slides = (
            self.db.table("mc_post_slides")
            .select("*")
            .eq("post_id", post["id"])
            .eq("org_id", self.org_id)
            .order("slide_n")
            .execute()
        )
        slide_rows = slides.data or []
        if not slide_rows:
            raise GenerationError(
                "slides_missing — run generate_storyboard + generate_image_prompts first"
            )

        prompt_column = {
            "nano_banana": "prompt_nano_banana",
            "galilai": "prompt_galilai",
            "midjourney": "prompt_midjourney",
        }.get(renderer)
        if prompt_column is None:
            raise GenerationError(
                f"unsupported_renderer: {renderer!r} "
                "(supported: nano_banana, galilai, midjourney)"
            )

        results: list[dict[str, Any]] = []
        for slide in slide_rows:
            prompt_text = slide.get(prompt_column)
            if not prompt_text:
                # Skip slides without a prompt — caller must regenerate
                # prompts first. Don't silently fabricate one.
                results.append({
                    "slide_n": slide["slide_n"],
                    "image_url": None,
                    "renderer": renderer,
                    "model": None,
                    "skipped_reason": "prompt_missing",
                })
                continue
            image = adapter.generate(
                ImagePromptInput(
                    prompt=prompt_text,
                    renderer=renderer,
                    aspect_ratio=_slide_aspect_ratio(slide, post),
                    request_id=f"{post['id']}:{slide['slide_n']}",
                ),
                org_id=self.org_id,
            )
            (
                self.db.table("mc_post_slides")
                .update(
                    {
                        "image_url": image.image_url,
                        "image_renderer": image.renderer,
                    }
                )
                .eq("post_id", post["id"])
                .eq("org_id", self.org_id)
                .eq("slide_n", slide["slide_n"])
                .execute()
            )
            results.append({
                "slide_n": slide["slide_n"],
                "image_url": image.image_url,
                "renderer": image.renderer,
                "model": image.model,
                "latency_ms": image.latency_ms,
            })

        return {
            "configured": configured,
            "renderer": renderer,
            "backend": adapter.backend,
            "slides": results,
        }

    def _resolve_image_gen_adapter(self) -> ImageGenAdapter:
        if self._image_gen_adapter is not None:
            return self._image_gen_adapter
        return get_image_gen_adapter(
            key_provider=_default_gemini_key_provider,
            org_id=self.org_id,
        )

    # ── Stage 4 (svg): deterministic brand-locked slide render ───────────

    def _resolve_svg_render_adapter(self) -> SvgRenderAdapter:
        if self._svg_render_adapter is not None:
            return self._svg_render_adapter
        # No upload resolver wired in v1 → the rasterized PNG is returned
        # inline as a data: URL (dev fallback, mirrors image_gen). Prod
        # should pass an upload_url_resolver that puts bytes in Supabase
        # Storage and returns the persistent URL.
        return get_svg_render_adapter(real=True)

    def _render_post_svg(
        self,
        post: dict[str, Any],
        *,
        variant: str | None = None,
    ) -> dict[str, Any]:
        """Compose + rasterize deterministic SVG slides for the post.

        For each slide: resolve design tokens (brand kit's ``design_tokens``
        overriding the variant preset) → build the role-specific SVG →
        rasterize via the seed ``svg_render`` adapter → persist ``svg_markup``
        + the PNG (``image_url`` as a ``data:`` URL when no storage resolver
        is wired) + ``image_renderer='svg'``.

        Unlike the raster path there is no credential gate — rasterization
        always works (resvg + bundled fonts), so ``configured`` is always
        ``True``.
        """
        kit = self._load_brand_kit(post["brand_kit_id"])
        if not kit:
            raise GenerationError("brand_kit_not_found")

        tokens = resolve_tokens(kit, variant or post.get("variant") or "premium")

        slides = (
            self.db.table("mc_post_slides")
            .select("*")
            .eq("post_id", post["id"])
            .eq("org_id", self.org_id)
            .order("slide_n")
            .execute()
        )
        slide_rows = slides.data or []
        if not slide_rows:
            raise GenerationError(
                "slides_missing — run generate_storyboard first"
            )

        adapter = self._resolve_svg_render_adapter()
        cta_word = (post.get("cta") or "").split()[0] if post.get("cta") else None

        results: list[dict[str, Any]] = []
        for slide in slide_rows:
            svg_markup = build_slide_svg(
                slide.get("role") or "cover",
                slide,
                tokens,
                cta_word=cta_word,
            )
            rendered = adapter.render(
                SvgRenderInput(
                    svg_markup=svg_markup,
                    width=tokens.canvas_w,
                    height=tokens.canvas_h,
                    request_id=f"{post['id']}:{slide['slide_n']}",
                ),
                org_id=self.org_id,
            )
            image_url = rendered.image_url
            if image_url is None:
                image_url = (
                    "data:image/png;base64,"
                    + base64.b64encode(rendered.png_bytes).decode("ascii")
                )
            (
                self.db.table("mc_post_slides")
                .update(
                    {
                        "svg_markup": svg_markup,
                        "image_url": image_url,
                        "image_renderer": "svg",
                    }
                )
                .eq("post_id", post["id"])
                .eq("org_id", self.org_id)
                .eq("slide_n", slide["slide_n"])
                .execute()
            )
            results.append(
                {
                    "slide_n": slide["slide_n"],
                    "role": slide.get("role"),
                    "image_url": image_url,
                    "renderer": "svg",
                    "svg_len": len(svg_markup),
                    "backend": rendered.backend,
                }
            )

        return {
            "configured": True,
            "renderer": "svg",
            "mode": "svg",
            "variant": tokens.variant,
            "slides": results,
        }

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
        brand_name = (kit.get("name") or "").strip()
        brand_line = (
            f"Brand name (use verbatim in the GalilAI 'Brand:' clause): {brand_name}"
            if brand_name
            else "Brand name: (none — omit the 'Brand:' clause, never emit a placeholder)"
        )
        return f"""# Brand
{brand_line}

# Design system
{kit.get('design_system') or '(empty)'}

# Persona
{kit.get('persona') or '(empty)'}

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

    @staticmethod
    def _compose_score_user_message(
        post: dict[str, Any], slides: list[dict[str, Any]]
    ) -> str:
        storyboard = post.get("storyboard") or {}
        slide_lines = "\n".join(
            f"- [{s.get('role')}] {s.get('headline') or ''}"
            + (f" — {s.get('body')}" if s.get("body") else "")
            for s in slides
        ) or "(no slides persisted)"
        # Reels carry a spoken narration ("roteiro de fala") in the storyboard
        # JSON — include it so the audit grades the recorded script + the
        # textual-vs-verbal-headline rule.
        spoken_lines = "\n".join(
            f"- [{s.get('role')}] {s.get('spoken')}"
            for s in (storyboard.get("slides") or [])
            if s.get("spoken")
        )
        spoken_block = (
            f"\n\n## Roteiro de fala (spoken narration — reels)\n{spoken_lines}"
            if spoken_lines
            else ""
        )
        hashtags = post.get("copy_hashtags") or []
        return f"""# Post to audit

## Format
{post.get('format')}

## Declared methodology (from the storyboard — VERIFY, do not trust)
- Dominant trigger: {storyboard.get('trigger_dominant') or '(none declared)'}
- Embedded triggers: {', '.join(storyboard.get('triggers_embedded') or []) or '(none)'}
- Templates: {', '.join(storyboard.get('templates') or []) or '(none)'}
- Arc: {storyboard.get('arc_pattern') or '(none)'}

## Slides (role → headline — body)
{slide_lines}{spoken_block}

## Caption
{post.get('copy_caption') or '(not generated yet)'}

## Hashtags
{' '.join(hashtags) if hashtags else '(none)'}

## First comment
{post.get('copy_first_comment') or '(none)'}

Grade all 8 criteria and output the JSON verdict object now."""

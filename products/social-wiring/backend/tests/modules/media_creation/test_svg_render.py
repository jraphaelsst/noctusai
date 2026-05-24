"""SVG render mode — design tokens, slide builders, and the render path.

The SVG mode (``projects/media-svg-render-mode``) renders deterministic
brand-locked slides via the seed ``svg_render`` primitive, alongside the
existing raster (image-gen) mode.

Layers tested:
- ``TestDesignTokens`` — preset + per-brand ``design_tokens`` override (no IO).
- ``TestSvgBuilders`` — each role emits valid, injection-safe SVG (no IO).
- ``TestSvgRenderModeService`` — service path with an injected
  ``FakeSvgRenderAdapter`` (DI seam; no rasterizer needed).
- ``TestSvgRenderModeHttp`` — full endpoint path with real resvg.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.svg_render import (
    FakeSvgRenderAdapter,
    resvg_available,
)

from app.modules.media_creation.design import (
    DesignTokens,
    build_slide_svg,
    preset_for,
    resolve_tokens,
)
from app.modules.media_creation.design.svg_slides import ROLES
from app.modules.media_creation.services.generation_service import GenerationService


# ── Design tokens ───────────────────────────────────────────────────────


class TestDesignTokens:
    def test_preset_premium_and_educational_differ(self):
        assert preset_for("premium").bg_primary != preset_for("educational").bg_primary

    def test_unknown_variant_falls_back_to_premium(self):
        assert preset_for("nonsense").variant == "premium"
        assert preset_for(None).variant == "premium"

    def test_resolve_no_override_returns_preset(self):
        tokens = resolve_tokens({"design_tokens": None}, "premium")
        assert tokens.accent_gold == preset_for("premium").accent_gold

    def test_resolve_brand_override_is_shallow_merged(self):
        kit = {"design_tokens": {"accent_gold": "#FF0000", "handle": "@wilson"}}
        tokens = resolve_tokens(kit, "premium")
        assert tokens.accent_gold == "#FF0000"   # overridden
        assert tokens.handle == "@wilson"        # overridden
        assert tokens.bg_primary == preset_for("premium").bg_primary  # inherited

    def test_resolve_variant_follows_request_not_stale_token(self):
        kit = {"design_tokens": {"variant": "premium"}}
        tokens = resolve_tokens(kit, "educational")
        assert tokens.variant == "educational"


# ── SVG slide builders ──────────────────────────────────────────────────


class TestSvgBuilders:
    TOKENS = DesignTokens(handle="@brand", location_pin="GRANJA VIANA")

    @pytest.mark.parametrize("role", ROLES)
    def test_every_role_emits_valid_svg(self, role):
        slide = {"slide_n": 1, "role": role, "headline": "Hook here", "body": "One. Two. Three."}
        svg = build_slide_svg(role, slide, self.TOKENS, cta_word="VALORIZAÇÃO")
        assert svg.startswith("<svg")
        assert svg.rstrip().endswith("</svg>")
        assert f"viewBox=\"0 0 {self.TOKENS.canvas_w} {self.TOKENS.canvas_h}\"" in svg
        assert "@brand" in svg  # handle drawn on every slide

    def test_unknown_role_defaults_to_cover(self):
        slide = {"slide_n": 1, "role": "weird", "headline": "X", "body": ""}
        svg = build_slide_svg("weird", slide, self.TOKENS)
        assert "COVER" in svg

    def test_user_text_is_xml_escaped(self):
        slide = {"slide_n": 1, "role": "cover", "headline": "A & B <script>", "body": ""}
        svg = build_slide_svg("cover", slide, self.TOKENS)
        assert "A &amp; B &lt;script&gt;" in svg
        assert "<script>" not in svg  # no raw injection

    def test_cta_word_renders_in_pill(self):
        slide = {"slide_n": 5, "role": "cta", "headline": "Last", "body": "DM"}
        svg = build_slide_svg("cta", slide, self.TOKENS, cta_word="valorização")
        assert "VALORIZAÇÃO" in svg  # uppercased action word

    def test_fonts_match_bundled_families_no_google_import(self):
        slide = {"slide_n": 1, "role": "cover", "headline": "X", "body": "y"}
        svg = build_slide_svg("cover", slide, self.TOKENS)
        assert "Cormorant Garamond" in svg
        assert "Inter" in svg
        assert "fonts.googleapis.com" not in svg  # no server-unreachable @import


# ── Service render path (DI seam, no rasterizer) ────────────────────────


class TestSvgRenderModeService:
    def _svc_with_seeded_slides(self):
        from noctusai_lib.testing import MockSupabaseClient

        sb = MockSupabaseClient()
        sb.from_("mc_brand_kits").insert(
            {
                "id": "kit-1",
                "org_id": "org-1",
                "name": "Granja Premium",
                "persona": "editorial",
                "design_system": "premium",
                "design_tokens": {"handle": "@wilson", "accent_gold": "#C5A55E"},
                "default_lang": "pt-BR",
            }
        ).execute()
        sb.from_("mc_post_slides").insert(
            [
                {"id": "s1", "org_id": "org-1", "post_id": "p1", "slide_n": 1,
                 "role": "cover", "headline": "3 condomínios", "body": "Sub"},
                {"id": "s2", "org_id": "org-1", "post_id": "p1", "slide_n": 2,
                 "role": "cta", "headline": "Fale conosco", "body": "DM"},
            ]
        ).execute()
        fake = FakeSvgRenderAdapter(upload_url_resolver=lambda png, req: "url")
        svc = GenerationService(sb, "org-1", svg_render_adapter=fake)
        post = {"id": "p1", "brand_kit_id": "kit-1", "variant": "premium",
                "cta": "VALORIZAÇÃO agora", "format": "carousel"}
        return svc, sb, fake, post

    def test_svg_mode_persists_markup_and_renderer(self):
        svc, sb, fake, post = self._svc_with_seeded_slides()
        result = svc.render_post(post, mode="svg")
        assert result["mode"] == "svg"
        assert result["configured"] is True
        assert result["variant"] == "premium"
        assert len(result["slides"]) == 2
        # adapter invoked once per slide
        assert len(fake.calls) == 2
        # persisted: svg_markup + image_renderer='svg'
        rows = sb.from_("mc_post_slides").select("*").eq("post_id", "p1").order("slide_n").execute()
        for row in rows.data:
            assert row["image_renderer"] == "svg"
            assert row["svg_markup"].startswith("<svg")
            assert "@wilson" in row["svg_markup"]  # brand design_tokens applied

    def test_svg_mode_404s_on_missing_brand_kit(self):
        from noctusai_lib.testing import MockSupabaseClient
        from app.modules.media_creation.services.generation_service import GenerationError

        sb = MockSupabaseClient()
        svc = GenerationService(sb, "org-1", svg_render_adapter=FakeSvgRenderAdapter())
        with pytest.raises(GenerationError, match="brand_kit_not_found"):
            svc.render_post({"id": "p1", "brand_kit_id": "ghost"}, mode="svg")


# ── Full endpoint path (real resvg) ─────────────────────────────────────


@pytest.mark.skipif(not resvg_available(), reason="resvg-py not installed")
class TestSvgRenderModeHttp:
    def _seed(self, client, kit_id):
        client.mock_supabase.from_("mc_posts").insert(
            {"id": "post-1", "org_id": "test-org-123", "brand_kit_id": kit_id,
             "title": "X", "idea": "Y", "format": "carousel", "variant": "premium",
             "slide_count": 2, "cta": "VALORIZAÇÃO agora", "status": "draft"}
        ).execute()
        client.mock_supabase.from_("mc_post_slides").insert(
            [
                {"id": "slide-1", "org_id": "test-org-123", "post_id": "post-1",
                 "slide_n": 1, "role": "cover", "headline": "3 condomínios", "body": "Sub"},
                {"id": "slide-2", "org_id": "test-org-123", "post_id": "post-1",
                 "slide_n": 2, "role": "cta", "headline": "Fale", "body": "DM"},
            ]
        ).execute()

    def test_render_svg_mode_end_to_end(self, client, seeded_kit):
        self._seed(client, seeded_kit)
        resp = client.post("/api/media-creation/posts/post-1/render", json={"mode": "svg"})
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["mode"] == "svg"
        assert body["configured"] is True
        assert len(body["slides"]) == 2
        for slide in body["slides"]:
            assert slide["renderer"] == "svg"
            assert slide["backend"] == "resvg"
            assert slide["image_url"].startswith("data:image/png;base64,")

    def test_render_svg_persists_markup_and_renderer(self, client, seeded_kit):
        self._seed(client, seeded_kit)
        client.post("/api/media-creation/posts/post-1/render", json={"mode": "svg"})
        slides = (
            client.mock_supabase.from_("mc_post_slides")
            .select("*").eq("post_id", "post-1").order("slide_n").execute()
        )
        for slide in slides.data:
            assert slide["image_renderer"] == "svg"
            assert slide["svg_markup"].startswith("<svg")

    def test_raster_mode_still_default(self, client, seeded_kit):
        """Default (no mode) → raster path, Fake image-gen fires (configured False)."""
        self._seed(client, seeded_kit)
        # raster path needs prompts; with none it skips — assert it took the
        # raster branch (renderer nano_banana, not svg).
        resp = client.post("/api/media-creation/posts/post-1/render")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["renderer"] == "nano_banana"
        assert body.get("mode") != "svg"

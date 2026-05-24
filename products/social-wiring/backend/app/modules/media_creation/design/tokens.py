"""Structured design tokens for the SVG render mode.

The deterministic SVG slide engine needs STRUCTURED tokens (palette hex,
type scale, brand handle) — but ``mc_brand_kits.design_system`` is a free
prose blob (the LLM pipeline reads it as context). This module bridges
that: it ships two **generic** structural presets (premium / educational)
and lets a brand kit override them with ``design_tokens`` (JSONB) as DATA.

The presets are deliberately generic ("premium dark + gold", "educational
light + navy" idioms) — a *specific* brand's exact palette lives per-org
in ``mc_brand_kits.design_tokens``, never baked into platform code.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DesignTokens(BaseModel):
    """Resolved visual tokens consumed by the SVG slide builders.

    Hex values are validated only loosely (any string) — they flow into
    SVG ``fill``/``stop-color`` attributes, which are autoescaped by the
    slide builder. Brand-supplied overrides are merged over a preset.
    """

    model_config = ConfigDict(extra="ignore")

    variant: str = "premium"

    # Canvas (Instagram carousel 4:5, locked skeleton)
    canvas_w: int = 1080
    canvas_h: int = 1350
    margin: int = 96

    # Palette
    bg_primary: str = "#1F1D1A"
    bg_deep: str = "#141210"
    accent_gold: str = "#B8924E"
    accent_gold_bright: str = "#D4B36A"
    text_primary: str = "#F4F1EC"
    text_muted: str = "#A79C88"
    divider: str = "#352F26"

    # Typography (families MUST match seed svg_render bundled faces)
    serif_family: str = "Cormorant Garamond"
    sans_family: str = "Inter"

    # Brand marks (optional, per-post/per-brand)
    handle: str = ""
    location_pin: str = ""


# Generic premium preset — dark, warm, gold-accented "high-end" idiom.
PREMIUM_TOKENS = DesignTokens(variant="premium")

# Generic educational preset — light lavender / navy / yellow "didactic" idiom.
EDUCATIONAL_TOKENS = DesignTokens(
    variant="educational",
    bg_primary="#E8E5F0",
    bg_deep="#3A4FB8",
    accent_gold="#3A4FB8",
    accent_gold_bright="#F0E63A",
    text_primary="#3A4FB8",
    text_muted="#5A6BC0",
    divider="#C7CBE8",
)

_PRESETS: dict[str, DesignTokens] = {
    "premium": PREMIUM_TOKENS,
    "educational": EDUCATIONAL_TOKENS,
}


def preset_for(variant: str | None) -> DesignTokens:
    """Return the structural preset for ``variant`` (premium default)."""
    return _PRESETS.get((variant or "premium").lower(), PREMIUM_TOKENS)


def resolve_tokens(brand_kit: dict | None, variant: str | None) -> DesignTokens:
    """Resolve the tokens for a render: preset(variant) overridden by the
    brand kit's ``design_tokens`` JSONB (when present).

    The brand kit override is shallow-merged over the preset — a kit may
    set only ``accent_gold`` + ``handle`` and inherit everything else.
    Unknown keys in ``design_tokens`` are ignored (``extra="ignore"``).
    """
    base = preset_for(variant)
    overrides = (brand_kit or {}).get("design_tokens") or {}
    if not isinstance(overrides, dict) or not overrides:
        return base
    merged = {**base.model_dump(), **overrides}
    # variant always follows the requested variant, not a stale token value
    merged["variant"] = base.variant
    return DesignTokens(**merged)

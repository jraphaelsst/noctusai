"""SVG render-mode design layer for media_creation.

The in-home design system for deterministic brand-locked slides:

- :mod:`tokens` — :class:`DesignTokens` + generic premium/educational
  presets + ``resolve_tokens(brand_kit, variant)`` (per-brand override
  via the ``mc_brand_kits.design_tokens`` JSONB column).
- :mod:`svg_slides` — deterministic per-role SVG builders (cover /
  develop / insight / cta), consumed by the SVG render mode and
  rasterized via the seed ``noctusai_lib.integrations.svg_render``
  primitive.
"""

from __future__ import annotations

from app.modules.media_creation.design.svg_slides import (
    ROLES,
    build_slide_svg,
)
from app.modules.media_creation.design.tokens import (
    DesignTokens,
    EDUCATIONAL_TOKENS,
    PREMIUM_TOKENS,
    preset_for,
    resolve_tokens,
)

__all__ = [
    "DesignTokens",
    "EDUCATIONAL_TOKENS",
    "PREMIUM_TOKENS",
    "ROLES",
    "build_slide_svg",
    "preset_for",
    "resolve_tokens",
]

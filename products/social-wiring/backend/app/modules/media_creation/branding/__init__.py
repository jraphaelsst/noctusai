"""Branding system — version-controlled brand catalog → DB.

Agency model: one org manages many real-estate **agents** (brand owners,
`mc_brand_owners`); each agent has 1+ **brandings** (`mc_brand_kits`), each
with structured `design_tokens` the SVG render mode consumes
(`KB § PATTERNS/svg-render-mode.md`).

The catalog (`catalog/<owner>/brand.json` + assets) is the source of
truth; `seed_catalog` upserts it idempotently into one org.
"""

from __future__ import annotations

from app.modules.media_creation.branding.loader import (
    CATALOG_DIR,
    BrandingDef,
    BrandOwnerDef,
    ReferenceDef,
    load_catalog,
    load_owner,
    seed_catalog,
)

__all__ = [
    "CATALOG_DIR",
    "BrandOwnerDef",
    "BrandingDef",
    "ReferenceDef",
    "load_catalog",
    "load_owner",
    "seed_catalog",
]

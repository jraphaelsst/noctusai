# PROJECT — social-wiring-branding-catalog

**Status:** ⏳ in-flight · **Branch:** `social-wiring-branding-catalog` (off `dev`) · **Started:** 2026-05-24

## §1 Context
Follow-on to `media-svg-render-mode`. The user reversed the earlier "leave Wilson as my data" call: Wilson's brand becomes the **first entry in a real multi-brand branding system** in noc. User decisions:
- **Agency model** — ONE tenant org manages many real-estate **agents** as clients; each agent has 1+ **brandings**. ⇒ new `mc_brand_owners` (agent/client) layer above `mc_brand_kits`.
- **Repo brand catalog → seeds DB** — brands are version-controlled definition files; a seed step loads them into `mc_brand_owners`/`mc_brand_kits`/`mc_brand_references`.
- Wilson demonstrates "more than 1 branding per agent" — premium + educational brandings under one owner.

## §2 Goal
A version-controlled branding catalog + an agent (`brand_owner`) layer, seeded into the DB per org; Wilson ported in as the first agent (2 brandings + references). The SVG render mode already consumes `mc_brand_kits.design_tokens`.

## §3a Seed-first analysis
- `mc_brand_owners` + catalog/loader are **social-wiring/media_creation domain** (only consumer = media-creation); N=1 ⇒ stays in the product. [A] accept-at-N=1; seed-convergence destination if a 2nd product needs a brand-owner layer.
- design_tokens shape already lands on the seed `DesignTokens` model (svg-render-mode). No new seed primitive needed.
- Per-product count for the cross-cutting concern (rendering) = 0 (already seed).

## §4 Phases
- **P1 (schema)** — `003_brand_owners.sql`: `mc_brand_owners` (agent layer, org-scoped RLS) + `mc_brand_kits.brand_owner_id` FK + `mc_brand_kits.slug` (catalog idempotency). Forward, idempotent.
- **P2 (catalog + loader)** — `branding/catalog/wilson/` (brand.json: owner + premium+educational brandings w/ design_tokens from DESIGN-SYSTEM.md + persona + references + design-system.md doc + reference assets) + `branding/loader.py` (pure parse + idempotent seed) + tests.
- **P3 (API + integrate)** — `routers/branding.py` (list owners/brandings + admin seed-catalog into caller's org) + `brand_owner_service` + register + tests · docs/3-way-sync · verify · commit/merge/push.

## §5 Gates
- Wave: P2 gated on P1 schema; P3 gated on P1∧P2.
- Idempotent seed (re-runnable, slug-keyed) — no dupes on re-seed.
- No push without explicit user go.

## §11 Learnings → `findings.md`

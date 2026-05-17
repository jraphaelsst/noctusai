# promotion-manifest-parser-blocklist — Project Document

> Living document. Filed 2026-05-16 as the **named destination** for the canonical `parse_manifest` YAML block-list gap surfaced during the social-wiring absorption Wave 5.2 (promotion-map automation). Self-contained — no dependency on the originating project folder surviving.

- **Created:** 2026-05-16
- **Status:** Filed / not started — **gated** on the prerequisite below
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `promotion-manifest-parser-blocklist` (cross-cutting tooling → `projects/promotion-manifest-parser-blocklist/`)

## 1. Context & Purpose

The canonical promotion-manifest parser `parse_manifest` (`mcp/noctusai/tools/noctus/dev/promotion.py`) does NOT parse the YAML **block-list** form of `origin:` / `intended_noc_destination:` keys (only the inline-scalar form). A seed-workspace's `.promotions/*.md` manifest authored with block-list values renders an **empty destination** — observed 2026-05-16 on ~5 of 14 real manifests during the promotion-map auto-derive work.

This is a **fix-at-root** because there are **N≥2 consumers** of `parse_manifest`: (1) `scripts/gen-promotions-index.py` (the auto-derived `PROMOTIONS.md` index), (2) the `list_promotions` MCP tool, (3) `promote_from_seed_workspace`. Patching the generator alone would be a quick-fix at the wrong level — the parser is the single point.

## 2. Prerequisites / gate

- None external. The gate is sequencing only: the generator + MCP tools must be re-run + re-baselined against the fixed parser in the same change (doc-code-coherence — `gen-promotions-index.py --check` drift gate, `list_promotions` output, `promote_from_seed_workspace` round-trip).

## 3. Scope

- Extend `parse_manifest` to accept the YAML block-list form of `origin:` / `intended_noc_destination:` (and any other multi-value manifest key) in addition to the inline-scalar form; preserve backward compatibility with existing inline manifests.
- Add parser regression tests covering both forms (block-list + inline) per regression-test-the-detector discipline.
- Re-run `scripts/gen-promotions-index.py` + verify the ~5 previously-empty destinations now render; re-baseline the seed-workspace pre-commit Rule-3 drift gate.

## 4. Success criteria

All 14-style manifests render a non-empty destination; the 3 consumers agree; parser tests pin both manifest forms.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the fix-at-root destination for the `parse_manifest` block-list gap surfaced by the promotion-map auto-derive work (N≥2 consumers → not a generator-local patch). | Claude Opus 4.7 |

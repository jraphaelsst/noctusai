# Absorption tracking — the 9th keeper-mirror cache

> **Absorption *state* is a derived ledger, never a hand-maintained index.** Absorptions are a recurring multi-session event (N≥2: `social-wiring` 2026-05-16 · `orbity` 2026-06-02). Tracking which capabilities have been uplifted, to which seed organ, validated on which pilot, and de-referenced into native docs — by **hand-editing a KB INDEX row** — is exactly the drift the absorb guide's own Gate 2 forbids (*"derive any index from the manifest dir; never hand-maintain a parallel count"*). So absorption state is an **event-shaped ndjson ledger → derived sqlite cache**, the 9th keeper-mirror, on the same 3-leg mirror contract as the other eight. Born 2026-06-02 (orbity absorption; user-flagged).

## The three legs (mirror contract — `KB § PATTERNS/common/keeper-pattern-cache.md`)

1. **Source of truth — `project-history/absorptions.ndjson`** (append-only, `*.ndjson merge=union`). Event-shaped, one JSON/line, two kinds:
   - **lifecycle**: `{ts, slug, kind:"lifecycle", source_repo, source_head, stage, note}` — `stage ∈ cloned → diagnosed → uplifting → porting → teardown → done`.
   - **capability**: `{ts, slug, kind:"capability", capability, target_organ, status, pilot, note}` — `status ∈ identified → building → pilot → fleet → native_doc → de_referenced`.
2. **Derived cache — `<git-common-dir>/noctusai/cache/absorptions.sqlite`** (Tier-1, resolved via `cache_backend.cache_path("absorptions")`, WAL + busy_timeout). Tables `absorptions(slug PK …)` + `capabilities(slug,capability PK …)` + `meta(source_sha)`. **Derivation = latest-event-wins** per slug / per (slug,capability) — a pure idempotent function of the ndjson.
3. **Keeper — `check_absorptions_cache_freshness`** (severity `warning`, advisory) — compares cached `meta.source_sha` vs live ndjson sha; composed into `check_all_cache_freshness` + the top-level checker + `_KEEPER_REGISTRY`.

## Auto-refresh — structural tier (zero-OpenAI)

`absorptions` is a **structural** cache (no embeddings) → registered in `_STRUCTURAL_CACHES` + `settle_structural_caches` → **refreshes pre-commit AND self-heals on the freshness check** (`KB § PATTERNS/common/cache-auto-freshness.md`). No push-time cost; advisory keeper never blocks. The eager `refresh()` after each `absorption_log` append keeps the local cache in sync immediately.

## MCP surface (`noctus.dev.absorption_*`)

- `absorption_log` — append a lifecycle or capability event (enum-validated; refuses unknown stage/status — no silent error), then eager-refresh the cache.
- `absorption_status` — derived state: every absorption's lifecycle stage + its capabilities' uplift statuses (lazy-rebuild if stale).
- `absorption_query` — filter by slug / stage / status.
- `absorption_refresh` — force a rebuild.

## Why it matters

The per-capability `status` chain **is the live uplift + de-reference ledger** of an absorption: as each organ is built (`identified → building`), proven on its pilot (`→ pilot → fleet`), and landed natively (`→ native_doc → de_referenced`), the row advances — so "where is this absorption?" is a query, never a stale hand-kept doc. At source-archival the `de_referenced` capabilities confirm the transient source-bridge (`KB § ABSORPTIONS/<source>/`) can be removed (`absorb-seed-workspace.md` Refinement 5).

## Composes

`keeper-pattern-cache` (3-leg contract) · `cache-portable-architecture` (Tier-1 path) · `cache-auto-freshness` + `cache-locking-discipline` · `branch-tree-tracking` + `roadmap-tracking` (sibling tracking systems — ndjson is event-shaped, roadmap markdown holds mutable slice prose) · `GUIDES/absorb-seed-workspace.md` (the procedure this tracks) · `mcp-first-scripts` (every automation is an agent-exposable tool).

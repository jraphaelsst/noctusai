# Seed absorption — methodology + tools

> Removing duplicated content from products by lifting it into the seed framework. Diagnostic tools at `noctus.seed.*`; the absorption loop is **scan → evaluate → self-audit → absorb → re-scan → build-verify**. The methodology is the operational arm of the platform DRY recurrence rule (`KB § PATTERNS/architect/project-execution.md § 2.7`).

## When to absorb

Absorption is triggered by the **DRY recurrence rule** — once a content shape repeats across products, the cost of leaving it scattered exceeds the cost of lifting it.

- **N=2 → triage time.** Inspect the two instances, decide one of three outcomes (per the universal rule):
  - **formalize** — lift to seed now (default if instances are byte-identical or near-identical).
  - **refactor** — align both to a shared shape, then formalize.
  - **accept-with-rationale** — catalog in `KB § PATTERNS/common/accept-with-rationale.md` if absorption cost > marginal duplication cost (e.g. trivial files of ≤5 lines that genuinely vary per product).
- **N=3+ → MUST formalize.** Silently shipping the 4th instance is forbidden. Minimum response when blocked: file a follow-up `seed-absorb-<short-name>` project, do not silently absorb seed-build into consumer scope.
- **Trivial files (≤5 lines)**: absorption complexity may exceed marginal gain — accept-with-rationale is OK, but the entry must name the tipping point ("when this grows past N=4 or 10 lines, lift").

The absorption-search standing duty (`KB § 06-AGENTS.md § Absorption-search sextet`) keeps the recurrence signal hot — every time you touch a product's services / routers / hooks / components, run the relevant scan modes before walking away.

## The MCP tools (`noctus.seed.*`)

All seven tools live under the `noctus.seed.*` namespace and are exposed through the noctusai MCP server. They share a common `_filewalk` helper at `mcp/noctusai/tools/noctus/seed/_filewalk.py` — touch the skip lists in **both** `scan_repetition` and `audit_drift` if you change them (silent drift between the two scans is a known footgun).

### `noctus.seed.scan_repetition`

Walks `products/*/` for files duplicated across N≥2 products at the same relative path. Per group, classifies each candidate as one of:

- **`byte_identical`** — every product's copy is character-for-character the same. Lowest-friction absorption: move to seed + delete consumer copies, or move to seed + add re-export shims if direct deletion would break imports.
- **`near_identical`** — files share ≥0.95 similarity (line-based ratio). Indicates a shared backbone with small per-product variance — usually a candidate for the **factory** strategy (3 below) or **template + runtime substitution** (4 below).
- **`divergent`** — same path, different bodies. Either a false positive (truly per-product content), an absorption that already started but didn't finish, or a candidate that needs structural refactor before absorption.

Output schema (per group): `{rel_path, occurrences, products, classification, similarity, suggested_destination}`. The `suggested_destination` is a heuristic — *always* validate by running `list_capabilities` (next tool) before committing to a placement.

### `noctus.seed.list_capabilities`

Enumerates public exports from `noctusai_seed.*` (the framework backend + frontend factories) and `noctusai_lib.*` (the 6-layer library — `primitives` / `config` / `testing` / `integrations` / `domain` / `api`). Use **before** inventing a new helper to confirm the seed doesn't already ship it.

This is the self-audit step in the loop — skipping it is how N=4-as-third-instance-of-N=3-already-absorbed slips happen. The output groups exports by module so you can scan for both *exact* and *near-name* matches (e.g. you're about to add `format_brl_currency`, the catalog already has `noctusai_lib.primitives.formatting.format_currency` accepting a `locale=`).

### `noctus.seed.audit_drift`

For each file in `templates/product-seed/` (the canonical product-template tree), diffs each product's copy against the canonical and reports per-pair status: `identical` / `small_drift` (≤20 lines) / `large_drift` / `missing`. Surfaces re-sync candidates — a product whose copy of a templated file has drifted is either:

- **legitimately drifted** (per-product content was added; doesn't belong in the template) → factor the drift into a named seam, push the unchanged backbone back into the template,
- **silently divergent** (someone hot-fixed the consumer instead of the template) → re-sync the consumer, file the hot-fix's intent into a project for proper template-side absorption.

`audit_drift` complements `scan_repetition`: scan finds *new* absorption candidates from product-side N≥2 patterns; audit finds *regression* against the existing canonical template tree.

### `noctus.seed.absorb_file`

Mutation companion to `scan_repetition`. Lifts a duplicated file from products into the seed framework, deletes duplicate copies, and (optionally) rewrites product-side imports. Codifies **Strategy 2 — move + re-export** (most common absorption shape, validated in rounds A-D for textarea + 19 shadcn UI components + 3 trivial frontend configs).

**Safety contract** — refuses (loudly, no on-disk change) when:
- The source product's copy doesn't exist.
- Other products' copies aren't byte-identical to the source (would silently destroy diverged content).
- The seed destination already exists with different content (would silently overwrite).

**Idempotent** — running twice on an already-absorbed file is a no-op. Running with a partially-completed prior absorption (seed has the file, some products still have copies) finishes the job.

**Pair with `audit_drift` after** — absorb_file moves the file but doesn't update the template at `templates/product-seed/`. Run `audit_drift` post-absorption to surface the template push-forward gap; update the template canonical to match the absorbed shape (re-export shim or factory call) so future scaffolds inherit it.

### `noctus.seed.specify_capability`

Pure-data planner — for the inverse direction. When the architect is about to ADD a new capability to the seed (factory, primitive, integration), this picks the right layer of the 6-layer `noctusai_lib` layout based on flags (`needs_io`, `framework_hook`, `pure_logic`, `test_only`) and returns:
- Suggested layer + reason.
- Canonical shape requirements — for `integrations`, that's the Protocol+Fake+Real+factory contract from `KB § PATTERNS/backend/seed-fake-real-adapter.md`. For `api`, it's the deferred-config dep-factory pattern. For `primitives`, it's the no-IO discipline.
- Checklist whose first step is "run `list_capabilities` first" — the cross-check that prevents reinventing existing helpers.
- Import-path template + reference examples for the chosen layer.

### `noctus.seed.report`

Rollup that cross-references `scan_repetition` + `audit_drift` into a single prioritized triage queue. The composition unlocks leverage that neither tool surfaces alone — a file that is BOTH duplicated byte-identical across N≥3 products AND drifts vs the canonical template gives one absorption move that closes both gaps (lift to seed, push the template forward to match the absorbed shape).

Priority bands, highest-leverage first:

- **P0** — byte_identical N≥3 AND template ships file AND ≥1 product drifts. One move resolves duplication + template convergence.
- **P1** — byte_identical N≥3, template-status irrelevant. Recurrence rule MUST formalize.
- **P2** — byte_identical N=2. Recurrence-rule triage time (formalize / refactor / accept-with-rationale).
- **P3** — near_identical N≥2. Reconcile per-product variance, THEN absorb.
- **P4** — template ships file but ≥1 product is missing it. Push the missing product to inherit (no scan signal because no duplication exists yet).
- **P5** — divergent / large_drift. Likely intentional — review and catalog if so.

Output schema: `{scanned_products, items: [{priority, rel_path, rationale, suggested_action, suggested_destination, in_template, scan_classification, scan_occurrences, drift_status_per_product}], summary: {Pn_count, total_items, skipped_no_action, ...}, upstream: {scan_summary, audit_summary}}`. Items sorted by priority asc, then occurrence-count desc, then path. `max_items` caps the list; summary always reflects the pre-cap result.

Read-only; composes the two upstream tools without re-implementing either.

### `noctus.hound.scan` — the trio orchestrator

The keeper enforces compliance contracts (regulatory). The **hound** sniffs out cleanup candidates across the absorption + fusion + optimization trio and aggregates their findings into a single prioritized queue (curatorial). One call instead of three.

Each scope's full result is preserved verbatim under `scopes.<name>`; aggregated counts + LoC-savings + files-absorbable estimates land in `unified`; a plain-text `next_action` picks the highest-leverage scope to attack first using this priority ladder:

1. **Absorption P0** (byte_identical N≥3 + template drifts) — one move closes both gaps.
2. **Optimization high-severity** (confirmed dead code) — safe to delete.
3. **Absorption P1** (byte_identical N≥3) — recurrence rule MUST formalize.
4. **Fusion subsume** (same-file or strong-overlap pairs) — collapse via mode/kind.
5. **Optimization warning-severity** (small single-call helpers + wrappers).
6. Otherwise — codebase clean enough that no single scope dominates.

Per-scope params forward through (`absorption_min_products`, `fusion_min_score`, `fusion_scope`, `optimization_min_severity`, `max_per_scope`). Soft-fails per scope (errors[] populated, non-failed scopes still complete). Read-only.

Lives at `mcp/noctusai/tools/noctus/hound/`. Parallels `noctus.seed.*` / `noctus.dev.*` / `noctus.team.*` as a sub-umbrella.

**Structural-duplicate filter (2026-05-10).** `scan_repetition` skips empty-marker files (Python `__init__.py`, `.gitkeep`, empty configs) and already-absorbed re-export shims (`@import "@noctusai/seed/..."`, `import { X } from "../../seed/..."` followed by `export default X`, etc.) by default. The detector flags ANY content-bearing file ≤5 operative lines that mentions `seed/` / `@noctusai/seed` / `noctusai_seed` / `noctusai_lib` as a shim (the absorbed state, not a duplication candidate). Pass `skip_structural_duplicates=False` to disable. On the live tree this dropped P1 absorption candidates from 11 → 0 (all 11 had been false positives — empty package markers + already-absorbed config shims).

### `noctus.seed.scan_optimizations`

Third leg of the **absorption + fusion + optimization** trio. Operates at **intra-file scope** — opportunities to delete, inline, or collapse code WITHIN a single source file (complements absorption's cross-product file-level scope and fusion's cross-tool function-level scope).

Six detectors:

- **`dead_function`** — module-level def with zero references in-file AND zero references in any sibling module. Cross-file false positives are filtered via a tree-wide reference pre-pass that collects every `Name` / `Attribute` / `ImportFrom` alias across every scanned `.py` (so `walk_files` in `_filewalk.py` is correctly recognized as live when sibling modules import it). Action: delete after grep verification.
- **`single_call_helper`** — private `_*` function called from exactly one place AND ≤ 25 LoC. Above 25 LoC, named helpers carry cognitive value even with one caller; under 3 LoC, savings are negligible. Severity: `warning` for ≤10 LoC (definitely inline), `info` for 11–25 LoC (judgment call). Realistic per-inline savings: ~3 LoC (def line + signature + return), NOT the full body.
- **`wrapper_only`** — function whose entire body is `return inner(*params)` without arg transformation. The function adds zero value; rename callers to use `inner` directly.
- **`verbose_tool_description`** — `@server.tool(description=...)` exceeding 240 chars. Agents pay this cost on every schema load.
- **`oversized_shim_docstring`** — FastMCP shim with a docstring > 2 lines. The impl function's docstring is the authoritative one; shim docstrings are duplication.
- **`lone_constant`** — UPPER_SNAKE module-level constant referenced from exactly one place. Inline at the call site.

`min_severity` (default `info`) caps the queue: `high` keeps only highest-confidence; `warning` drops info-level judgment calls. Live-tree run on the `mcp/noctusai/tools/noctus` tree (51 files): **147 LoC of warning+ opportunities** (1 dead function + 46 small single-call helpers + 2 wrappers); **539 LoC including info-level** (lone constants + verbose descriptions + judgment-call helpers).

The trio's distinct scopes:

| System | Scope | Detects |
|---|---|---|
| **Absorption** (`scan_repetition` / `audit_drift` / `report`) | Cross-product (file-level) | Files duplicated across products → lift to seed |
| **Fusion** (`scan_fusions`) | Cross-tool (function-level) | Tool pairs that should collapse via mode/kind switch |
| **Optimization** (`scan_optimizations`) | Intra-file (line-level) | Dead code / single-use helpers / wrappers / verbose surfaces |

### `noctus.seed.scan_fusions`

Meta-detector for **MCP-tool fusion opportunities** — pairs of tools where a unifying rollup tool would unlock leverage (the same shape that motivated `report` itself). Static analysis of every tool registered under `mcp/noctusai/tools/noctus/**/*.py`; no runtime invocation.

Four signals scored per pair:

- **Same-namespace prefix** (`noctus.dev.*` vs `noctus.team.*` etc.) — fixed bonus; cross-namespace fusions are rare.
- **Param-overlap** (Jaccard of input parameter names) — high overlap means callers feed the same arguments.
- **Return-key overlap** — Jaccard + saturation curve over absolute count of shared top-level dict keys parsed from each tool's docstring `Returns:` block. ≥3 shared keys = strong signal regardless of breadth (the canonical shape: both keyed by `slug` / `rel_path` / `phase_id`).
- **Description-noun overlap** — count of shared content nouns in `description=` blurbs (stopwords filtered).

Two **existing-fusion filters** keep the queue clean:
1. **Direct-import filter** — pair (A, B) where A's source imports B's module (or vice versa) is an existing rollup, not an opportunity.
2. **Transitive filter** — pair (A, B) where some third tool C imports BOTH is also an existing fusion (C is the rollup; the pair is its components). Keeps `scan_repetition + audit_drift` out of the queue once `report` ships.

Heuristic verb-form mutation detector marks each tool read-only or mutation. Word-boundary regex against verb forms (`absorbs`, `moves`, `deletes`, …) — bare nouns (`absorption`, `modification`) don't trip it. `require_both_read_only=True` (default) filters mixed pairs.

Output schema: `{scanned_files, tools_indexed, pairs: [{tool_a, tool_b, score, signals: {same_namespace, param_overlap, param_intersection, return_keys_jaccard, return_keys_count, return_keys_intersection, description_nouns_intersection, both_read_only}, rationale, suggested_rollup_name}], summary: {pairs_above_threshold, pairs_returned, existing_fusions_skipped, score_distribution}}`. Pairs sorted by score desc.

Use when asking: *"what rollup tool should I build next?"* — the same role `scan_repetition` plays for *"what file should I absorb next?"*.

Together the eight tools form the absorption + extension + meta-tooling + optimization feedback loop:
- `scan_repetition` — finds duplicates that should be lifted.
- `list_capabilities` — confirms existing helpers before lifting / inventing.
- `audit_drift` — finds product↔template divergence post-absorption.
- `absorb_file` — executes the lift (Strategy 2).
- `specify_capability` — plans the deliberate addition.
- `report` — combines scan + audit into a single prioritized triage queue.
- `scan_fusions` — surfaces fusion opportunities at the tool layer (which composites should I build next?).
- `scan_optimizations` — surfaces intra-file dead code / single-use helpers / wrappers / verbose surfaces (what can I delete or inline within this file?).

**Placeholder-noise filter (default-on, 2026-05-10).** The first drift-audit run (Gamma's 2026-05-10 report) surfaced that placeholder-substitution noise dominated the small-drift findings — every product's `{{PRODUCT_NAME}}` → `<actual name>` substitution counted as drift, drowning the real signal. `audit_drift` now substitutes the canonical mechanical placeholders (`{{PRODUCT_NAME}}`, `{{PRODUCT_SLUG}}`, `{{SCHEMA_NAME}}`, `{{BACKEND_PORT}}`, `{{FRONTEND_PORT}}`, `{{PRODUCT_ICON}}`) into the template using each product's resolved metadata BEFORE diffing — successful substitution no longer surfaces as drift. Per-product metadata is read best-effort from `start.sh` PRODUCTS array (display name + ports) + the seed-row migration in `products/core/backend/migrations/NNN_seed_<slug>_product.sql` (canonical name + icon), with slug-derived defaults as fallback. Pass `mask_placeholders=False` to disable and see raw diffs (debugging the substitution itself). On the live repo this flipped 30 (file, product) pairs from `small_drift` → `identical`.

## Absorption strategies (with examples from rounds A-D, 2026-05-10)

### Strategy 1 — Delete dead code (zero consumers)

The simplest absorption is no absorption — vestigial wrappers that nobody imports just get deleted.

- **Example:** `app/exceptions.py` shims (4 products). They re-exported from `noctusai_lib.primitives.exceptions` but had **zero** consumers — vestigial from an earlier consolidation. **Action:** delete all 4 wrappers; the canonical `noctusai_lib.primitives.exceptions` continues to ship the real shapes.
- **Example:** `frontend/src/pages/SSOCallback.tsx` wrappers (9 products). Unrouted (the seed `createProductApp` already auto-mounts `/sso` on line 253 of `seed/framework/frontend/src/app.tsx`). **Action:** push the env-var reading the wrappers were doing into the seed mount itself; delete 9 wrapper files.

**When to use:** the duplication exists but nothing imports it (greppable: `grep -rn "from .exceptions" products/<name>/backend/app/` returns zero hits). Cheapest possible absorption — verify zero-consumer with grep, delete, build.

### Strategy 2 — Move to seed + re-export

Move the canonical content into the seed package, then either rewrite consumer imports to point at the seed, or leave a thin re-export shim in each product (acceptable for one cycle if rewriting all imports atomically would balloon the change).

- **Example:** 19 shadcn UI components shared by ERP + Therapy. **Action:** move canonicals to `seed/framework/frontend/src/components/ui/`; add a `package.json` `exports` field (`"./components/ui/*": "./src/components/ui/*"`); rewrite imports from `@/components/ui/X` → `@noctusai/seed/components/ui/X`. No re-export shims left behind — the import rewrite was small enough to do atomically.

**When to use:** byte-identical or trivially identical, and the consumer-side reference shape is uniform (all products import the same name). The re-export shim is a transitional aid, not the destination — it should be retired in the same cycle if you can.

### Strategy 3 — Factory pattern for near-identicals

When most of the file is shared but a few values vary per product, lift the *shape* into a seed factory and have each product call it with its variance as parameters.

- **Example:** `frontend/tailwind.config.ts` (11 products near-identical, only `./index.html` glob varied between products that ship vs. don't ship a top-level `index.html`). **Action:** `createTailwindConfig({ extraContent, extraPlugins })` factory in seed; each product's `tailwind.config.ts` becomes a 3-line call.

**Footgun:** factory deps must live where the factory does. If the seed factory `require()`s `tailwindcss-animate`, that dep must be installed in the seed package's `package.json`, not just per-product — `require()` resolves from the file containing the call. Same holds for Python factories that import optional vendor SDKs.

**When to use:** near-identical (≥0.95 similarity) and the variance is **finite + nameable** (a list of paths, a feature flag, an icon set). If the variance grows unbounded ("every product wants a different X"), the right pattern is dependency injection (Strategy 4 or a Protocol seam), not a wider factory signature.

### Strategy 4 — Template + runtime substitution

When the per-product variance is purely a runtime value (a port, a hostname), lift the file as a *template* with placeholders and let the runtime substitute at startup.

- **Example:** `frontend/nginx.conf` (3 products near-identical, only `listen <port>` varied). **Action:** seed-side `nginx.conf.template` with `${PORT}`; each product's `Dockerfile` `COPY`s the template to `/etc/nginx/templates/default.conf.template` + sets `ENV PORT=<port>`. The official `nginx:alpine` image substitutes templates from `/etc/nginx/templates/` at startup automatically — no runtime code change needed.

**When to use:** the variance is environmental (port, host, log level, feature toggle) rather than structural (different routes, different middleware). If a downstream tool already does template substitution (nginx, envsubst, Helm), prefer that over hand-rolling a templater in our code.

## Absorption loop (per-candidate)

This is the per-candidate workflow. It's the same shape whether you're absorbing one byte-identical file or running a multi-round campaign:

1. **Scan** — run `noctus.seed.scan_repetition`; pick a candidate. Default order: highest N first; ties broken by simplest absorption (byte_identical > near_identical > divergent; smaller LOC > larger).
2. **Evaluate** — read all instances; identify what (if anything) varies; pick a strategy from the four above. If strategy is unclear, walk through them in order — most candidates land on 1 or 2.
3. **Self-audit** — run `noctus.seed.list_capabilities`; confirm the seed doesn't already provide what you're about to add (skipping this is how the recurrence rule fires against itself).
4. **Absorb** — apply the strategy. Land the seed-side change first; then the consumer-side delete/rewrite; commit as one logical unit so a `git revert` would undo the whole absorption.
5. **Re-scan** — run `noctus.seed.scan_repetition` again; confirm the group disappeared (or shrank to a thin re-export wrapper that's structurally absorbed). If the group is unchanged, the absorption didn't take — investigate before moving on.
6. **Build verify** — at minimum 1 affected product per absorption: `cd products/<one>/frontend && npx vite build` (frontend) or `cd products/<one>/backend && pytest` (backend). For factories: build at least 2 products to confirm the factory works across the variance space.

## Safety rules

- **DON'T absorb when the per-product file genuinely has product-specific content.** "Looks similar" is not "should be one." If the variance is structural (different code paths per product), leave it scattered + accept-with-rationale; don't force a factory signature that obscures the divergence.
- **DON'T absorb something that's only N=1 yet.** Wait for the recurrence signal. Premature absorption builds a seed surface for a use case that may never materialize, and the seed becomes harder to learn for future contributors.
- **DON'T touch the `_filewalk` skip lists without updating BOTH scan_repetition + audit_drift.** The shared helper at `mcp/noctusai/tools/noctus/seed/_filewalk.py` feeds both tools — a one-sided change creates silent drift between them. There's a regression test on this; don't add `# silent-ok` to bypass.
- **ALWAYS verify via build, not just type-check.** TypeScript / mypy will catch most import errors but they miss `require()`-time module resolution failures, vite plugin loading failures, and runtime template substitution mistakes. The build is the oracle; static checks are a smoke test.

## Related

- **The inverse — `noctus.dev.delete_product`** — cascades through every registration surface (deactivate-row migration + `start.sh` + optional folder removal). Symmetry rule: every new scaffold registration surface MUST add a matching unregistration in `delete_product`. If absorption removes a product's need for a surface entirely, run `delete_product` on the product; don't leave half-registered ghosts.
- **Test hygiene** — when adding a new mutation tool (any `noctus.dev.*` or `noctus.seed.*` that writes), route writes through a `products_dir=` / `template_root=` test seam so the unit tests don't pollute real files. Regression-guard pattern at `TestScaffoldRespectsTestSeam` / `TestDeleteProductRespectsTestSeam` in `mcp/noctusai/tests/`.
- **Universal DRY recurrence rule** — `KB § PATTERNS/architect/project-execution.md § 2.7` (the rule that triggers absorption).
- **Seed-first design checklist** — `KB § GUIDES/seed-first-design.md` (companion checklist to use *before* writing new product code, so absorption-after-the-fact doesn't have to fire).
- **Accept-with-rationale catalog** — `KB § PATTERNS/common/accept-with-rationale.md` (durable home for the "we know this is duplicated, here's why we kept it" entries).
- **Absorption-search sextet** — `KB § 06-AGENTS.md § Absorption-search sextet` (the in-product duplication scanners that complement `scan_repetition`'s cross-product view).

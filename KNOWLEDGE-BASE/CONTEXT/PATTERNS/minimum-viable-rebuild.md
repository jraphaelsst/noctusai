# Rebuild only modified products, never the whole fleet

> **Rule.** Container rebuild scope = **the products whose code was actually modified this session**. NOT the fleet, even when a seed-level change technically affects every product. Other products catch up lazily on their next own-modify-triggered rebuild — every product Dockerfile `FROM noctus-seed-*-base`, so the seed change rides in on whatever build the next user actually needs.

---

## 1 · The slip pattern

A seed-level change (Dockerfile · seed FE · seed BE) lands. Agent reads "seed affects every product" and reflexes into `./start.sh` (whole fleet) or `docker compose up -d --build` (no slug filter). Result: ~9 containers rebuild in parallel, ~5–15 min wall-clock, high RAM+CPU+disk usage, and parallel-build daemon crashes (the 2026-05-20 bit — Docker Desktop died mid-flight rebuilding all 9 products at once). User waits, can't work, frustration compounds.

The conceptual confusion: a seed change conceptually affects every product, so the agent maps "every product affected" → "every product needs rebuild *now*." That's a false equivalence. **Affected ≠ needs-rebuild-now.** The product picks up the new seed on its NEXT build whenever that happens — driven by *that product's* next modification, not the seed's modification.

---

## 2 · The rebuild-scope test

Before any container build, ask:

> **"Which products did this session's commits actually modify?"**

`git diff --name-only origin/main..HEAD` (or the equivalent unstaged scope) → take the set of `products/<slug>/` prefixes → that's the rebuild scope. Plus base images if seed/ changed (cheap, shared, no fan-out).

Concretely, for the canonical commit shape:

| Change shape | Rebuild scope |
|---|---|
| Seed change only (`seed/...`, `KB`, root docs) | **Base images only.** No product containers. They each catch up on their next own-modify rebuild. |
| One product changed (`products/X/...`) | **Just X.** (Plus base images if seed/ also changed in the same set.) |
| Two products changed (`products/X/...` + `products/Y/...`) | **X and Y only.** |
| Whole fleet smoke-test (`./start.sh smoke-fleet` or analogous) | **All 9.** This is the explicit-fleet-ask carve-out (§4 below). |

---

## 3 · Why lazy cascade works

Every product Dockerfile inherits via `FROM noctus-seed-{backend,frontend}-base`. Build mechanics:

1. Seed change → rebuild base images (`scripts/infra/build-base-images.sh`). Cheap (~60–90s), single source of truth.
2. Each product's next `docker compose up -d --build <slug>` (triggered by whatever change that product owner is making) pulls the fresh `noctus-seed-*-base:dev` automatically, gets the seed change for free.
3. The seed change propagates organically as products are touched — no agent fan-out needed.

The base-image build is the **structural cure** for the "fleet rebuild on seed change" reflex: as long as bases are fresh, every consumer's next rebuild picks up the seed without a fleet-wide sweep.

---

## 4 · When fleet-rebuild IS the right call (carve-outs)

Sequential or parallel whole-fleet rebuild belongs to:

- **User explicitly asks:** "rebuild the fleet" / "smoke-test all products against the new seed" / "build everything" / explicit fleet smoke-test command.
- **Seed change has fleet-blocking validation gate:** rare — pilot-3 normally suffices ([[KB § PATTERNS/project-execution.md § 2.12]]).
- **Session purpose IS fleet work:** an absorption gate that requires every product to pass, a release-cut, a structural migration validated everywhere.
- **CI pipeline:** the CI runner rebuilds the matrix on every push — that's the validation layer for fleet-wide seed changes, separate from local dev.

Default in interactive sessions: **only modified products + base images if seed changed**.

---

## 5 · 2026-05-20 worked example — social-wiring

**Session diff:** `seed/framework/frontend/src/infra.tsx` + `seed/lib/frontend/.../useLLMSpend.ts` + 9 `products/*/backend/Dockerfile` (the ENV propagation) + `start.sh` + KB + new `products/social-wiring/backend/app/modules/media_creation/` module.

**Naive rebuild scope:** "All 9 product Dockerfiles changed → rebuild all 9." That's what the agent reflexed into and the user redirected.

**Correct rebuild scope:** Base images (seed/ changed) + social-wiring (the only product with actual code added this session — the media_creation module). The other 8 product Dockerfiles changed but ONLY a one-line `ENV VITE_SAME_ORIGIN=1` addition — it'll ride in on whatever rebuild those products' owners trigger next.

**Wall-clock delta:** ~2–3 min (1 product) vs ~15–30 min (9 products, with daemon crash risk).

---

## 6 · Composes with sibling rules

- **Pilot-products-first** ([[KB § PATTERNS/project-execution.md § 2.12]]): 3-pilot bound for *validating* a seed change; this rule's modified-only bound is for *not running unnecessary builds during normal dev*. They compose: pilot-3 is the validation layer; modified-only is the everyday-build layer.
- **Estimate off evidence, not structure** ([[KB § 01-PHILOSOPHY.md § Estimate off evidence]]): same shape — read the actual diff to decide scope, don't assume from "seed touches the fleet."
- **No quick fixes** ([[KB § 01-PHILOSOPHY.md § No quick fixes]]): inverted sibling — don't patch symptoms, also don't do unnecessary work.
- **Container freshness contract** ([[KB § PATTERNS/containerization.md § 12b]]): the freshness contract fires when a *running* container's code went stale. This rule fires when *no rebuild was needed in the first place* for the unchanged products.

---

## 7 · Detection — codify when recurrence ≥3

A `noctus.dev.*` MCP tool `check_rebuild_scope` could, given a session's planned `docker compose up -d --build ...` invocations + the working-tree diff, flag any rebuild whose target slug doesn't appear in the diff. Current recurrence: N=2 (this + the 2026-05-19 fleet-wide-build pre-crash documented in fleet/build-isolated branch). Stage-4 codification deferred to N=3 per [[KB § PATTERNS/methodology-codification-pipeline.md]]. For now [A] accept-with-rationale at the memory level.

---

**Doc anchors.** Memory entry: `feedback_minimum_viable_rebuild.md`. Bit: 2026-05-20 — agent kicked off fleet-wide sequential rebuild of all 9 products when only social-wiring had actual code changes. User redirected: *"is the social wiring build dependent on core or seed? Build whatever social wiring depends on. Leave the erp and all unnecessary builds. We only rebuild modified products, not the whole fleet."* Sibling: [[KB § PATTERNS/containerization.md § 5c]] sync runbook · [[KB § PATTERNS/seed-canonical-defaults.md]] (the seed change that triggered the slip).

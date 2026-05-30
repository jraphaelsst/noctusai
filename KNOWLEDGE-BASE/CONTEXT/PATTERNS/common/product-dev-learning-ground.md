# Product development is its own learning ground — learn the craft, not just the methodology

> **The craft half of the complementary pair** with `KB § PATTERNS/common/methodology-execution-discipline.md`. Same mindset — *friction is a learning event* — but this axis improves **how we BUILD products** (development technique), not **how we work** (process). A standing user value, re-enforced 2026-05-30 as product development resumes.

## The gap this closes

The platform has a mature **methodology** learning loop (the s1→s2→s3→s4 codification pipeline + keepers — process improvement is first-class). It has *mechanism* for craft learning (`KB § PATTERNS/common/build-learn-cache-mindset.md` — every artifact accumulates 8 knowledge categories as it's built) but had not named **craft improvement as a deliberate, compounding loop**. Result: product-dev lessons risk being fix-and-forgotten instead of compounding, so we re-learn the same technique lessons on each product.

## The rule

**Treat product development as a first-class learning ground.** While building the actual apps (backend/frontend), a bug that recurs, an approach that failed, or a pattern that proved out is a **learning event for development technique** — capture it, don't just fix-and-forget, so the next product is faster and better:

1. **Fix** the immediate issue.
2. **Capture** the technique lesson as you build — via the `build-learn-cache` mechanism (sidecar `<artifact>.knowledge.yaml` ∨ noc-graph node; the 8 categories: known_facts / errors / drifts / alternatives / manual_validation / integration / e2e / bugs_fixed).
3. **Promote** a recurring technique (N≥2 across artifacts/products) into the **dev-technique pattern library** — `KB § PATTERNS/backend/*` or `KB § PATTERNS/frontend/*` — the craft analog of the methodology codification pipeline.

The destination is distinct from methodology lessons: **craft lessons → `KB § PATTERNS/backend|frontend/`** (how to build); methodology lessons → `KB § PATTERNS/common|architect/` + the s1→s4 pipeline (how we work).

## The two axes (complementarity thesis)

> **Neither alone is enough: a perfect methodology building products with un-compounding technique still stagnates, and great technique on a leaky process still drifts. Together they make the system get better on BOTH axes every time we touch it.**

Process axis (`methodology-execution-discipline.md`) ↔ craft axis (this doc) = two flywheels; the org compounds only when both spin. When friction surfaces, ask **which axis it teaches** — a gate/tooling slip → process; a product bug/build-technique miss → craft — and route the lesson to the matching ground.

## Composes with
- `KB § PATTERNS/common/methodology-execution-discipline.md` — the process-axis complement.
- `KB § PATTERNS/common/build-learn-cache-mindset.md` — the per-artifact capture mechanism this elevates into a deliberate loop.
- `KB § PATTERNS/backend/*` · `KB § PATTERNS/frontend/*` — where promoted craft patterns live.
- `KB § PATTERNS/common/methodology-codification-pipeline.md` — the methodology-axis analog of "promote a recurrence."

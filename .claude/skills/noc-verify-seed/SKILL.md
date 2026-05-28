---
name: noc-verify-seed
description: Use BEFORE dispatching any "consume seed X" or "build seed X" slice — triggers "consume seed", "use seed adapter", "wire to seed X", "verify the seed ships it", "is the seed ready", "build a seed for X", "new seed". Two-leg gate — discovery (does this already exist?) + existence (do the four ships-it gates pass?) — that catches both the duplicate-build trap and the half-ship trap before the engineer pays the contextualization tax.
version: 1.0.0
---

# noc-verify-seed — discovery + existence gates at dispatch time

🔴 **Two traps this skill catches:**
- **Duplicate-build:** a brief says "build a seed for X" but a similar seed already exists. Embedding-space lookup is faster than human archaeology.
- **Half-ship consume:** a brief says "consume seed X" but only Protocol+Fake shipped — no Real, no factory, no `__init__.py` export. 30s grep saves 30min of engineer rework.

## Workflow

### Leg A — Discovery (BEFORE authoring or briefing a NEW seed; semantic, ~5s)

0. **Does this seed already exist (or nearly)?**
   - `noctus.dev.code_similar_to_text text="<brief's planned-consume description>" top_k=5` against the code-embeddings cache (mcp + noctusai_lib + products/seed).
   - `noctus.dev.kb_neighbors text="<same description>" top_k=5` against KB integrations/patterns.
   - **score ≥ 0.85** ⇒ STRONG signal a sibling exists ⇒ STOP, present the candidates, re-brief as "consume seed `<existing>`" (skip to Leg B).
   - **score 0.75-0.85** ⇒ WEAK signal ⇒ open the candidate file, judgment call (extend the existing seam vs new seed). Document the decision (this is a `noc-triage` decision point).
   - **score < 0.75** ⇒ no sibling, proceed to author the new seed.

### Leg B — Existence gates (BEFORE dispatching a "consume seed X" slice; deterministic, ~30s)

1. **Resolve the seed surface against the FORK BASE, not the working tree.** Dispatching = engineer forks off `origin/dev`. The truth is what `git ls-tree origin/dev` shows. One call: `git -C <primary> ls-tree -r origin/dev -- noctusai_lib/integrations/<X>/ | grep -E "__init__|adapter|factory"`.

2. **Check the four ships-it gates** (each one a single grep — ALL must pass):
   - **Protocol exported** — `git show origin/dev:noctusai_lib/integrations/<X>/__init__.py | grep -E "^(from|import) .*\b<X>Protocol\b"`.
   - **Fake exported** — same `__init__.py`, `Fake<X>` symbol.
   - **Real exported** — same, `Real<X>` (or `<Vendor><X>` for branded adapters).
   - **Factory exported** — `make_<x>` (lowercase) returns the Protocol; grep for `def make_<x>(`. The factory IS the consumer-facing seam; missing factory ⇒ consumer-side forks.

3. **Verify the consumer-import path the brief will use** — `git show origin/dev:noctusai_lib/integrations/__init__.py | grep -E "^from \.X import"`. Import that doesn't resolve = stale-base dispatch.

4. **Spot the half-shipped slip.**
   - Gates 1+2 pass, 3+4 fail ⇒ Protocol+Fake but no Real/factory ⇒ scope adjust BEFORE dispatch (extend seed OR re-route).
   - Gates all pass but factory's signature ⊥ what the brief plans to call ⇒ extend the seed seam (back-compat-defaulted shape-config) BEFORE the consumer slice. → `KB § PATTERNS/architect/seed-canonical-defaults.md`.

5. **Emit the verification line in the brief** — `seed-ships-verified: noctusai_lib.integrations.<X> { Protocol, Fake, Real, make_<x> } @ <origin/dev sha>` — engineer trusts without re-verifying.

## Guardrails
- ⚠️ Leg B verifies against `git ls-tree origin/dev`, NEVER the working tree. The harness's `Agent isolation: "worktree"` famously forks from a stale base; even with `task_branch`, truth is the fork base.
- ⚠️ Leg A returns SUGGESTIONS — embeddings have false positives. A 0.85 hit is a "look at this," not "this is identical." Open the file before deciding.
- Pure-logic seed modules (no IO) are exempt from Real/factory gates — they ship as a function, not Protocol+Fake+Real triple.
- "Consume seed" briefs without Leg B are forbidden. "Build new seed" briefs without Leg A are forbidden. Both gates are cheaper than the engineer's contextualization tax (~45-60k tokens) + rework loop.

## Depth
`KB § 03-SEED-ARCHITECTURE.md` (the spine) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` (the shape) · `KB § PATTERNS/architect/seed-canonical-defaults.md` (defaults are answers) · `KB § PATTERNS/common/code-embeddings.md` (Leg A backing cache) · memory `feedback_verify_seed_ships_it{,_at_dispatch_time,_on_fork_base}` (the three codifications this skill folds).

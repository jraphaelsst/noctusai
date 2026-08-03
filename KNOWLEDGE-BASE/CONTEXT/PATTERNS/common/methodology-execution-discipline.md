# Methodology execution discipline — close the loop, work within the grain, learn from gating

> **The behavioral half of the prevention system.** The branch-hygiene + learn-before-archive *machinery* (keeper / sweep / salvage gate) is the safety net that catches drift after the fact. This discipline is how agents *behave* so the net rarely has to fire. One of a **complementary pair** with `KB § PATTERNS/common/product-dev-learning-ground.md` — see "The two axes" below.

Born 2026-05-30: ~330 dangling remote branches + an embedding-refresh tax + a history of `--no-verify` rationalizations had accumulated. Every one traced to a *behavioral* gap, not a missing tool. The tools were then built; this codifies the behavior.

## The five principles

### 1. Close the loop — "works" ≠ "done"
A task is done only when **nothing dangles**: branch integrated-or-salvaged, `origin` branch deleted post-integration, worktree removed, docs + caches synced, no orphan ref / pointer / temp file. **Whoever pushes a branch owns its cleanup on integration** — pushing for durability without later deleting is the literal source of the orphan-branch pile-up. The close-out checklist:
- branch merged (or salvaged-then-deleted per learn-before-archive) ·
- `origin/<branch>` deleted once content is confirmed on `dev` ·
- worktree removed (`git worktree remove`) ·
- docs/KB/INDEX synced, caches fresh (the hooks handle most) ·
- no `NOC-REMEDIATE` left without a named destination.

Backstopped by `check_dangling_remote_branches` + `session_end_sweep` (remote section) + the guarded `delete_integrated_remote` tool — but the *default* is to close the loop yourself, not lean on the net.

### 2. Work within the grain — know the gates before you act
The gates are knowable, so anticipate them and execute cleanly instead of tripping them mid-flight:
- **CLAUDE.md word cap (~2500) + pointer-only §1** — check the budget before adding a §1 line; trim a verbose line if needed (its detail lives at its KB pointer). → `KB § PATTERNS/common/claude-md-router-discipline.md`
- **pre-commit keepers** — `kb_sync` (every KB doc indexed, pointers resolve), `check_claude_md_router`, `check_eight_way_sync`, cache refreshes. Author docs from the live keeper contract (`keeper_pattern_lookup`) before writing.
- **change-gated pre-push** — a delete-only / no-source push skips the embed refresh; a source change refreshes only the affected caches. Don't expect (or wait on) a full refresh that won't run. → `KB § PATTERNS/common/push-time-embedding-gate.md`
- **branch protection** — `main`/`prod` are gated; everyday work + pushes land on `dev`.

A gate you could have foreseen tripping is a **planning miss**, not bad luck.

### 3. A fired gate is a learning event, never a bypass target
When a keeper / budget / wall fires: **STOP → understand WHY → fix correctly OR surface to the tech-lead → codify if it is a recurring shape.** Never `--no-verify`, never fight the linter/budget, never blind-delete. This sharpens "safety nets capture failures → learnings → methodology evolves" into an *operating* rule: the firing is signal, and the response is to learn, not to route around. Worked example (2026-05-30): a recurring `vector-costs.ndjson` merge conflict was fixed at the root with a `merge=union` gitattribute rather than re-resolved by hand each time. → `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` · `KB § PATTERNS/common/background-engineer-safety-discipline.md`

### 4. Prove the check can FAIL — a green that cannot go red proves nothing

Writing a guard is not the same as having one. Before trusting any new test, gate, assertion or
detector, **break the thing it guards and watch it fail**. If it still passes, it is not a guard —
it is decoration that will report success forever, including on the day the defect ships.

The negative control is one command and it is not optional for anything guard-shaped:
```
# 1. guard passes on healthy code           → expected
# 2. remove/corrupt the guarded property    → the guard MUST now FAIL
# 3. restore                                → guard passes again
```
Step 2 is the whole point. A guard that skips it has never been tested — only *run*.

**Worked example (2026-08-03).** An agent diagnosed a "silent false-green" (worktree tests
resolving another tree's seed lib), built a `pytest.ini` `pythonpath` pin, fanned it across 11
products + the seed template, and wrote 12 guard tests. All 12 passed. Then the negative control:
remove the pin → **the guard still passed**. That single red-that-wasn't exposed the truth — every
product's `tests/conftest.py` had solved this in May, the diagnosis was wrong (it came from a bare
`python -c` probe, which does not load conftest), and the entire mechanism was a duplicate. All of
it was reverted *before* commit. Without the negative control, a fork of an existing seed mechanism
would have shipped fleet-wide with a full green suite vouching for it.

⇒ **A passing new guard is a hypothesis until you have seen it fail on purpose.**

### 5. Search for prior art BEFORE designing a fix — source-of-truth applies to solutions

"Codebase is source of truth" is usually read as *verify facts against the tree*. It applies just as
hard to **solutions**: before designing a mechanism, grep for the one that already exists. The most
expensive bug is not a wrong fix — it is a *correct* fix for a problem someone already solved,
because it lands as a second mechanism doing the same job, i.e. a fork, and both drift from then on.

The check is ~30 seconds and precedes design, not review:
- `grep` the obvious host files (`conftest.py`, the seed lib, the product's own module) for the
  concept you are about to implement;
- `noctus.dev.code_search` / `find_reusable_component` for the fuzzy-intent version;
- read the sibling product that hit this first — fan-outs leave comments naming their origin
  (the May shim literally said *"mirroring ERP-P7's reference fix"*).

Trigger phrases that should stop you cold and send you grepping: *"this needs a mechanism"*,
*"I'll add this to every product"*, *"the seed should handle this"*. All three are
replication-to-seed-symmetry language — the right count of new mechanisms is usually **zero**.
→ `KB § PATTERNS/architect/project-execution.md` (replication-to-seed symmetry)

⇒ **Design starts with a grep, not a blank file.**

## The two axes (complementarity thesis)

This rule improves **how we WORK** (process). Its complement, `KB § PATTERNS/common/product-dev-learning-ground.md`, improves **how we BUILD** (product craft). Same core mindset — *friction is a learning event* — applied to two grounds:

> **Neither alone is enough: a perfect methodology building products with un-compounding technique still stagnates, and great technique on a leaky process still drifts. Together they make the system get better on BOTH axes every time we touch it.**

They are two flywheels; the org compounds only when both spin. Always read/codify them as a pair.

## Composes with
- `KB § PATTERNS/common/product-dev-learning-ground.md` — the craft-axis complement.
- `KB § PATTERNS/common/learn-before-archive.md` — the pre-delete salvage gate (close-the-loop's "salvage" leg).
- `KB § PATTERNS/common/drift-fix-on-contact.md` · `storage-hygiene.md` · `persistent-files-absorption.md` — the hygiene rules this operationalizes.
- Roadmap: `project-history/roadmaps/branch-hygiene-and-learn-before-archive-2026-05.md`.

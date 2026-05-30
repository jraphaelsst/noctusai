# Methodology execution discipline — close the loop, work within the grain, learn from gating

> **The behavioral half of the prevention system.** The branch-hygiene + learn-before-archive *machinery* (keeper / sweep / salvage gate) is the safety net that catches drift after the fact. This discipline is how agents *behave* so the net rarely has to fire. One of a **complementary pair** with `KB § PATTERNS/common/product-dev-learning-ground.md` — see "The two axes" below.

Born 2026-05-30: ~330 dangling remote branches + an embedding-refresh tax + a history of `--no-verify` rationalizations had accumulated. Every one traced to a *behavioral* gap, not a missing tool. The tools were then built; this codifies the behavior.

## The three principles

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

## The two axes (complementarity thesis)

This rule improves **how we WORK** (process). Its complement, `KB § PATTERNS/common/product-dev-learning-ground.md`, improves **how we BUILD** (product craft). Same core mindset — *friction is a learning event* — applied to two grounds:

> **Neither alone is enough: a perfect methodology building products with un-compounding technique still stagnates, and great technique on a leaky process still drifts. Together they make the system get better on BOTH axes every time we touch it.**

They are two flywheels; the org compounds only when both spin. Always read/codify them as a pair.

## Composes with
- `KB § PATTERNS/common/product-dev-learning-ground.md` — the craft-axis complement.
- `KB § PATTERNS/common/learn-before-archive.md` — the pre-delete salvage gate (close-the-loop's "salvage" leg).
- `KB § PATTERNS/common/drift-fix-on-contact.md` · `storage-hygiene.md` · `persistent-files-absorption.md` — the hygiene rules this operationalizes.
- Roadmap: `project-history/roadmaps/branch-hygiene-and-learn-before-archive-2026-05.md`.

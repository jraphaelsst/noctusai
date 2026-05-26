---
name: noc-branch-dispatch
description: Use when parallelizing work across multiple engineers — triggers "dispatch agents", "branch this in parallel", "run these in parallel", "branch + dispatch", "branch yourself and dispatch N agents". The architect/tech-lead decomposes into file-disjoint slices, dispatches isolated engineers, integrates, gates.
version: 1.0.0
---

# noc-branch-dispatch — parallel engineer orchestration

The orchestrator IS the architect/tech-lead (plans + dispatches + integrates + stays with the user). Subagents ARE engineers (focused briefs, isolated worktrees, build + report, never plan orchestration). "branch yourself and dispatch" = the tech-lead self-branches its OWN inline slice AND dispatches engineers who EACH self-branch (apply this with `noc-self-branch`).

## Workflow (10-step runbook)

1. `noctus.dev.dispatch_preflight project_slug=<slug>` — fork-base + collision + env-pin + project-doc-phantom checks.
2. **Decompose into file-disjoint slices** — classify collision-class per slice vs the parallel-active file set (`git diff --name-only`): C1 disjoint → parallel-clean · C2 same-file-additive → brief additive-only · C3 substantive-overlap → re-scope to a sibling file OR sequence.
3. One isolated worktree per engineer off `origin/dev` (`task_branch start` per slice).
4. **Dispatch in ONE message** (multiple `Agent` calls) so they run concurrently. Each brief ≤~15 lines, references `engineer-default`. Sonnet default; `model: opus` only for judgment-heavy slices.
5. Collect each engineer's short-form return + a `/tmp` patch overlay-safety copy.
6. **Detect collisions** — (a) path-overlap AND (b) semantic-duplicate git can't see.
7. Merge `--no-ff` least-conflict-first; **dedicated honest reconciliation commit** for any reconciliation.
8. Architect runs the FULL gate ONCE at integration on a clean `origin/dev` tree (engineers run only the narrowest scoped check).
9. Cleanup worktrees (salvage-before-delete).
10. Gate `main` only at 100% — human-gated per R4.

## Guardrails
- Below `<100 LoC ∧ <3 files ∧ single-phase` → the architect does it **inline** (don't pay the ~45–60k engineer contextualization tax). 2+ small file-disjoint tasks ride ONE compound brief.
- Wave N+1 dispatches only after every Wave N slice **FF-merges** (not just reports).
- Engineers commit ONLY their own branch; tech-lead owns all merging/pushing/blessing.

## Depth
`KB § PATTERNS/branching-dispatch.md` (the runbook) · `KB § PATTERNS/branching-and-merging.md` §18/§21 (collision-class) · `KB § PATTERNS/dispatch-engineer-tuning.md` (fast/cheap engineers).

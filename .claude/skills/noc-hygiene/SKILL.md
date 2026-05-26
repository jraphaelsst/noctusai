---
name: noc-hygiene
description: Use for end-of-work cleanup and absorption sweeps — triggers "what cleanup is urgent?", "hygiene scan", "any duplication to absorb", "dead code", "stale worktrees / disk". Run the keeper-analog tools before walking away.
version: 1.0.0
---

# noc-hygiene — curatorial sweep before you walk away

Keeper = regulatory (blocks commits). Hound/mole = curatorial (surfaces what to clean).

## Workflow

1. **Code hygiene** — `noctus.hound.scan` = single entry for absorption (file-level) + fusion (cross-tool) + optimization (intra-file); emits `next_action` (default "what cleanup is urgent?").
2. **Absorption sextet** (editing a product's services/routers/hooks, even unrelated work) — `scan_cross_product_helpers` + `scan_within_product_helpers` + `scan_service_line_recurrence` + `scan_block_patterns`. Within-product N=2 = architect-eyes; scanners threshold N≥3.
3. **Storage hygiene** — `noctus.dev.mole` over artifacts · environments · stale `.claude/worktrees/agent-*/`. `sweep --force` is destructive (dry-run default; never deletes uncommitted/main/siblings/.env/migrations).
4. **Worktree removal = salvage ritual** (every teardown): (1) extract learnings → KB/memory → (2) record recovery pointer (branch+SHA → `project-history/worktree-salvage.ndjson`) → (3) mole sweep → (4) remove. Tear down ONLY through a tool (`task_branch cleanup` / `mole sweep` / `cleanup_stale_worktrees`) — never a bare hand-typed `git worktree remove`.

## Guardrails
- DRY recurrence rule: N=2 → triage · N=3+ → MUST formalize (extract to seed/shared-lib).
- Remediation markers `NOC-REMEDIATE[<class>]: … — <date>` are the sanctioned non-silent deferral; batch via `noctus.dev.scan_remediation_markers`.

## Depth
`KB § PATTERNS/architect/seed-absorption.md` (hound) · `KB § PATTERNS/common/storage-hygiene.md` (mole) · `KB § 06-AGENTS.md` (sextet/trio).

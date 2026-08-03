---
description: Methodology garbage-collection — the exhaust leg of the capture pipeline. Measures the always-on budgets, retires promoted/stale memory index lines, and proposes §1 rule-family consolidations.
---

# /gc — methodology garbage-collection

You are running the **methodology-GC** protocol. The user invoked `/gc $ARGUMENTS`.

**Premise:** this methodology has world-class *capture* (triage → memory → `/codify` → keeper) and this command is its *exhaust*. Without GC the always-on surfaces grow monotonically while every keeper stays green — because the keepers gate the SHAPE of each entry, not the NUMBER of them. Measured twice: §1 went 72 → 79 rules across a fortnight in which the word budget was raised to accommodate it. → `KB § PATTERNS/common/methodology-gc.md`

**Cadence:** monthly, or immediately when `check_claude_md_router` trips its rule-count ceiling.

## Protocol

1. **Measure budgets** — report each against its ceiling:
   - CLAUDE.md §1 rule count — `awk '/^## 1 ·/,/^## 2 ·/' CLAUDE.md | grep -c '^- '` (target 50; `check_claude_md_router` hard-caps 55).
   - CLAUDE.md word count (cap 2500).
   - `MEMORY.md` bytes (keeper caps 20 KB; the harness read returns NOTHING past ~24.4 KB — the cap sits deliberately below that cliff) + topic count.
   - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/` file count (junk-drawer threshold 50 — propose a topical split above it).
2. **Retire promoted memories** — for each `MEMORY-<topic>.md` pointer whose rule now lives in CLAUDE.md §1, a `CLAUDE/<topic>.md`, or a keeper: retire the pointer. NEVER delete the body file — vector recall still reaches it (learn-before-archive).
3. **Sweep stale entries** — verify against the codebase/git before archiving anything (codebase is source of truth; an entry that looks stale but reflects live state gets a refreshed hook instead).
4. **Sweep orphans** — memory files absent from every index: index the live ones, archive the superseded ones.
5. **Propose §1 family consolidation** — ≥4 §1 rules sharing one framework ⇒ propose collapsing to a single family line + a family-index KB doc holding the members **verbatim**. The test is *"would a session that needs one member need the rest?"* — shared topic words are not enough. Load-bearing standalone rules (seed-first, no-silent-errors, self-branching) stay standalone regardless. **Propose only**: §1 edits are router surgery — apply with user consent, keeper-gated, and prove the move lossless (every original rule survives exactly once) rather than asserting it.
6. **Restore budgets** — after a consolidation, tighten any cap that had been raised as a stopgap back to what the content now supports. A cap that only ever rises is not a budget.
7. **Report** — budgets before/after, what was retired, consolidation proposals. If everything is within budget: say so and stop — a no-op GC is a healthy result.

## Guardrails
- **Learn-before-archive is absolute** — GC moves *index lines*, never deletes *body files*.
- **Verbatim or nothing** — a family consolidation MOVES rule text byte-for-byte. Summarising a rule into a family line is lossy and forbidden. → `KB § PATTERNS/common/lossless-doc-refactor.md`
- §1 and keeper changes ride the normal gates (`check_claude_md_router`, `kb_sync`) — never `--no-verify`.
- GC is not `/codify` — it retires and consolidates what's already decided; it never promotes. Ripe candidates found mid-sweep route to `/codify`.

Reference: `KB § PATTERNS/common/methodology-gc.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` (this command closes its loop) · `KB § PATTERNS/common/persistent-files-absorption.md`.

# Knowledge lifecycle — family index (§1 consolidation)

> **Family-line pattern:** CLAUDE.md §1 carries ONE line for this family; the member rules live here **verbatim**. This is a lossless MOVE, not a summary — the bytes below are the bytes that were in §1. Each member keeps its own depth doc; this index is the router hop between the §1 family line and those docs. Consolidated 2026-08-03 (harness-audit re-author; §1 had reached 79 always-on rules). → `KB § PATTERNS/common/methodology-gc.md`

The **learning posture** rules (safety nets · friction on both axes · always-hardening · triage-at-decision-time) are their own family — that family is about NOTICING, this one about what happens to what you noticed.

## Members (verbatim from §1)

- **Knowledge tracking — durable findings.** findings.md = what-we-LEARNED; in-flight comms processed same commit, not parked. → `KB § 01-PHILOSOPHY.md`
- **Scoped auto-improvement + consult-before-editing.** Dispatches surface `drift-found:`/`scoped-improvement:`; tech-lead RESOLVES, engineers SURFACE; consult BEFORE editing any doc/agent; log open entries with a `resolve_when` so landed drift self-closes. → `KB § PATTERNS/common/scoped-auto-improvement.md`
- **Persistent-files absorption.** findings.md/PROJECT.md/lessons MUST land in KB/memory BEFORE archive — recovery pointer + absorption both legs. → `KB § PATTERNS/common/persistent-files-absorption.md`
- **Learn-before-archive.** Before any destructive op preserve what would be LOST; tool `noctus.dev.salvage_before_delete`. → `KB § PATTERNS/common/learn-before-archive.md`
- **Roadmap tracking — multi-session project plans.** Multi-slice initiatives live in `project-history/roadmaps/<slug>-YYYY-MM.md` (durable, mutable — `projects/` is ephemeral, ndjson is event-shaped). Goal + slice table + decision log + retrospective. Absorb lessons → KB/memory. → `KB § PATTERNS/common/roadmap-tracking.md`

## Why a family line

These 5 rules shared one framework, and a session that needs one of them typically needs the rest — so a single router hop costs a lookup and returns 4 always-on lines of budget. The forcing function is the router keeper's rule-COUNT ceiling; the procedure is `/gc` step 5. → `KB § PATTERNS/common/claude-md-router-discipline.md`

## One ledger, four islands merged (2026-11-04)

The learning writers now share the auto-improvement ledger as their durable copy (injectable `ai_logger` seam, default `auto_improvement.log_entry`; a logger failure is surfaced in the return, never swallowed):

- `noctus.dev.phase_learning_log` -> also `kind=phase-learning`, `source={tool:phase_learnings, ref:<sqlite id>}`; SQLite stays the local cache. Return is `{id, ledger}`.
- `noctus.dev.brief_ledger_append` -> `outcome` of `miss`/`rework` also writes `kind=drift` (with `resolve_when`) attributed to the agent; successes are not logged there. Return carries `ai`.
- `noctus.dev.findings` -> also `kind=finding`, `source={tool:findings, ref:<slug>:<category>:<sha8>}`. Return carries `ledger` + `finding_ref`.
- `noctus.dev.archive` (project mode) -> learn-before-archive no longer trusts `learnings_absorbed`: every `kind=finding` row for the project must be closed or promoted (status != `s1-emergent`), else it refuses listing the open rows. Escape `accept_open_findings="<reason>"` (reason echoed in the return). A `findings.md` with no ledger rows (pre-merge project) still falls back to `learnings_absorbed=True`.

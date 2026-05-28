---
name: noc-wrap-up
description: Use at end-of-task wrap moments — triggers "anything else?", "are we done?", "wrap up", "what's left?", "final check", "done?", "before we ship", "before I push". Honest 3-5 polish-item survey, never reflexive "all good". Born from the 2026-05-26 evening session that caught 11 silent test failures via this exact discipline.
version: 1.0.0
---

# noc-wrap-up — honest assessment before the wrap

🔴 **The trap:** "anything else?" → reflexive "no, all good." That answer ships silent debt. Survey-and-name beats reflex.

## Workflow

1. **Survey five surfaces** (read-free; just check the actual state):
   - **Silent test failures** — `noctus.dev.pytest` over touched modules (or `pytest -q` on the slice's test file). Test files that import an undeclared dep silently skip; test files green-but-skipped count as failed surveys. → `KB § PATTERNS/common/silent-test-failure-from-missing-dep.md`.
   - **Two-leg dispatch footer leftovers** — `noctus.dev.auto_improvement_query open_only=true since=<session-start>` for unresolved `drift-found:` / `scoped-improvement:` entries opened in this session. Tech-lead RESOLVES; engineers SURFACE. Nothing should leave the session in s2-memory if a s3-codified move is cheap. → `KB § PATTERNS/common/scoped-auto-improvement.md`.
   - **s-stage backfills owed** — same query, status filter `s2-memory` or `s3-codified` without a same-target s4. `noctus.dev.codify_log` enforces s4-requires-s3; backfill in-session beats next-session-archaeology. → `KB § PATTERNS/common/methodology-codification-pipeline.md`.
   - **Untracked + uncommitted drift** — `git status --porcelain` at the worktree AND the primary checkout. Untracked at root = drift-fix-on-contact precondition; uncommitted in a peer worktree = potential cross-tree pollution. → `KB § PATTERNS/common/drift-fix-on-contact.md`.
   - **Pending dispatches / orphan branches / stale caches** — `noctus.dev.cleanup_stale_worktrees dry_run=true` + `noctus.dev.orphan_branch_sweep` + `noctus.dev.detect_stale_caches`. Three single calls, ~5s total.

2. **Name 3-5 polish items WITH rationale** — for each surfaced surface, write one line: `<item> — <why it matters now>`. If a survey returns clean, SAY SO ("no s2-memory entries opened this session") rather than skipping the survey line (silent-skip = silent-error shape).

3. **Decide in-flight vs surface-with-destination** — clear-path polish items resolve THIS commit (in-flight-resolution rule); only genuinely-out-of-scope / needs-decision items get a named destination (`NOC-REMEDIATE[<class>]` marker, project followup row, or s2-memory entry). NEVER park a clear-path item with a vague "follow up later".

4. **Present the survey, ask explicit go/no-go** — the user decides what's wrap-blocking vs ship-anyway. The survey is the gift; the decision stays the user's.

## Guardrails
- "All good" is a **positive claim** that the 5 surveys ran clean — say WHICH surveys ran, not just the conclusion. Reflexive all-good without a survey = silent-error shape.
- Wrap-up survey is NOT the same as the hygiene sweep (`noc-hygiene` runs hound/mole; `noc-wrap-up` checks session-specific debt). Both fire at end-of-work; this one is fast (~30s), `noc-hygiene` is slower.
- Sibling discipline: when the user says "wrap up" + "ship to main" together, this skill runs FIRST, `noc-ship` runs after — the wrap survey is a pre-condition for the bless gate.

## Depth
`KB § 01-PHILOSOPHY.md` (no silent errors · fix-on-contact · in-flight resolution) · `KB § PATTERNS/common/scoped-auto-improvement.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` · memory `feedback_honest_wrap_up_assessment.md` (the codified rule).

# mcp-tool-name-alignment — Orchestration Findings

> Transcribed by the orchestrator post-merge per `KB § PATTERNS/branching-and-merging.md § 17.6.1`. Engineer F kept audit data inline in PROJECT.md §6 Phase 0 + §11 Change log per the no-silent-errors rule after the harness blocked their `findings.md` Write call; this file curates the synthesis from their report.

## Errors encountered

None.

## Mistakes / slips

- **Harness blocked findings.md Write** despite the brief's explicit Write-authorization paragraph. The harness's "subagents return findings as text, not write report files" guard fired. Engineer-side workaround: audit data preserved inline in PROJECT.md §6 Phase 0 + §11 Change log per the no-silent-errors rule. **This finding contributed to the §17.6.1 N=5 recurrence formalize.**

## Lessons learned (durable rules)

- **The trigger was tighter than the slip.** AdConnect MVP HEAD references only the 3 live `noctus.seed.*` tools (`audit_drift`, `list_capabilities`, `scan_repetition`). The brief's "PROJECT.md drafts referenced names that don't exist" reflected an earlier draft state already corrected before the audit ran. The slip-recovery flow worked tighter than the brief assumed. **Lesson:** audit projects can pivot from "rewrite errors" to "confirm clean state" — the audit itself is the deliverable.
- **MCP-tool namespace surface is healthy** as of 2026-05-10. 269 references audited (22 `noctus.seed.*` + 247 `noctus.dev.*`). Zero wrong-namespace cases. Zero actionable dead references.

## Interesting findings (surprises, discoveries)

- **5 aspirational/historical tool references** (left alone, documented in PROJECT.md §6):
  - `noctus.dev.archive_phase` (KB future-tense)
  - `noctus.dev.deploy` (KB "would close the loop")
  - `noctus.dev.dispatch_parallel` (KB "Follow-up project (TBD)")
  - `noctus.dev.team` (archived doc records the rejected name → renamed to `noctus.team.*`)
  - `noctus.dev.phase_learning_*` (legit wildcard glob over `phase_learning_{consume,log,query}`)
- **Live tools never mentioned in projects/KB**: `batch_speed_gain_{cumulative,log,query,update}`, `delete_product`, `scaffold_interrogate`. Valid tools that don't yet appear in any project doc — either undocumented, or simply unused so far.
- **Architect's "tools the platform thinks should exist" list** surfaced as deferred candidates: `archive_phase`, `deploy`, `dispatch_parallel`, plus `noctus.seed.report` / `scan_fusions` mentioned in MEMORY.md as "built 2026-05-10" but not in HEAD on the audit branch (lived on a parallel agent's unmerged work).

## Knowledge pieces (durable patterns)

- **Authoritative live-tool counts** (from `grep -rn 'name="noctus\.' mcp/noctusai/tools/`) on origin/main as of audit time:
  - `noctus.seed.*` — 3 live: `audit_drift`, `list_capabilities`, `scan_repetition`
  - `noctus.dev.*` — 66 live (full list in PROJECT.md §6 Phase 0)
  - `noctus.team.*` — 6 live (out of scope)
- **Audit recipe**: enumerate every `noctus.{seed,dev,team}.*` mention in `projects/**/PROJECT.md`, `archive/projects/**/PROJECT.md`, `KNOWLEDGE-BASE/**/*.md`, `CLAUDE.md` + `CLAUDE/*.md`, `mcp/noctusai/**/*.py` (docstrings + comments), `products/**/MASTER-PROMPT.md` + `products/**/README.md`. Classify as Correct / Wrong-namespace / Dead / Aspirational.

## Deferred items

None deferred. The 5 aspirational tools form an interesting "tools the platform thinks should exist" list — surfacing to architect for future prioritization, but not actionable in this hygiene project.

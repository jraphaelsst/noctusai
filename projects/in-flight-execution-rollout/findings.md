# in-flight-execution-rollout — Findings

Curated knowledge artifact per `KB § 01-PHILOSOPHY.md § Knowledge tracking — durable findings file` + `KB § PATTERNS/branching-and-merging.md § 17`. Orchestrator (CLI agent) appends slips / errors / lessons / surprises as subagent reports come in. Final synthesis pass at orchestration close.

---

## Errors encountered

_(none yet — Batch 1A dispatch pending)_

---

## Mistakes / slips

- **2026-05-03 · orchestrator (me):** Delegated orchestration itself to a subagent (the master-tree planning task that produced this very PROJECT.md). User caught it immediately: *"why didnt you fly in with them? That was what i was expecting. You fly in as the head."* Lesson formalized as anti-pattern in `KB § 01-PHILOSOPHY.md § Branching-first orchestration` + CLAUDE.md universal-rule bullet + `feedback_branching_first_orchestration.md`. **Subagents are EXECUTORS, never PLANNERS.** Slip caught on the very first parallel-execution opportunity, before it could become a habit.
- **2026-05-04 · orchestrator (me):** Single-worktree contention discovered when the projects-cleanup subagent's `git checkout -b` switched the orchestrator's worktree state mid-flight, stashing uncommitted Phase 0 work. The branching-first methodology shipped that morning implicitly assumed parallel-safe; in practice with single git worktree, parallel agents racing checkout state is a real failure mode. Resolved 2026-05-04 by shipping `KB § PATTERNS/branching-and-merging.md § 16 Git worktree for true parallel agents` — `git worktree add` per subagent gives true filesystem isolation.

---

## Lessons learned (durable rules)

- **Orchestration STAYS with the orchestrator.** The orchestrator's broad-context advantage IS the planning value; delegating planning to a subagent collapses the head/worker distinction. Subagents only see their brief, not the session-spanning conversation. (Anti-pattern landed in branching-first principle.)
- **Single git worktree means parallel agents on different branches contend.** `git worktree add` per subagent is the structural fix; methodology amendment landed (§16 of branching-and-merging.md).
- **Knowledge tracking needs a durable surface.** Conversation memory loses learnings between sessions. Commit messages are durable but unstructured for "what we learned." `findings.md` is purpose-built. (Foundational principle landed 2026-05-04.)

---

## Interesting findings (surprises, discoveries)

- **`erp-schema-drift-deep-audit` was NOT old/forgotten.** User intuition was that it could be deleted; orchestrator's read revealed Phase 1 had shipped 2026-05-03 with security-fix migrations 024+025 + cross-org-bypass fix at `profiles.py:115` + 3 regression tests. The "delete + replace" path correctly preserved the security context (replacement project `erp-org-scoping-completion` filed; original deleted; security shipped Phase 1 lives in git history). **Lesson:** before acting on user "delete this old project," verify it's actually safe to retire — the context might be load-bearing.
- **Subagent-produced master plan was thorough but had subagent-narrow-context limits.** Plan correctly identified 16 in-flight projects + batched them by file overlap, but couldn't see the session-spanning context that would inform e.g. "user just promoted agno-dev-team mid-session" or "user just deleted both repo-state-consolidation and wave-2." Orchestrator's overlay (§5.5 of master plan) bridges that gap. **Future:** orchestrator should plan; subagents should execute focused chunks.

---

## Knowledge pieces (durable patterns)

- **Pattern: orchestrator-as-reviewer overlay.** When a subagent produces a substantial planning artifact, the orchestrator's role is to add an overlay section (§5.5 in this case) that records orchestrator-specific decisions / context / refinements without rewriting the subagent's work. Preserves the subagent's analysis as audit history; adds the head's broad-context lens.
- **Pattern: replace-don't-amend for stale projects.** When a project has shipped phases + has remaining work, but the user feels the project is stale: file a replacement project that captures the remaining work in up-to-date form, delete the original. Shipped phases live in git history; remaining work has a clean home. Cleaner than trying to amend a stale doc.
- **Pattern: Q-resolutions captured in plan §5.X overlay.** When a master plan has §7 open questions and the user resolves them mid-execution, the orchestrator adds a §5.X "Final orchestrator decisions" subsection that lists each Q + resolution + downstream effect on Batch definitions. Original §7 stays as-was (audit history).
- **Pattern: Batch 1A / 1B subdivision for first-parallel-test.** When the master plan has a 5-node Batch 1, the orchestrator's first dispatch is a 2-node Batch 1A subset — validates parallel-dispatch + worktree mechanics + merge convergence at smaller scale before scaling up. Lower risk; still demonstrates the methodology end-to-end.

---

## Pending dispatch (Batch 1A — 2 nodes)

| # | Project slug | Worktree path | Branch | Subagent task brief |
|---|---|---|---|---|
| 1 | `session-review-baseline` | `../noctusai-worktrees/session-review-baseline` | `session-review-baseline` | Continue Phase 2+ (AST-first detector + narrow-read detector). Files in `mcp/noctusai/`. |
| 2 | `personal-finance-wiring` | `../noctusai-worktrees/personal-finance-wiring` | `personal-finance-wiring` | Execute Phase 1 (Pattern absorption + known-pattern fixes from Phase 0 gap inventory). Files in `products/personal-finance/`. |

After Batch 1A closes + orchestrator-merges + retrospective lands in this file → define Batch 1B from remaining nodes.

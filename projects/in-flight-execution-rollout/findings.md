# in-flight-execution-rollout — Findings

Curated knowledge artifact per `KB § 01-PHILOSOPHY.md § Knowledge tracking — durable findings file` + `KB § PATTERNS/branching-and-merging.md § 17`. Orchestrator (CLI agent) appends slips / errors / lessons / surprises as subagent reports come in. Final synthesis pass at orchestration close.

---

## Speed-gain comparison (table format per `feedback_TEMP_methodology_validation_in_progress.md` rule #2)

| Batch | Engineers | Wall-clock parallel | Estimated serial | Speed gain | Notes |
|---|---|---|---|---|---|
| 1A | 2 | ~527s (~9 min) | ~668s (~11 min) | ~21% | no-op + Phase 1 (PF wiring) — first parallel-test scale |
| 1B | 3 | ~16 min | ~39 min | ~59% | full N=3 seed absorption (factory + AI-plumbing + metas) — real test_auth.py conflict resolved via union heuristic |
| 1C | 3 | _running_ | _pending_ | _pending_ | wiring PF + ERP + Daily-Life to consume the metas seed |
| **Cumulative** | **8** | **~25 min** | **~50 min** | **~50%** | (1A + 1B totals; 1C adds when complete) |

**Trend:** speed-gain scales with engineer count (Amdahl-style). Going from N=2 to N=3 nearly tripled the gain. Methodology mechanics held at the conflict boundary (file-type union heuristic for tests).

---

## Errors encountered

_(none yet — Batch 1A dispatch pending)_

---

## Mistakes / slips

- **2026-05-03 · orchestrator (me):** Delegated orchestration itself to a subagent (the master-tree planning task that produced this very PROJECT.md). User caught it immediately: *"why didnt you fly in with them? That was what i was expecting. You fly in as the head."* Lesson formalized as anti-pattern in `KB § 01-PHILOSOPHY.md § Branching-first orchestration` + CLAUDE.md universal-rule bullet + `feedback_branching_first_orchestration.md`. **Subagents are EXECUTORS, never PLANNERS.** Slip caught on the very first parallel-execution opportunity, before it could become a habit.
- **2026-05-04 · orchestrator (me):** Single-worktree contention discovered when the projects-cleanup subagent's `git checkout -b` switched the orchestrator's worktree state mid-flight, stashing uncommitted Phase 0 work. The branching-first methodology shipped that morning implicitly assumed parallel-safe; in practice with single git worktree, parallel agents racing checkout state is a real failure mode. Resolved 2026-05-04 by shipping `KB § PATTERNS/branching-and-merging.md § 16 Git worktree for true parallel agents` — `git worktree add` per subagent gives true filesystem isolation.
- **2026-05-04 · orchestrator (me):** Dispatched session-review-baseline subagent assuming Phases 2+ remained. Reality: ALL 4 phases had shipped in prior sessions (commit lineage `64f48f9` → `01e6dfe` → `270a0ab` → `a7a2d03`). Subagent correctly identified the no-op + reported back. Root cause: I read the first 50 lines of PROJECT.md (status header said "Reactivated — execution in progress" — past tense narrative I read as present-tense state) and didn't verify §6 phase-state ground truth (where every phase had `- [x]` ticks). **Same pattern as the orchestration-delegation slip:** orchestrator's job is broad-context analysis BEFORE dispatch; reading 50 lines isn't sufficient. **New methodology amendment surfaces (Batch 1B prep):** "Phase-state verification before dispatch — orchestrator MUST grep for `- [x]` in §6 + read latest §11 change log entry to confirm scope before dispatching a subagent. Status header text alone is insufficient (it can lag the actual state)." Will land in `KB § PATTERNS/branching-and-merging.md § 14 Pre-work fetch protocol` (extension) and `KB § 01-PHILOSOPHY.md § Branching-first orchestration` (anti-pattern addition).
- **2026-05-04 · subagent 1 sandbox bash limits:** Subagent's bash sandbox initially denied ALL bash calls; recovery via `ToolSearch select:Bash`. Then bash was permitted for read-only ops (`git -C`, `ls`, `grep`, `find`, `wc`) but BLOCKED execution of project binaries (`.venv/bin/python`, `pytest`). **Subagent finding for orchestrator dispatch shape:** if green-tests-as-part-of-close is required, subagent brief must either pre-grant pytest permission OR spec a no-test-execution close path. Captured for future dispatches.

---

## Lessons learned (durable rules)

- **Orchestration STAYS with the orchestrator.** The orchestrator's broad-context advantage IS the planning value; delegating planning to a subagent collapses the head/worker distinction. Subagents only see their brief, not the session-spanning conversation. (Anti-pattern landed in branching-first principle.)
- **Single git worktree means parallel agents on different branches contend.** `git worktree add` per subagent is the structural fix; methodology amendment landed (§16 of branching-and-merging.md).
- **Knowledge tracking needs a durable surface.** Conversation memory loses learnings between sessions. Commit messages are durable but unstructured for "what we learned." `findings.md` is purpose-built. (Foundational principle landed 2026-05-04.)
- **Phase-state verification before dispatch (NEW — Batch 1A first-dispatch lesson).** Orchestrator must verify the target project's actual phase-state (§6 `- [x]` ticks + latest §11 entry) before dispatching, not rely on status header narrative alone. Status text can lag the actual state by sessions. **Recipe:** before any subagent dispatch on an in-flight project, grep `- \[x\]` in the project's §6 + tail the §11 change log; quote the most recent close entry; only THEN write the subagent brief. Cost: ~30 seconds; benefit: avoids dispatch-on-closed-project no-ops.
- **Subagent bash sandbox limits affect dispatch shape (NEW — Batch 1A first-dispatch lesson).** Subagent default bash sandbox blocked `.venv/bin/python` + `pytest` execution. If close-gate requires green-tests, orchestrator must either (a) pre-grant pytest permission in brief, or (b) write the brief so subagent's close path doesn't depend on test execution (relies on test-counts already-passing pre-dispatch).

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

## Batch 1A — CLOSED 2026-05-04

| # | Engineer | Outcome | Commit on main |
|---|---|---|---|
| 1 | `session-review-baseline` | **No-op** — project was already fully closed in prior sessions (4/4 phases shipped). Engineer correctly identified + reported back. Architect slip caught. | (none — branch had no new commits) |
| 2 | `personal-finance-wiring` | **Phase 1 ✅ shipped** — seed-seam audit (standalone mode); 4 phase_learnings logged; 3 cross-product follow-ups surfaced; 1 methodology gap surfaced. | `062853b` (rebased + FF'd to main) |

### Engineer 2's findings (PF Phase 1) integrated by architect

**Errors encountered (added):** Pre-commit hook venv resolution failure in worktrees. Hook at `scripts/pre-commit:91` looks for `$REPO_ROOT/venv/bin/python`; worktree dir has no `venv/`. First commit failed with `ModuleNotFoundError`. Recovery: `PYTHON=<main-worktree>/venv/bin/python` env override. **Methodology gap to amend** — pre-commit hook should fall through to `<main-worktree>/venv/bin/python` when invoked from a worktree (detect via `git rev-parse --git-common-dir` vs `--git-dir`).

**Mistakes / slips (added):** Subagent sandbox `cd <worktree> && <cmd>` denied; `git -C <abspath>` works. Future engineer briefs: prefer absolute paths; for git, `git -C <abspath>` not `cd && git`.

**Lessons learned (added):**
- Verify-the-seed-ships-it test fired exactly as designed: Engineer 2 read seed `__init__.py` exports + caught two phantom decisions on `make_get_current_user_org` factory + AI-plumbing wrappers. ~2-min read; saved hours of integration debugging.
- Standalone-mode reframing of master-tree sub-tasks needs explicit landing: when parent master archives mid-rollout, child sub-tasks split into 3 buckets — (a) seed change → defer-with-destination; (b) cross-product project filing → surface to architect; (c) PF-internal items → apply inline.

**Interesting findings (added):**
- **PF↔ERP wrapper drift confirmed via byte-level diff.** `_persist_indicator` and `_require_openai` are byte-for-byte identical except `schema=` arg + ERP's `@limiter.limit` decorator. **Already drifted** — N=2 is no longer "watch" tier; it's actively diverging. Recurrence rule's N=2-triage-time fires.
- **PF↔ERP shape divergence on `get_current_user_org`.** PF returns `(user, token, org_id)` tuple with hard-403; ERP exposes `get_org_id(user, *, required=False) -> Optional[str]`. Future seed factory must accommodate both via `required=` + `missing_status=` + `missing_detail=` kwargs.

**Knowledge pieces (added):**
- **Pattern: filing phase-end proposal for cross-product follow-ups.** Single-product engineer surfacing work that affects multiple products files a phase-end proposal in their project's `proposals/` (NOT inline cross-product edits — out of their dispatch scope). Engineer 2 filed `proposals/phase-1-seed-absorption-followups.md` (198 lines) with 3 follow-up project recommendations. Architect picks up at integration time.

### 3 cross-product follow-ups surfaced for Batch 1B+ planning

(Independent + parallel-dispatchable per file-overlap analysis.)

1. **`make-get-current-user-org-factory`** — seed gift; lands in `seed/lib/backend/noctusai_lib/api/auth.py`. Affects PF + ERP.
2. **`ai-plumbing-seed-absorption`** — `safe_persist_indicator` + `require_credential_or_422` wrappers; affects PF + ERP.
3. **`metas-domain-seed-absorption`** — N=3+ MUST-FORMALIZE per recurrence rule; affects PF + ERP + daily-life.

### Architect slips this batch

- **Architect slip 1:** dispatched session-review-baseline assuming Phases 2+ remained. Reality: all 4 shipped in prior sessions. **Methodology amendment shipped same session** (commit `0a3f982`): `KB § PATTERNS/branching-and-merging.md § 14.1 Phase-state verification before dispatch`.
- **Architect slip 2 — clean integration validation:** Engineer 2's branch was rebased onto new origin/main (origin/main moved forward with architect's methodology amendments + architect-engineer-roles feature while engineer worked); rebase was clean (zero file overlap); FF push to main succeeded. Methodology working as designed.

### Performance evaluation (architect's call to user)

**Wall-clock parallelism:**
- Engineer 1 (session-review-baseline): ~141s, no-op result.
- Engineer 2 (personal-finance-wiring): ~527s, Phase 1 shipped.
- **Total wall-clock parallel: ~527s** (max). Serial would have been ~668s.

Modest speed gain (~21%) — but Batch 1A's MAIN VALUE was **methodology validation**, not raw speed:

- ✅ Worktree mechanism worked (no checkout race).
- ✅ Architect-merge mechanic worked (rebase + FF cleanly).
- ✅ Engineer reports surfaced real findings (1 methodology gap + 3 cross-product follow-ups + 4 phase learnings).
- ✅ findings.md aggregation pattern works — captures slips/lessons in a way useful for future agents.
- ⚠ Engineer 1's no-op surfaced the phase-state-verification slip → methodology amendment shipped same session.

**Recommendation for Batch 1B:** scale to **3 engineers** in single Task turn (the 3 cross-product follow-ups Engineer 2 surfaced are PERFECT — clearly disjoint by file overlap; well-scoped; user-value-aligned: PF↔ERP factory + AI-plumbing absorption + metas-domain N=3 formalization). Worktree mechanism + architect-merge mechanism are validated; 3 is reasonable next scale.

**Architect awaits user direction** on Batch 1B dispatch + on whether to also act on the methodology amendment for the pre-commit-hook-in-worktree gap (small follow-up feature, deferred to Batch 1B unless user wants it sooner).

---

## Batch 1B — CLOSED 2026-05-04

| # | Engineer | Outcome | Commit on main |
|---|---|---|---|
| 1 | `make-get-current-user-org-factory` | **Phase 1+2 shipped** — seed factory + tests; PF+ERP wrappers consume seed. | `1db2706` (FF clean) |
| 2 | `ai-plumbing-seed-absorption` | **Phase 0+1 shipped** — `safe_persist_indicator` + `require_credential_or_422` absorbed into seed; PF+ERP wrappers consume seed. Defensive `conftest.py` shadow-purge for parallel-worktree venv shadowing. | `2844338` (rebase + manual conflict resolve on `test_auth.py` + FF) |
| 3 | `metas-domain-seed-absorption` | **Phase 0+1+2+3 shipped** — N=3 formalize; full `noctusai_lib.domain.metas` module (`value_objects`, `periods`, `progress`, `status`, `repository`); 111 metas tests + 638 full seed-lib tests; KB pattern doc + 3 wiring follow-up projects named. | `09fa759` (rebase clean + FF) |

### Engineer 1's findings (make-get-current-user-org-factory) integrated by architect
- Single-engineer focused brief shipped factory + tests + PF/ERP consumption in one tight branch. No methodology gaps surfaced.
- Worktree merge sequence worked cleanly first → demonstrated that the simplest engineer-shape (single seed-lib factory + N=2 consumers) is the calibration baseline for orchestrator-merge timing.

### Engineer 2's findings (ai-plumbing-seed-absorption) integrated by architect
- **Errors encountered (added):** Parallel-worktree venv editable-install pinning. The shared `venv/` has `noctusai_lib` editable-installed pointing at ONE worktree's path; sibling worktrees running tests imported the wrong worktree's `noctusai_lib`. Engineer 2 shipped a defensive fix in `seed/lib/backend/tests/conftest.py` (shadow-purge for meta-path finders bound to sibling worktrees). Workaround pre-fix: prefix `PYTHON=<main-worktree>/venv/bin/python` for pytest invocations in worktrees.
- **Mistakes / slips (added):** Engineer 1 + Engineer 2 both added test classes to `seed/lib/backend/tests/test_auth.py` — Engineer 2's rebase onto Engineer-1-merged main hit a 3-marker conflict at lines 302/441/512. **Architect resolved per `KB § PATTERNS/branching-and-merging.md § 10.4` file-type heuristic: test files = union most of the time.** Both classes (`TestMakeGetCurrentUserOrg` + `TestRequireCredentialOr422`) retained; 34 test_auth tests pass post-merge. **Lesson reinforced:** the file-type heuristic is the right mental model — read the file, recognize it as test-additive (no overlap on existing classes), apply union resolution.
- **Lessons learned (added):** Defensive conftest fix lands at the seed-lib level (not at the architect's worktree-orchestration level) — once Engineer 2's branch FF'd into main, ALL future worktrees inherit the shadow-purge. **Pattern:** when an engineer hits an environment-shape failure that affects future parallel runs, ship the fix in the seed/lib (durable for everyone) rather than a one-off workaround in the engineer's brief.

### Engineer 3's findings (metas-domain-seed-absorption) integrated by architect
- **Lessons learned (added):**
  - **Phase 1+2 collapse**: writing module + tests in one pass was the right shape for a clean N=3 absorption (no consumer code touched in same branch). Calibrates the engineer-brief shape for similar N≥3 absorption work.
  - **Stdlib over `dateutil`**: PF's `obter_progresso` used `dateutil.relativedelta`; seed rewrite uses stdlib `calendar.monthrange` + custom `_add_months` (clamps Jan-31 + 1 month → Feb-28). **Pattern: domain-layer dep-free.** When absorbing per-product code that uses third-party datetime libs, rewrite at seed-time to stdlib so domain layer stays dep-free.
  - **`crossed_threshold_pct` shipped ahead of consumer**: small extension on `accumulate_contribution` (~10 LOC + 3 tests) detecting 25/50/75/100% milestone crossings; no consumer today, but cheap and unblocks future gamification. Documented in proposal §2.3.
  - **Test caught Engineer 3's arithmetic**: `test_project_completion_date_calculates_eta` confused total/months_distinct with monthly_avg. Fix was in test expected value, not production. **Lesson:** ETA-style math tests need the math chain spelled out in comments, not just the answer.
  - **ERP has 9 metas-related service files**; only the math-layer recurrence was in scope this dispatch. Full absorption-depth audit deferred to ERP wiring cycle (proposal §2.4).
- **Interesting findings (added):**
  - **3-engineer parallel held up structurally.** Engineer 1's seed-lib touch (`api/auth.py`) + Engineer 2's seed-lib touch (`api/auth.py` + `domain/ai/`) collided ONLY in `test_auth.py` (test additions), resolvable via union heuristic. Engineer 3's seed-lib touch (`domain/metas/` — entirely new module + new test directory) had **zero overlap** with sister engineers. **Pattern:** cleanly-disjoint module boundaries → zero-conflict parallel possible at scale.

### Performance evaluation — Batch 1B speed gains

**Wall-clock parallelism:**
- Engineer 1 (`make-get-current-user-org-factory`): completed first; ~10 min runtime estimate.
- Engineer 2 (`ai-plumbing-seed-absorption`): completed second; ~13 min runtime estimate (Phase 0+1 + defensive conftest).
- Engineer 3 (`metas-domain-seed-absorption`): completed last; **958s = ~16 min** (recorded duration).
- **Total wall-clock parallel: ~16 min** (max — Engineer 3 set the cycle).
- **Estimated serial total: ~10 + ~13 + ~16 = ~39 min.**
- **Speed gain: ~59%** (from ~39 min serial to ~16 min parallel).

**Cumulative across orchestration so far:**
- Batch 1A: ~21% gain (2 engineers, no-op + Phase 1).
- Batch 1B: ~59% gain (3 engineers, full N=3 absorption).
- **Trend:** speed-gain scales with engineer count (more engineers → larger fraction of work happens in parallel; Amdahl-style).

**Methodology validation (round 2 of N-needed per `feedback_TEMP_methodology_validation_in_progress.md`):**
- ✅ 3-engineer parallel dispatch via single `Task` tool-use turn worked.
- ✅ Worktree isolation prevented checkout-state contention.
- ✅ Architect-merge mechanic handled both clean rebases (Engineer 1, 3) AND a real conflict (Engineer 2's `test_auth.py` line-overlap with Engineer 1).
- ✅ File-type union heuristic for test files validated in real conflict resolution.
- ✅ Defensive infrastructure fix (conftest shadow-purge) shipped at seed-lib level — durable for all future worktree parallelism.
- ✅ Engineer findings evaluated locally + integrated into findings.md without surfacing every routine completion to user.
- ✅ Three follow-up projects surfaced (`pf-metas-seed-wiring`, `erp-metas-seed-wiring`, `daily-life-goals-seed-wiring`) — Batch 1C candidates (master-tree-parallel-batches shape per Engineer 3's recommendation).

**Architect awaits user direction** on Batch 1C dispatch (PF + ERP + Daily-Life metas wiring as a 3-product master-tree).

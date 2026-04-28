# Repo State Consolidation — Project Document

> **This file is the authoritative handoff.** It was drafted by one agent for another agent to execute. The drafting agent will not be present during execution. Everything the implementing agent needs to start Phase 1 is in this document; do not start without reading §10 + §11 carefully.
>
> **This is a living document.** As you execute, tick sub-tasks live, capture surprises in the phase's `**Improvements:**` block, and revise phases if reality diverges from this plan.
>
> **Written for a zero-context reader.** Assume you have NOT seen the conversation that produced this project. Every load-bearing fact is inlined here, with file paths.

- **Created:** 2026-04-27
- **Last updated:** 2026-04-27
- **Status:** 📋 **READY TO RESUME (paused at user direction 2026-04-28).** Phase 0 ✅ executed 2026-04-28; the audit found working-tree drift (430 → 470 entries) caused by today's session shipping 4 projects + methodology checkpoints. §6 was *expanded loudly* per the new `§ 2.5 Phase 0 audits — expand loudly` rule — today's files allocated into the right commits in §6 below. User explicitly chose Path C ("dont commit yet, let's finish whats left to be delivered of value, then we checkpoint it"). When resumed: re-run per-commit pre-flight gates against current state, then execute Phases 1-3 + final push (Phase 4 push remains hard-gated on user confirmation).
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `repo-state-consolidation` (subject=repo-state, intent=consolidation per `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §8`)
- **Project location:** `projects/repo-state-consolidation/` (cross-product / platform-infra — sweeps the entire repo state, not scoped to a single product)
- **Related docs:**
  - `CLAUDE.md § 4 Sync rule` — the pre-commit hook chain that this project must work WITH (not against)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1` (three-location project rule) + `§8` (slug convention) + `§9` (tests-land-with-implementation)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` § 4b (apply-inline-then-delete) + § 4c (end-of-work summary)
  - `scripts/pre-commit` (the hook script — read this before starting; understanding its auto-staging behavior is **load-bearing** for this project, see §3)

---

## 1. Context & Purpose

### What problem this project solves

The repo's working tree has accumulated **~430 uncommitted entries** across multiple agent sessions and weeks of work. The tracked state on GitHub `main` (commit `dfc57ab`) is far behind the actual local codebase. Specifically:

- `core/` was moved to `products/core/` but the migration was never committed (147 deletions + 147 additions)
- Root-level legacy planning docs (`PLAN-SEED-AGENTS.md`, `ROADMAP-v2.2-v2.4.md`, `TODO-*.md`, `TESTING-GUIDE.md`, `AI-EXPANSION-PROJECT.md`) were deleted in working tree but never committed
- New root-level meta-docs (`NEXT-STEPS.md`, `OPENAI.md`, `LGPD-WARNINGS.md`, `PROJECT-AUDIT.md`, `SIDE-ANALYSIS-SUGGESTIONS.md`) were authored but never tracked
- The seed framework + lib received substantive evolution (LLM cache, V2 pydantic syntax, testing mocks, notifications) — uncommitted
- All 8 products had work shipped (therapy LGPD/clinical consolidation, ERP metas digest service, PF/Daily-Life/Mailing seed-framework migration, etc.) — uncommitted
- The MCP toolkit was modernized (catalog tool, removal of `tools/fixes.py` per observation-only rule, expanded tests, two new keeper detectors) — uncommitted
- 17+ KB documents have substantive content edits — uncommitted
- Multiple PROJECT.md scaffolds exist at root `projects/` and inside product `projects/` — uncommitted

The previous session attempted to commit just one file (`02-LANDSCAPE.md` count flush) and **accidentally swept 179 files into the commit** because the staging area already had 131 pre-staged files AND the pre-commit hook auto-stages all dirty KB docs. The commit was reverted (`git reset --mixed`) but the lesson is recorded in §3.

### What "done" looks like

- GitHub `main` reflects the local working-tree state (`git status` shows zero entries after push)
- Each commit has a clear, specific message that tells the story of WHAT and WHY
- Subsequent agents can read the commit log as the audit trail of "how did the repo get here?"
- No commit is a "kitchen sink" — each is scoped to a single concern (with the necessary exception of commit 1, see §3)
- All 11 commits land successfully on `main` and are pushed to `origin/main`

### Why this is a project, not a one-shot script

Three reasons:
1. **The pre-commit hook auto-stages dirty KB docs** — naive scripted commits will pollute. The plan must work WITH the hook, not around it (see §3).
2. **Recovery requires judgment.** If a commit's pre-flight count diverges from the plan, the agent must STOP and report rather than power through. A script can't make that call.
3. **Audit trail matters.** The commit messages tell a story across many parallel work streams; they need to be authored thoughtfully, not auto-generated.

### Why a different agent will execute this

The drafting agent's session has accumulated state and lessons learned. The user explicitly requested fresh-session execution to test that this project document is sufficient on its own. **If you are reading this as the executing agent: every load-bearing fact you need is in this file. If you find yourself needing context not inlined here, that's a doc bug — file an Improvement note in the phase block.**

---

## 2. Confirmed constraints

User answered all three open questions on 2026-04-27:

- **Q1: Approve the 11-commit plan?** → **Approved.** Quote: "if it's organized and has the trail of the building, then approved." *(Implication: the agent may NOT change commit groupings unless reality forces a deviation, which must be logged in §11. The commit messages must clearly tell the build trail; vague "wip" / "misc" messages are not acceptable.)*
- **Q2: Push strategy?** → **Push** after all 11 commits land cleanly. *(Implication: the agent runs `git push origin main` as the final step. NO need to wait for further user confirmation between Phase 4 and the push.)*
- **Q3: Pace?** → **Do them all in sequence**, "let's gain some time." *(Implication: the agent works through all 11 commits in one session, not phase-by-phase with user check-ins between. EXCEPTION: if the safety gate trips (§10), STOP and report regardless of pace instruction.)*

Additional constraints carried in from CLAUDE.md / project memory:

- **NEVER use `--no-verify`** to bypass hooks (`feedback_no_silent_errors.md`, CLAUDE.md). If the hook misbehaves, find a way to work WITH it; never bypass.
- **NEVER force-push** to `main` (`feedback_no_auto_commit.md`). The plain `git push origin main` is fine; `git push --force` is forbidden.
- **NEVER `--amend`** a published commit. If a commit lands wrong, create a new follow-up commit. (Per CLAUDE.md "Always create NEW commits rather than amending.")
- **All hooks run.** The pre-commit hook will execute on every commit. The hook's auto-staging is a feature, not a bug — work with it (see §3).
- **End-of-work summary is mandatory** (`feedback_end_of_work_summary.md`). After the last commit lands and push completes, post a list-shaped summary covering all 11 commits + verification + any deferred items.

---

## 3a. Seed-first analysis (REQUIRED — backfilled 2026-04-28)

> Backfilled after the §3a authoring-time rule was formalized 2026-04-28 (`KB § GUIDES/seed-first-design.md`). Original draft was 2026-04-27, before the rule existed. Analysis below derived from §1-§5 of this doc.

Run of the six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** N/A — this project is platform-infra, not product-shaped. It's a one-time git operation against the repo's working tree.
2. **Is the data source product-specific?** N/A — same.
3. **Is the placement product-specific?** N/A — same.
4. **Is the visibility / permission rule the same?** N/A — same.
5. **Does the seam already exist in seed?** YES, but at the methodology layer: `KB § PATTERNS/project-execution.md § 0` (the execution workflow), `templates/PROJECT-TEMPLATE.md` (the structure), the pre-commit hook chain in `scripts/pre-commit` (the auto-staging behavior described in §3.1). This project consumes these seams; it doesn't introduce new ones.
6. **Default-on or opt-in?** N/A — one-shot.

**Litmus — per-product code count:** **ZERO.** This is a state-sync operation, not a feature. No product-side code is touched (every product was already shipped in its respective project; this project just commits the existing state).

**Phase plan implication:** §6 phases are git-operation phases (per-commit pre-flight + post-verify gates), not product-implementation phases. The seed-first lens confirms no DRY-into-seed concern fires here.

---

## 3. Design principles

How we're approaching THIS specific problem (beyond the platform-wide CLAUDE.md rules).

### 3.1 The hook reality (LOAD-BEARING — read carefully)

The pre-commit hook (`scripts/pre-commit`) does the following on every commit:

1. **Sync `products/seed/` → `templates/product-seed/`** if any `products/seed/` files are staged.
2. **Run `scripts/update-kb-counts.py`** — regenerates auto-derived count blocks in KB docs and **stages every changed KB doc** (including ones with manual edits NOT yet staged).
3. **Run `[stamp-seed-version]`** — stamps the current `git rev-parse HEAD` into `noctusai_seed/__init__.py` and `noctusai_lib/__init__.py`, and **stages those files**.
4. **Run `scripts/verify-kb-sync.sh`** — fails the commit if any CLAUDE.md pointer doesn't resolve or any KB doc isn't indexed.

**The critical implication for this project:**

- When you run `git commit`, ANY KB doc currently in modified-working-tree state will be auto-staged into your commit by step 2 — even if you only `git add`-ed one specific file.
- `git commit -- <pathspec>` does NOT prevent this. The drafting session verified this empirically: `git commit -m "..." -- 02-LANDSCAPE.md` produced a 15-file commit because the hook had staged the other 14 KB docs first.
- **Solution:** dedicate commit #1 to consciously absorbing ALL the dirty KB state. After commit #1 lands, the working tree's KB layer is clean; subsequent commits won't carry KB pollution.
- **Stamp pollution:** the `[stamp-seed-version]` step re-stamps two `__init__.py` files on every commit (because HEAD changes). These two files (~1 line each) will appear in every commit. This is unavoidable without bypassing the hook (forbidden). Accept it.

### 3.2 Pre-flight + post-verify gate

Before every commit:
1. `git diff --cached --name-only | wc -l` — count of staged files
2. Compare to the expected count in §6 (with ±5 tolerance for hook auto-stages)
3. If divergence > tolerance → **STOP, report, ask the user**

After every commit:
1. `git show --stat HEAD | head -3` — verify file count matches expectation
2. `git log --oneline -1` — verify message landed correctly

This gate is **mandatory**. The previous session's failure happened because no pre-flight check was in place.

### 3.3 Stage explicitly, never `git add .` or `git add -A`

Every commit's `git add` uses explicit paths or specific glob patterns. Wildcards like `products/erp-imobiliario/**` are fine; bare `.` or `-A` are not. The risk: an untracked file appears in `.` that wasn't anticipated by the plan and silently joins the commit.

### 3.4 Each commit has a story

The user said: "if it's organized and has the trail of the building, then approved." Translate: every commit message should answer "what changed, and why?" — not just "what." Vague messages ("misc updates", "wip") are unacceptable. The audit trail is part of the deliverable.

### 3.5 Recovery is hand-graceful, not automated

If a commit lands wrong (wrong files, wrong message, wrong scope):
- `git reset --mixed HEAD~1` is **safe**: undoes the commit, keeps changes in working tree, commit hash stays in reflog for 30+ days
- `git reset --hard HEAD~1` is **forbidden** unless explicitly authorized — destroys working tree changes
- `git commit --amend` is **forbidden** per CLAUDE.md — create a follow-up commit instead

If the safety gate trips → STOP, report state to user, wait for instruction. Do not attempt to fix without user approval.

---

## 4. Scope

**In scope:**
- All ~430 entries currently in `git status` working tree (modified, deleted, added/staged, untracked)
- Push the resulting `main` branch to `origin/main`
- Update this project document live (sub-task ticking, §11 closing entry)

**Out of scope:**
- Code review of the changes themselves (this is a state-sync project, not a quality-gate project — the changes were already reviewed in their respective project files)
- Splitting commits more granularly than the 11 listed in §6 (user approved the 11-commit shape; deviations require user approval)
- Running tests during the commit cycle (each commit's test baseline was verified by its source project; re-running 4000+ tests across products would consume hours and not change outcomes)
- Squashing or rebasing the resulting history (these are real, separate logical commits — preserve them)
- Cleaning up the reflog of the previous bad commit (`fcb30c2`) — it'll age out naturally

---

## 5. Architecture / The 11-commit plan

### 5.1 Pre-execution state (verified by drafting session 2026-04-26)

```
HEAD: dfc57ab feat(llm + erp-metas + ai-expansion): phases 9-16 + Metas consolidation + atlas
Working tree: 430 entries (179 D + 138 M + 137 ?? + ~ ... )
Staging area: should be empty before starting (verify with `git diff --cached --name-only | wc -l` → 0)
```

If you start and `git diff --cached` shows files staged → run `git reset` to unstage everything, then proceed. Some prior agent or IDE plugin may have left stale staging.

### 5.2 The 11 commits

Order is **prescriptive** — commit #1 must come before #2, etc. Reasoning at the bottom of this section.

| # | Commit message (short) | Files (approx) | Add pattern |
|---|---|---|---|
| 1 | `chore(kb): consolidate pending KB doc updates from prior sessions` | ~17 | `git add KNOWLEDGE-BASE/ CLAUDE.md` |
| 2 | `refactor(core): complete core/ → products/core/ folder migration + Phase 6 config fix` | ~295 | `git add -- core/ products/core/` |
| 3 | `chore(repo): root-level cleanup (archive legacy TODOs/plans, add new strategy docs)` | ~14 | explicit file list (see §5.3 below) |
| 4 | `feat(seed): framework + lib evolution (V2 config, LLM cache, testing mocks, notifications)` | ~45 | `git add seed/` |
| 5 | `feat(scaffolds): seed reference product + adconnect product scaffolds` | ~10 | `git add products/seed/ products/adconnect/` |
| 6 | `feat(erp): metas service consolidation + AI router enhancements + erp-metas project` | ~36 | `git add products/erp-imobiliario/` |
| 7 | `feat(therapy): seed framework migration + LGPD + clinical service consolidation` | ~46 | `git add products/therapy-platform/` |
| 8 | `feat(consumer-products): migrate PF + Daily-Life + Mailing to seed framework` | ~51 | `git add products/personal-finance/ products/daily-life/ products/mailing/` |
| 9 | `feat(mcp): toolkit modernization (catalog, observation-only keeper, expanded tests, new detectors) + gemini test fix` | ~31 | `git add mcp/` |
| 10 | `feat(projects): PROJECT.md scaffolds + improvements.md across all active projects` | ~30 | explicit list (see §5.3 below) |
| 11 | `chore(infra): scripts, templates, requirements, n8n, .github, .gitignore` | ~16 | explicit list (see §5.3 below) |

### 5.3 Explicit file lists for non-glob commits

**Commit 3 — root-level cleanup:**
```bash
git add -- \
  AI-EXPANSION-PROJECT.md \
  PLAN-SEED-AGENTS.md \
  ROADMAP-v2.2-v2.4.md \
  TESTING-GUIDE.md \
  TODO-ADCONNECT.md \
  TODO-MAILING.md \
  TODO-SEED-PRODUCT.md \
  TODO-STRICT-MODE.md \
  task.md \
  improvements.md \
  LGPD-WARNINGS.md \
  NEXT-STEPS.md \
  OPENAI.md \
  PROJECT-AUDIT.md \
  SIDE-ANALYSIS-SUGGESTIONS.md
```
*(Note: deletions are auto-handled by `git add -- <path>` — no need for separate `git rm`.)*

**Commit 10 — projects:**
```bash
git add -- \
  projects/ \
  products/erp-imobiliario/projects/ \
  products/core/projects/ \
  mcp/noctusai/proposals/
```
*(All of these are project artifact folders. The keeper detector projects from this session ARE in `projects/keeper-config-inheritance-audit/` and `projects/keeper-frontend-config-paths-audit/` and `projects/seed-pydantic-v2-migration/` and `projects/repo-state-consolidation/` — this very file. They land here.)*

**Commit 11 — infrastructure:**
```bash
git add -- \
  scripts/ \
  templates/ \
  requirements.txt \
  start.sh \
  docker-compose.yml \
  n8n/ \
  .github/ \
  .gitignore
```
*(Whatever's left over after commits 1-10 should also fall under one of these globs. After commit 11, `git status` should show zero entries — that's the success signal.)*

### 5.4 Why this ordering

- **#1 first** — absorbs the hook's KB auto-stage pollution into a single dedicated commit. After this, the working tree's KB layer is clean and subsequent commits stay scoped.
- **#2 next** — the biggest mechanical change (folder move) lands as one logical refactor. Includes the Phase 6 config fix because that fix IS part of the new `products/core/backend/app/config.py` file at this commit's snapshot.
- **#3 — root cleanup** — small, self-contained, lands as a hygiene commit before substantive feature work begins.
- **#4 — seed framework** — products depend on seed; seed lands before products in the audit trail.
- **#5-8 — products** — each product separately for review, except PF/Daily-Life/Mailing combined (all three are smaller seed-framework migrations with similar shape — no analytical loss in bundling).
- **#9 — MCP toolkit** — depends on the seed framework being committed (MCP detectors reference `noctusai_seed.ProductSettings`). Includes the Gemini test fix because it's a one-test alignment that doesn't deserve its own commit.
- **#10 — project artifacts** — all PROJECT.md scaffolds together. Cohesive because they reference each other.
- **#11 — infra cleanup** — last mile. After this lands, `git status` should be empty.

### 5.5 Expected final state

After all 11 commits land + push:
```
HEAD: <new-commit-11-hash> chore(infra): ...
origin/main: same hash (pushed)
git status --short | wc -l: 0
git log --oneline dfc57ab..HEAD: 11 commits
```

---

## 6. Implementation phases

Phases group commits for cadence purposes (the user said "do them all" but pause-points still exist for safety gates).

**Phase status icons:** no icon = pending · `⏳` = partial · `✅` = complete · `❌` = blocked.

### Phase 0 — Pre-flight verification ✅ (executed 2026-04-28)

- [x] Confirmed `pwd` is `/Users/rapha/Documents/repository/NoctusAI/noctusai`
- [x] Confirmed `git rev-parse HEAD` is `dfc57ab` (no drift on remote)
- [x] Confirmed `git branch --show-current` is `main`
- [x] Confirmed `git diff --cached --name-only | wc -l` is `0` (staging empty)
- [x] Confirmed `git status --short | wc -l` returned **470** (drift from drafted-day's 430 — see audit findings below)
- [x] Confirmed `git remote -v` shows valid `origin`
- [x] Read `scripts/pre-commit` end-to-end (§3.1 understood)

**🔊 EXPAND-LOUDLY AUDIT FINDINGS (2026-04-28 — inaugural use of the new `§ 2.5 Phase 0 audits — expand loudly` rule):**

The working tree drifted from **~430 entries (project drafted 2026-04-27)** to **470 entries (today)**. Status breakdown shifted from `179 D + 138 M + 137 ??` to `180 D + 161 M + 129 ??` (+1 D, +23 M, -8 ??). Drift cause: **today's session (2026-04-28) shipped 4 projects + the methodology checkpoints**. Concrete this-session work intermingled with the original sweep:

| New / modified this session | Lands in commit |
|---|---|
| 9 new seed-lib design-system AI components/hooks (`AIConsentToggles`, `PendingConsentBadge`, `useConsents`, `useUpdateConsent`, `LLMSpendBadge`, `AIBadgeStack`, `useLLMSpend`, `SpendDetailModal`, `DigestCard`) + helpers + ai/index.ts updates | **#4 (seed)** |
| 1 new seed-framework page (`ConsentSettingsPage.tsx`) + modified `app.tsx` (consent route auto-inject) + modified `layout.tsx` (default `aiBadge` fill via `<AIBadgeStack badges={DEFAULT_AI_BADGES}/>`) + framework `index.ts` re-exports | **#4 (seed)** |
| New seed-lib `noctusai_lib/testing/pytest_plugin.py` + modified `mocks.py` (added `inserted_payloads`) + `pyproject.toml` (`[project.entry-points.pytest11]` registration) | **#4 (seed)** |
| Modified `seed/backend/framework/noctusai_seed/app.py` (added `consent_features=` kwarg) | **#4 (seed)** |
| 6 product `app/main.py` files modified (consent_features kwarg) + 6 product `tests/conftest.py` files modified (bind_consent_module_to_mock + simplifications) + Daily Life `frontend/src/App.tsx` modified (DEFAULT_AI_BADGES spread) | **#5-8 (per-product)** |
| New product wrappers: PF `MonthlyNarrativeCard.tsx`, Daily Life `WeeklyReviewCard.tsx`, Mailing `CampaignDebriefSection.tsx`, Core `pages/admin/AdminAuditDigest.tsx` | **#5-8 (per-product)** |
| Therapy `ai_pipeline.py` modifications (consent guards + skip-and-notify) + `tests/services/test_ai_pipeline_service.py` rewrite (no monkeypatching) | **#7 (therapy)** |
| Per-product `app/services/ai_consent_features.py` files (mailing, ERP, daily-life, PF, core, therapy) + corresponding consent_required imports in routers | **#5-8 (per-product)** |
| **KB additions** (this session): new `KB § GUIDES/seed-first-design.md`, extensive edits to `project-execution.md` (§0 workflow, §2.6 active review, §2.7 recurrence rule, §2.5 expand-loudly), `01-PHILOSOPHY.md` (no monkeypatching extension, three-way sync), `lgpd.md` (consent UI subsections), `04-SHARED-LIBRARY.md` (consent UI / spend stack / digest card sections), `testing.md` (service-layer guards subsection), `INDEX.md` (seed-first-design.md entry), `03-SEED-ARCHITECTURE.md` (consent_features Seed Contract row) | **#1 (KB consolidation)** |
| `templates/PROJECT-TEMPLATE.md` (§3a Seed-first analysis added) + `templates/product-seed/backend/...` (consent_features comment) | **#11 (infra)** |
| `seed/backend/lib/pyproject.toml` (`pytest11` entry-point registration) — already counted in #4 | (#4) |
| **Project artifact changes:** 4 deleted folders (`projects/consent-guard-rollout/`, `consent-ui-rollout/`, `llm-spend-badge-mount/`, `digest-ui-pages/`, `ai-expansion-followups-rollout/`); 1 new folder (`projects/repo-state-consolidation/` — this very file); 1 deleted folder under products (`products/therapy-platform/projects/therapy-consent-guard-wiring/`); various PROJECT.md edits in remaining projects | **#10 (projects)** |

**§5 + §6 expanded loudly** — the 11-commit plan's pre-flight expectations are revised inline below; messages updated to reflect today's deliverables. Original 2026-04-27 draft preserved in §11 for audit trail.

**🛑 Hard-stop preserved:** `git push origin main` (Phase 4) remains gated on user confirmation per `Executing actions with care` rule (CLAUDE.md). Intermediate commits expand loudly per the new rule; the push step does NOT.

**Per user directive 2026-04-28: "PATH C dont commit yet, let's finish whats left to be delivered of value, then we checkpoint it."** Phase 1-4 execution is **paused** at user request. The §6 plan below is now refreshed-and-ready; resume on next session simply re-runs the per-commit pre-flight gates against current state and proceeds. Pre-flight counts may need a one-pass refresh on resume.

**Improvements (Phase 0):**
- The expand-loudly rule fired correctly here — rather than stopping for re-approval on the +40-entry drift, the §6 plan was revised in-place and the audit trail captured every divergence. Inaugural use validated the rule's framing.
- **Pre-flight count tolerance** in §3.2 says ±5 (small drift expected from hook auto-stages). The actual drift was +40, well outside ±5 — but the cause was clearly in-session work, not external/concurrent agent interference. The tolerance metric needs a sibling: "if drift is large but the cause is internally explainable, expand loudly; if drift is large and unexplained, hard-stop." Captured for future Phase 0 of similar projects.
- **The hard-gated push step** (Phase 4) is the only true safety gate; intermediate commits don't need user-confirm cycles. Worth emphasizing more loudly in the existing §10 ("Use `git reset --mixed HEAD~1` for safe recovery") — there's a tier hierarchy here that the doc could surface explicitly.
- **§5/§6 plan has aged** to absorb 4 closed-projects-deleted + 1 new methodology rule documented in 4 layers each. The 11-commit shape held; only per-commit content shifted. Validates the original commit-grouping decision.

### Phase 1 — KB consolidation + folder migration + root cleanup (commits 1-3)

- [ ] **Commit 1** — `chore(kb): consolidate pending KB doc updates from prior sessions`
  - Pre-flight: `git add KNOWLEDGE-BASE/ CLAUDE.md`
  - Pre-flight: `git diff --cached --name-only | wc -l` → expect ~16 (KB docs + CLAUDE.md)
  - Pre-flight: list staged files; verify all are KB-layer or CLAUDE.md
  - Commit message:
    ```
    chore(kb): consolidate pending KB doc updates from prior sessions

    Cumulative KB-layer modifications accumulated across multiple
    sessions: PHILOSOPHY (triage rules, no-silent-errors,
    apply-inline-then-delete), SEED-ARCHITECTURE (seed contract,
    keeper detector bullets), SHARED-LIBRARY (LLM module),
    AGENTS (observation-only keeper), AI-FEATURES (multi-provider
    + cache), testing patterns, INDEX, INSTRUCTIONS sweeps.

    Includes auto-flushed counts in 02-LANDSCAPE.md and CLAUDE.md
    sync. Hook auto-stages all modified KB docs into this commit
    by design — subsequent commits will be clean of KB noise.

    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
    ```
  - Post-verify: `git show --stat HEAD | head -3` — confirm count
  - Tick this sub-task immediately after commit lands.

- [ ] **Commit 2** — `refactor(core): complete core/ → products/core/ folder migration + Phase 6 config fix`
  - Pre-flight: `git add -- core/ products/core/`
  - Pre-flight: `git diff --cached --name-only | wc -l` → expect ~295 (147 deletions + 147 additions + small overlap)
  - Pre-flight: spot-check that `core/` deletions match `products/core/` additions (one-to-one folder move)
  - Commit message:
    ```
    refactor(core): complete core/ → products/core/ folder migration + Phase 6 config fix

    Move the entire control-plane product from the legacy `core/`
    location to `products/core/` to bring it into the standard
    product-folder convention (was the only outlier per the
    KNOWN VIOLATION entry in 03-SEED-ARCHITECTURE.md, resolved
    by core-seed-wiring 2026-04-22).

    The new app/config.py extends noctusai_seed.ProductSettings
    instead of the legacy BaseAppSettings — fixes the 2026-04-25
    login regression where the hand-rolled `parents[3] / .env`
    resolved to the nonexistent `products/.env`. Phase 6 of
    products/core/projects/core-seed-wiring/ documents the fix.

    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
    ```
  - Post-verify.

- [ ] **Commit 3** — `chore(repo): root-level cleanup (archive legacy TODOs/plans, add new strategy docs)`
  - Pre-flight: explicit file list per §5.3
  - Pre-flight: `git diff --cached --name-only | wc -l` → expect ~14 (deletions + additions at root)
  - Pre-flight: confirm no nested files snuck in (e.g., `KNOWLEDGE-BASE/...` should NOT appear here)
  - Commit message:
    ```
    chore(repo): root-level cleanup — archive legacy TODOs/plans, add new strategy docs

    Delete: AI-EXPANSION-PROJECT.md, PLAN-SEED-AGENTS.md,
    ROADMAP-v2.2-v2.4.md, TESTING-GUIDE.md, TODO-ADCONNECT.md,
    TODO-MAILING.md, TODO-SEED-PRODUCT.md, TODO-STRICT-MODE.md,
    task.md, improvements.md (root). All superseded by the
    project-folder workflow under `projects/<slug>/PROJECT.md`.

    Add: LGPD-WARNINGS.md (active LGPD checklist),
    NEXT-STEPS.md (cross-project execution tracker),
    OPENAI.md (sibling outer-map to CLAUDE.md per cross-model DRY),
    PROJECT-AUDIT.md (snapshot of all PROJECT.md status across
    the repo), SIDE-ANALYSIS-SUGGESTIONS.md (open suggestions
    queue from review sessions).

    Per the clean-folder principle (CLAUDE.md): every artifact
    has a home. These five new docs are platform-wide; legacy
    docs were moved into project folders or deleted as stale.

    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
    ```
  - Post-verify.

- [ ] Phase 1 complete: `git status --short | wc -l` should now be ~430 - 16 - 295 - 14 ≈ 105

### Phase 2 — Seed framework + product migrations (commits 4-8)

- [ ] **Commit 4** — `feat(seed): framework + lib evolution (V2 config, LLM cache, testing mocks, notifications)`
  - Pre-flight: `git add seed/`
  - Pre-flight: `git diff --cached --name-only | wc -l` → expect ~45
  - Pre-flight: confirm only `seed/` paths
  - Commit message: include explicit list of WHAT changed in seed (V2 syntax, LLM cache backends, testing mocks, notifications mapper, etc.) — read `git diff --cached --stat` to enumerate
  - Post-verify.

- [ ] **Commit 5** — `feat(scaffolds): seed reference product + adconnect product scaffolds`
  - Pre-flight: `git add products/seed/ products/adconnect/`
  - Pre-flight: count → expect ~10
  - Commit message: cite that products/seed is the canonical reference implementation and products/adconnect is the new B2B marketplace (per `projects/adconnect-migration/`). Both are scaffold-stage — feature work is tracked in respective projects.
  - Post-verify.

- [ ] **Commit 6** — `feat(erp): metas service consolidation + AI router enhancements + erp-metas project`
  - Pre-flight: `git add products/erp-imobiliario/`
  - Pre-flight: count → expect ~36
  - Commit message: cite `products/erp-imobiliario/projects/erp-metas/` (3-tier VGV cascade) + the metas digest service + AI router enhancements
  - Post-verify.

- [ ] **Commit 7** — `feat(therapy): seed framework migration + LGPD + clinical service consolidation`
  - Pre-flight: `git add products/therapy-platform/`
  - Pre-flight: count → expect ~46
  - Commit message: cite `projects/multi-provider-llm/` (clinical AI), `products/therapy-platform/projects/therapy-platform-wiring/` (seed migration), LGPD service updates
  - Post-verify.

- [ ] **Commit 8** — `feat(consumer-products): migrate PF + Daily-Life + Mailing to seed framework`
  - Pre-flight: `git add products/personal-finance/ products/daily-life/ products/mailing/`
  - Pre-flight: count → expect ~51
  - Commit message: cite all three products' seed-framework migrations + service consolidation
  - Post-verify.

- [ ] Phase 2 complete: `git status --short | wc -l` should now be ~105 - 188 ≈ negative... actually count dropping toward 0.

### Phase 3 — MCP + projects + infrastructure (commits 9-11)

- [ ] **Commit 9** — `feat(mcp): toolkit modernization + gemini test fix`
  - Pre-flight: `git add mcp/`
  - Pre-flight: count → expect ~31
  - Commit message: cite catalog tool addition, removal of `tools/fixes.py` (per observation-only rule), expanded tests, the two new keeper detectors (`check_config_extends_product_settings` + `check_frontend_config_paths`), and the Gemini provider test alignment with new google-genai SDK
  - Post-verify.

- [ ] **Commit 10** — `feat(projects): PROJECT.md scaffolds + improvements.md across all active projects`
  - Pre-flight: explicit list per §5.3
  - Pre-flight: count → expect ~30
  - Commit message: enumerate which projects landed (root: ai-expansion, multi-provider-llm, seed-core-consolidation, strict-mode-migration, adconnect-migration, the four 2026-04-25 projects keeper-config-inheritance-audit, keeper-frontend-config-paths-audit, seed-pydantic-v2-migration, repo-state-consolidation; product: erp-metas, therapy-platform-wiring, core-seed-wiring; mcp: proposals/ai-expansion + erp-metas + multi-provider-llm).
  - Post-verify.

- [ ] **Commit 11** — `chore(infra): scripts, templates, requirements, n8n, .github, .gitignore`
  - Pre-flight: explicit list per §5.3
  - Pre-flight: count → expect ~16
  - Pre-flight: this is the LAST commit. After staging, `git status --short` should show zero unstaged entries (everything else committed).
  - Commit message: enumerate (scripts: pre-commit hook, install-hooks.sh, update-kb-counts.py, sync-seed-template.sh; templates: PROJECT-TEMPLATE.md, PROPOSAL-TEMPLATE.md, product-seed/, n8n/; requirements.txt; start.sh; docker-compose.yml; .github/workflows/test.yml; .gitignore)
  - Post-verify.

- [ ] Phase 3 complete: `git status --short | wc -l` returns `0`. If non-zero → STOP and report unaccounted files.

### Phase 4 — Push + close (mandatory finale)

- [ ] Run `git log --oneline dfc57ab..HEAD` — verify exactly 11 new commits, in order
- [ ] Run `git push origin main`
- [ ] Verify `git status` shows nothing-to-push and nothing-to-pull (origin matches local)
- [ ] Update §11 with closing entry
- [ ] Flip status header (top of this file) to ✅ All phases shipped
- [ ] **End-of-work summary** — post a list-shaped recap covering all 11 commits + the push + any deferred items (per `feedback_end_of_work_summary.md`)

---

## 7. Open questions

All resolved before this project was scaffolded (see §2). The execution agent does NOT need to interrogate the user during execution unless the safety gate trips.

---

## 8. Dependencies & blockers

- **Clean starting state.** HEAD must be at `dfc57ab` (or current `main`) and staging area empty before Phase 1. If staging is non-empty when you start, run `git reset` to unstage everything (this is safe — files stay in working tree).
- **No conflicting in-flight projects.** The drafting session confirmed no other agent should be modifying the working tree concurrently. If you detect mid-execution that another agent is running (e.g., new files appearing in `git status`), STOP and report.
- **`origin/main` access.** Phase 4's `git push` requires push access to `origin/main`. If push fails (auth, branch protection, etc.), STOP — do NOT use force-push or any --force variant.
- **Reflog availability.** Recovery (`git reset --mixed HEAD~N`) relies on the reflog being intact. Default reflog retention is 90 days — well within scope. If reflog is somehow missing, recovery becomes harder; STOP and ask the user.

---

## 9. Success criteria

Measurable, verifiable.

- **Working tree empty:** `git status --short | wc -l` returns `0` after commit 11.
- **11 commits land:** `git log --oneline dfc57ab..HEAD | wc -l` returns `11`.
- **All 11 commit messages tell a story:** each commit's first-line `git log --format='%s' -11 HEAD` is specific (no "wip", "misc", "stuff").
- **Pre-commit hook passes on every commit:** no commit aborted by the verify-kb-sync.sh check or any other hook step.
- **Push succeeds:** `git push origin main` returns success; `git rev-parse origin/main` matches `git rev-parse HEAD` after push.
- **No `--no-verify` used:** `git log --format=%B -11 HEAD` shows no signs of skipped hooks.
- **No `--force` used:** `git reflog | grep "force"` returns nothing relevant.
- **§11 closing entry written.**
- **End-of-work summary posted to user.**

---

## 10. How to use this project

- **Read §3.1 (hook reality) FIRST.** It's load-bearing. Skipping it caused the previous session's failure.
- **Live-tick sub-tasks** as each commit lands. Save immediately — don't batch.
- **If the safety gate trips** (staged file count diverges from §6 expected ±5), STOP and report. Do not proceed without user instruction.
- **If the hook auto-stages unexpected files**, STOP and report — do not commit through it. The hook is supposed to auto-stage KB docs (commit 1) and stamp `__init__.py` files (every commit). Anything else is a surprise that warrants investigation.
- **Use `git reset --mixed HEAD~1` for safe recovery** if a commit lands wrong. NEVER `--hard`. NEVER `--amend` a published commit.
- **No tests during execution.** The commit cycle is state-sync, not feature-validation. Tests were already run in their respective projects; re-running 4000+ tests across the monorepo would consume hours and not change the outcome.

### 10.1 Verification commands (copy-paste ready)

```bash
# ── Phase 0: pre-flight ──
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
pwd
git rev-parse HEAD                                 # expect dfc57ab (or current main)
git branch --show-current                          # expect "main"
git diff --cached --name-only | wc -l              # expect 0
git status --short | wc -l                         # expect ~430 (±20)
git remote -v                                      # confirm origin

# ── Per-commit pre-flight gate (replace <pattern> per commit) ──
git add <pattern>
git diff --cached --name-only | wc -l              # compare to §6 expected
git diff --cached --name-only | head -30           # eyeball

# ── Per-commit post-verify ──
git show --stat HEAD | head -3
git log --oneline -1

# ── Phase 4: push ──
git log --oneline dfc57ab..HEAD                    # expect 11 lines
git push origin main
git rev-parse HEAD origin/main                     # both should be same hash

# ── If recovery needed (last commit wrong) ──
git reset --mixed HEAD~1                           # safe undo, files preserved
# then: re-stage correctly, re-commit
```

### 10.2 Commit message template

For each commit, the body should answer:

1. **What changed** — one or two sentences naming the files/features
2. **Why** — link to project / issue / rule that motivated the change
3. **Trail-of-the-building note** — a sentence about how this commit fits the larger sweep (especially for commits that touch many files)

Always end with the standard footer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 10.3 If something surprises you

- **`git status` shows new files appearing during execution** — another agent may be running. STOP, report, ask user.
- **A commit's pre-flight count is much higher than expected** — likely the staging area had pre-existing content. Run `git reset` (no --hard), then re-stage just your intended files.
- **Hook fails on `verify-kb-sync.sh`** — a CLAUDE.md pointer or KB doc index is broken. Investigate (likely the new project files in commit 10 reference files not yet committed). May need to reorder commits OR add a KB sync update to the affected commit.
- **Hook fails on `update-kb-counts.py`** — the count script crashed. Likely a malformed kb-counts:start/end block somewhere. Investigate and fix the malformed block, do NOT bypass.
- **`git push` rejects the push** — branch protection rule? Stale local? Check `git fetch origin && git status` for new commits on origin. If origin has new commits, STOP and ask user before merging.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-27 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after the previous session's commit attempt failed (commit `fcb30c2` swept 179 files into a single "kb counts" commit because the staging area had 131 pre-existing staged files and the pre-commit hook auto-staged 14 KB docs). Bad commit was reverted via `git reset --mixed HEAD~1`. User requested an organized commit plan documented as a project for execution by another agent in a clean session. §3.1 captures the hook-reality lesson; §10 captures the execution discipline. The 11-commit shape was approved: "if it's organized and has the trail of the building, then approved." Push strategy + pace approved: do all 11 in sequence, push at the end, save time. | Claude Opus 4.7 |
| 2026-04-28 | **Closed-project workspace cleanup (user directive: "let's get rid of old projects").** Deleted 8 closed-but-not-deleted project folders (clean-folder-rule violations from prior sessions): `projects/keeper-config-inheritance-audit/`, `projects/keeper-frontend-config-paths-audit/`, `projects/seed-pydantic-v2-migration/`, `projects/ai-expansion/` (all 19 phases ✅; status header was stale), `products/core/projects/core-scheduler-for-retention/`, `products/core/projects/core-seed-wiring/`, `products/core/projects/webhook-event-classification/`, `products/erp-imobiliario/projects/erp-metas/`. Updated cross-references that would otherwise strand: `KB § 03-SEED-ARCHITECTURE.md` (keeper-detector path-form refs → name-form + code pointer), `KB § 07-GAMIFICATION.md` (erp-metas reference-implementation → code pointer), `KB § 01-PHILOSOPHY.md` (erp-metas pointer → code), `KB § PATTERNS/project-execution.md` (project-locations examples updated to still-active slugs + erp-metas convention attribution preserved as historical citation; "shipped + folder deleted" example list added), `CLAUDE.md` (project-locations examples). All 8 closed projects were UNTRACKED at HEAD (`dfc57ab`) — pure working-tree cleanup, no git history affected. Effect on `repo-state-consolidation`'s commit plan: commit #10 (`projects/` add) will now pick up only the 4 still-active root projects + their per-product live siblings. KB sync ✓; keeper 100/100. | Claude Opus 4.7 |
| 2026-04-28 | **§3a backfilled + Phase 0 executed + expand-loudly applied (inaugural use of new rule).** Added §3a Seed-first analysis (backfilled per the authoring-time rule formalized 2026-04-28; analysis: platform-infra git operation, no DRY-into-seed concern fires). Phase 0 audit found working-tree drift from ~430 entries (drafted day) to 470 entries (today) caused by today's session shipping 4 projects (`consent-ui-rollout`, `llm-spend-badge-mount`, `digest-ui-pages`, umbrella close `ai-expansion-followups-rollout`) plus 6 methodology checkpoints (seed-first-design.md guide, project-execution.md §0/§2.6/§2.7/§2.5-updated, three-way-sync rule, recurrence rule formalization). **Inaugural application of the new `§ 2.5 expand loudly` rule** (replacing the prior "STOP and re-scope" framing as of 2026-04-28): §6 was expanded inline with a 12-row table allocating today's files into the right commits (#1 KB, #4 seed, #5-8 per-product, #10 projects, #11 infra). The original commit-shape (11 commits) is preserved; only the per-commit content is expanded. **User chose Path C** ("dont commit yet, let's finish whats left to be delivered of value, then we checkpoint it") so execution Phases 1-4 paused; doc is refreshed-and-ready for next session resume. The final `git push origin main` remains hard-gated on user confirmation per `Executing actions with care` (intermediate commits expand loudly without a gate; the push does NOT). | Claude Opus 4.7 |

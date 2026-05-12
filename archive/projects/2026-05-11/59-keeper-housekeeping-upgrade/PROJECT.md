# Keeper Housekeeping Upgrade — Project Document

> **This is a living document, not a rigid checklist.** Revise phases, fold in optimizations, update the Change Log as we learn.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Design locked → Phase 1 ready
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Related docs:** `KB § PATTERNS/seed-absorption.md § noctus.hound.scan`, `KB § PATTERNS/storage-hygiene.md` (mole), `mcp/noctusai/tools/noctus/dev/compliance.py` (keeper detectors), `KB § PATTERNS/autonomous-operator-via-subagent.md`
- **Project slug:** `keeper-housekeeping-upgrade` at `projects/keeper-housekeeping-upgrade/` *(cross-cutting platform work)*

---

## 1. Context & Purpose

Operator tick 2 (2026-05-11) surfaced four hygiene-compliance gaps that no current module patrols: archive folder rotation drift, dispatcher inbox/outbox staleness, merged-but-not-deleted git branch orphans, gitignore drift on coordination/log files. The trio today — **keeper** (regulatory), **hound** (curatorial code hygiene), **mole** (custodial disk storage) — has clean boundaries but leaves a "workspace hygiene as compliance" axis uncovered. User's instinct: housekeeping non-compliance IS compliance non-compliance, and the keeper's "detect + propose, never modify" stance fits perfectly.

**The win:** keeper grows a second compliance axis (hygiene) without becoming a fourth identity. Operator + architect get an active monitor that surfaces "your archive is stale" / "your inbox has 26 entries older than 24h" / "12 merged branches haven't been deleted" as proposals, exactly mirroring LGPD / webhook-pin findings.

---

## 2. Confirmed constraints

- **Single identity, two axes** — *(user 2026-05-11: "Make this keeper upgrade. Not as a separate identity")*. Keeper hosts all compliance checks; hygiene is a new category, not a new module. Hound and mole stay in their lanes.
- **Observation-only stance preserved** — *(`feedback_keeper_observation_only.md`)*. New detectors propose; never modify files. Mole + archive-clean remain the execution layer.
- **Severity calibration** — *(`feedback_first_run_keeper_warning_triage`)*. New detectors emit `warning` severity by default.
- **Regression-test-the-detector** — *(`feedback_regression_test_the_detector.md`)*. Every new `check_*` ships a colocated `Test<CamelCase>`. Non-negotiable.
- **Three-way sync** — KB pattern doc + memory entry land together. CLAUDE.md routing pointer only if warranted.

---

## 3. Design principles

1. **Hygiene is a compliance category, not a code-hygiene category.** Code DRY violations stay in hound. Workspace hygiene is the keeper's domain because the unit-of-judgment is "does the workspace honor its convention?" — same shape as "does this router honor webhook 5-pin?"
2. **Each new detector emits a proposal pointing at the correct executor.** Keeper proposes; mole/scripts/engineer executes.
3. **Reuse existing scaffolding.** New detectors mount into `compliance.py`'s global-checks bucket. No new MCP tool.
4. **Default-on for all four.** Severity `warning` keeps them from the `error` floor.

---

## 3a. Seed-first analysis

1. Identical-for-every-product? N/A — these are **repo-wide** checks, not per-product. They run in the global-checks bucket alongside existing `seed_version_propagation`, `phase_state_consistency`, `section_seven_placeholder_parity`.
2. Data source product-specific? No — filesystem state of `archive/`, `dispatcher-*.md`, `git branch -a`, `.gitignore`.
3. Placement product-specific? No — `mcp/noctusai/tools/noctus/dev/compliance.py` global-checks section.
4. Visibility/permission uniform? Yes — keeper reports to architect.
5. Seam exists in seed? Yes — the global-checks pattern.
6. Default-on or opt-in? Default-on with `warning`.

**Litmus — per-product code count: 0 lines.** ✅

**Phase plan implications:** §6 works in `compliance.py` global-checks scope. No per-product walking.

---

## 4. Scope

**In scope:**
- Add 4 new `check_*` functions to `compliance.py` global-checks section: `check_archive_staleness`, `check_dispatcher_staleness`, `check_branch_orphan`, `check_gitignore_drift`.
- 4 colocated regression tests.
- Update `KB § PATTERNS/storage-hygiene.md` trio table to clarify keeper now covers hygiene-compliance.
- Memory entry capturing the new compliance axis.
- Drive-by: add `dispatcher-outbox.md` + `scripts/mole-last-sweep.log` + `scripts/archive-clean-last-sweep.log` (if exists) to `.gitignore`.

**Out of scope:**
- New `noctus.housekeeper.*` MCP namespace.
- Mole expansion.
- Hound expansion.
- Automatic remediation. Keeper proposes; user/operator executes.

---

## 5. Files to touch

- `mcp/noctusai/tools/noctus/dev/compliance.py`
- `mcp/noctusai/tests/test_compliance_hygiene.py` (NEW)
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/storage-hygiene.md`
- `.gitignore`
- `dispatcher-inbox.md` — engineer decides whether to untrack via `git rm --cached` + re-add as `dispatcher-inbox.template.md` (tracked, format-only) OR keep tracked + gitignore an alternate "live" path. Document the choice in §11.

---

## 6. Phase plan

### Phase 1 — Detector scaffolding + tests ✅ DONE 2026-05-11 (Engineer K)

**Improvements:** none identified for Phase 1 specifically. Two architect-followups surfaced (filed to §11):
- `_detect()` consistency: 7 existing pre-existing global detectors aren't wired through `review.py::_detect()`; engineer mirrored existing pattern (validate-only). Decision deferred to a separate methodology pass.
- Editable-install re-point gotcha at worktree time — captured for KB § GUIDES/setup.md amendment.

**1.1** Read `compliance.py` global-checks section end-to-end. Identify registration pattern (likely a list near `_detect_global` or similar).

**1.2** Implement 4 `check_*` functions:

| Detector | Trigger | Proposal text |
|---|---|---|
| `check_archive_staleness` | `archive/projects/<YYYY-MM-DD>/` folders older than D-2 (local time) | "Archive contains N stale folder(s); run `bash scripts/archive-clean.sh --force`." |
| `check_dispatcher_staleness` | Entries in `dispatcher-inbox.md` or `dispatcher-outbox.md` with `### YYYY-MM-DDTHH:MM` timestamps >24h not under `## Completed (last 24h)` | "N dispatcher entries >24h not rotated; prune or escalate to dispatcher-archive." |
| `check_branch_orphan` | `git for-each-ref` filtered to branches reachable from `origin/main` (SHA or patch-id), excluding `main` | "N branches merged but not deleted; `git branch -d <name>` (local) / `git push origin --delete <name>` (remote)." |
| `check_gitignore_drift` | Known transient paths exist OR are tracked but should be ignored. Initial list: `dispatcher-outbox.md`, `scripts/mole-last-sweep.log`, `scripts/archive-clean-last-sweep.log`, anything under `.claude/worktrees/` | "N coordination/log files not gitignored; patch `.gitignore` + `git rm --cached` if tracked." |

Each returns the existing `KeeperFinding` shape with `severity='warning'`, `category='hygiene'`, `detector_id='hygiene.<name>'`. Engineer reads `compliance.py` for the exact constructor.

**1.3** Wire into the global-checks list. Verify `noctus.dev.review` (or equivalent CLI mode) fires all four.

**1.4** Colocated tests in `mcp/noctusai/tests/test_compliance_hygiene.py`:
- `TestArchiveStaleness` — temp `archive/projects/<3-days-ago>/`; assert detector fires + proposal mentions `--force`. Teardown cleans up.
- `TestDispatcherStaleness` — temp inbox with 48h-old entry; assert fires.
- `TestBranchOrphan` — mock `for-each-ref` output OR set up tmp git repo; assert fires on merged branch + skips unmerged.
- `TestGitignoreDrift` — touch `dispatcher-outbox.md`; assert fires.

Tests follow status+body assertion rule (`feedback_status_code_assertion_rule.md`): assert severity AND proposal body together.

**1.5** Drive-by `.gitignore` patch: add `dispatcher-outbox.md`, `scripts/mole-last-sweep.log`, `scripts/archive-clean-last-sweep.log`. Decide and document the `dispatcher-inbox.md` tracking shape.

### Phase 2 — KB + memory sync (architect post-Phase 1 merge)

**2.1** Amend `KB § PATTERNS/storage-hygiene.md` trio table — add hygiene-compliance note to keeper row.

**2.2** Memory entry: new compliance axis on the keeper.

**2.3** §11 Change Log entry in this PROJECT.md.

### Phase 3 — Project close (architect)

Mark Status: Done. FF-merge to main (already merged per phase). Archive via `noctus.dev.archive`.

---

## 7. Open questions

(none active — design locked with user 2026-05-11)

---

## 8. Risks & mitigations

- **Detector noise** — fresh clone has zero state → all four pass silently. First real-world run surfaces real findings; user triages once. *Mitigation:* `warning` severity floor.
- **Branch-orphan over-detection** — with 150+ commits today this list could be N=20+. *Mitigation:* proposal includes the count and a batch-delete one-liner.
- **Dispatcher-staleness parser brittleness** — depends on heading format. *Mitigation:* test covers current format; format changes trigger parser update.

---

## 9. Success criteria

- 4 new `check_*` functions in `compliance.py` with colocated tests.
- `noctus.dev.review` global-mode surfaces real findings on this repo's state (≥1 from each detector — verified manually).
- KB pattern doc updated; memory entry written.
- 3 transient files gitignored; `dispatcher-inbox.md` tracking shape decided + documented.

---

## 10. Copy-paste commands

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
python -m pytest mcp/noctusai/tests/test_compliance_hygiene.py -v
# Verify wiring (exact flag depends on cli.py):
python mcp/noctusai/cli.py --review --globals-only
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

- **2026-05-11** — Project filed. Design locked with user: "all 4 detectors in one pass". Engineer K dispatch authorized.
- **2026-05-11** — Phase 1 shipped (Engineer K). 4 hygiene-compliance detectors landed in `mcp/noctusai/tools/noctus/dev/compliance.py` + colocated regression suite (`tests/test_compliance_hygiene.py`, 19 tests green) + drive-by `.gitignore` patch (dispatcher-outbox + 2 sweep logs). All wired into `check_all_products()` global-checks section. Real-repo live findings: archive=0, dispatcher=0, branch-orphan=0 (all 290 local branches are recent), gitignore-drift=3 (closed by the drive-by patch). Tracking-shape decision for `dispatcher-inbox.md`: **kept tracked as-is** (scaffold file with header docstring + section structure — keeping it in history lets fresh clones bootstrap the two-session pattern without an extra setup step; `dispatcher-outbox.md` is the operator-only churn surface and that one IS gitignored).

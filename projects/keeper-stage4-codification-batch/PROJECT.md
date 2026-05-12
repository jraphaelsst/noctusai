# Keeper Stage-4 Codification Batch — Project Document

> **Living document.** Revise phases, fold in learnings.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Design locked → Phase 1 ready (Engineer P dispatch)
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Related docs:** `KB § PATTERNS/methodology-codification-pipeline.md` (the pipeline this project drives Stage 3→4 promotions through), `mcp/noctusai/tools/noctus/dev/compliance.py` (target module), `KB § PATTERNS/storage-hygiene.md` (trio table, just-amended for hygiene-compliance keeper axis)
- **Project slug:** `keeper-stage4-codification-batch` at `projects/keeper-stage4-codification-batch/`

---

## 1. Context & Purpose

User directive 2026-05-11: *"codify it all"* — promote every Stage 3 rule that meets the codification criteria (deterministic predicate + recurrence ≥3 + clear remediation) into a Stage 4 keeper detector. Today the methodology has accumulated ~30 Stage 3 rules in memory + KB; a meaningful subset can be promoted in one focused engineer pass.

**Why batch:** the detectors all land in `compliance.py`. Splitting across N parallel engineers would race on the same file. Until `compliance.py` is split into per-category modules (a separate refactor project), the right shape is **ONE engineer with a batched scope**.

**The win:** the methodology becomes self-enforcing. Rules currently surfaced by agent-memory only (and therefore depend on the agent remembering them mid-task) become mechanical checks that fire on `noctus.dev.review`. The promotion is exactly the pipeline's design — first run was K's keeper-housekeeping; this batch extends the same shape to 5+ more rules.

---

## 2. Confirmed constraints

- **Observation-only stance preserved** — every new detector emits proposals, never modifies code. Same as K's pattern. *(Why: `feedback_keeper_observation_only.md` — keeper never executes.)*
- **Severity `warning` floor** — these are correctness/discipline rules, not safety bugs. The keeper's `error` floor is reserved for compliance-contract violations (LGPD, webhook 5-pin). *(Why: `feedback_first_run_keeper_warning_triage` — calibrate severity so the first run isn't a flood.)*
- **Colocated regression test for each detector** — `Test<CamelCase>` class in `mcp/noctusai/tests/test_compliance_<batch>.py` (or extension of `test_compliance.py`). *(Why: `feedback_regression_test_the_detector.md` — non-negotiable.)*
- **Stay in compliance.py** — engineer does NOT refactor compliance.py into multiple modules in this pass. That's a separate project. Add new `check_*` functions alongside existing ones. *(Why: scope control — refactor + add is harder to review than add-only.)*
- **No-overlap rule applies to batches within the file** — engineer drafts each detector sequentially within the same PR, but verifies all 5-7 detectors compose cleanly at the end (one pytest run, all green).

---

## 3. Design principles

1. **Pick rules with the cleanest predicates first.** Some rules need careful AST work (e.g. detecting `Depends(ProductDependencies.get_org_id)` shape); others are pure-text greps (`# silent-ok` comment). Land the easy ones first; harder ones can defer to Phase 2 if time runs out.
2. **One detector = one function = one test class.** No clever sharing between detectors. The detector list is a long catalog; keep each entry self-contained for ease of review + future retirement.
3. **Each detector ships with a concrete remediation in its proposal text.** Per the codification pipeline §3.3 — proposals without remediation add noise.

---

## 3a. Seed-first analysis

1. Identical-for-every-product? Mixed — some detectors are per-product (auth shape, monkey-patch in tests, MCP path constants); some are repo-global (silent-ok comments, doc-tool-reference drift).
2. Data source product-specific? Code state of each product (per-product scans) or repo-global state.
3. Placement product-specific? No — `compliance.py` globally hosts all detectors.
4. Visibility/permission uniform? Yes — keeper reports to architect.
5. Seam exists in seed? Yes — the existing `check_all_products()` per-product loop + the global-checks bucket.
6. Default-on or opt-in? Default-on, severity warning.

**Litmus — per-product code count: 0 lines.** ✅

---

## 4. Scope

**In scope — 7 detector candidates (all Stage 3 → Stage 4 ready):**

| # | Detector | Rule source | Predicate | Severity |
|---|---|---|---|---|
| 1 | `check_no_silent_ok_comment` | `feedback_silent_ok_is_not_a_substitute_for_logging.md` | Grep `# silent-ok` literal in production code (`products/*/backend/app/`, `seed/`, `mcp/`). | warning |
| 2 | `check_no_self_monkeypatch` | `feedback_no_monkeypatching_in_tests.md` | AST scan test files for `monkeypatch.setattr(<our-module>, ...)` where `<our-module>` matches `app.` / `seed.` / `noctusai_lib.` / `noctusai_seed.` prefixes. Permit `monkeypatch.setattr(<external-vendor>, ...)`. | warning |
| 3 | `check_auth_dep_anti_pattern` | `feedback_auth_factory_pattern.md` | AST scan routers for `Depends(ProductDependencies.get_org_id)` / `Depends(ProductDependencies.get_user_role)` / `Depends(ProductDependencies.get_user_client)` (positional-args 422-trap shape). Permit imperative use (without `Depends(...)`). | warning |
| 4 | `check_mcp_path_via_settings` | `feedback_mcp_path_constants_from_settings.md` | AST scan `mcp/noctusai/tools/**/*.py` for `Path(__file__).parents[<N>]` — should import `REPO_ROOT` / `PRODUCTS_DIR` from `settings` instead. | warning |
| 5 | `check_mcp_write_tool_worktree_arg` | `feedback_mcp_write_tools_resolve_caller_root.md` | AST scan MCP tool defs in `mcp/noctusai/tools/**` — write-side tools (functions writing to filesystem) must accept `worktree_path: str` arg. Heuristic: tool name contains `archive` / `scaffold` / `absorb` / `set_proposal_status` / `proposal_template` / similar write-verbs. | warning |
| 6 | `check_pipefail_grep_q` | M's mole-enum-fix finding 2026-05-11 | Grep `cmd | grep -q ...` patterns under `set -o pipefail` (or `set -euo pipefail`) — the SIGPIPE-141 footgun. Initial scope: `scripts/*.sh`. | warning |
| 7 | `check_doc_tool_reference_drift` | `feedback_doc_code_coherence_rule.md` (§9 of pipeline doc, codification candidate) | For each `bash scripts/<name>.sh <mode>` mention in KB docs, confirm `<mode>` still exists in the script (regex `\b<mode>\b` near top-of-file usage header). Mismatches = drift. Initial scope: `KB § PATTERNS/methodology-codification-pipeline.md § 8`. | warning |

**Out of scope:**
- Refactoring `compliance.py` into per-category modules (separate project; opens parallelism for future batches).
- Promoting judgment-dependent rules (no quick fixes / estimate off evidence / triage at decision time) — these stay at Stage 3 forever per the pipeline doc §5.1.
- Promoting context-dependent rules (parallelize by default / branching-first orchestration) — same reason.
- Promoting TEMPORARY rules (Option D pattern / branching-first methodology validation) — these have explicit TEMP guards in memory; codifying them now locks calibration.

---

## 5. Files to touch

- `mcp/noctusai/tools/noctus/dev/compliance.py` — add 7 `check_*` functions + wire into globals.
- `mcp/noctusai/tests/test_compliance_codification_batch.py` (NEW) — 7 test classes, ~3-5 tests each.
- For each new detector, update §8 table in `KB § PATTERNS/methodology-codification-pipeline.md` with a new row. (Per the doc-code coherence rule we just shipped.)
- Memory entries: update each rule's entry to flip the Stage 3 → Stage 4 status flag if applicable. Append "Codified 2026-05-11 in `check_*` via keeper-stage4-codification-batch" line.

---

## 6. Phase plan

### Phase 1 — Engineer P implements 7 detectors ✅ DONE 2026-05-11 (Engineer P)

**Improvements:** two calibration items captured + addressed in-pass — self-allowlist for `check_no_silent_ok_comment` (detector matched its own definition); prefix-match + read-prefix-guard list for `check_mcp_write_tool_worktree_arg`. Meta-finding: `check_no_self_monkeypatch` was already codified pre-batch — Stage 3 inventory needs fresh sweep against live `_detector_function_names()` before future codification batches.

**1.1** Read `compliance.py` end-to-end. Identify the `KeeperFinding` dict shape (per K's earlier finding: it's a dict with `{product, file, issue, severity}` keys, not a class). Match existing globals pattern.

**1.2** For each detector in §4 table (top to bottom — easy → harder):
- Implement `check_<name>(repo_root: Path) -> list[KeeperFinding]`.
- Use the prescribed predicate. If the predicate has edge cases (e.g. test files containing literal `# silent-ok` in a docstring describing the rule), include an allowlist or scope-narrow.
- Write a colocated `Test<CamelCase>` class in `test_compliance_codification_batch.py` with ≥3 tests: positive-fires, negative-doesn't-fire, edge-case (empty/missing-target/scope-narrow).
- Wire into `check_all_products()` globals.

**1.3** Run `pytest mcp/noctusai/tests/test_compliance_codification_batch.py -v` — all green.

**1.4** Run `noctus.dev.review` against this repo. Capture which detectors emit real findings. Surface counts to the architect.

**1.5** Update `KB § PATTERNS/methodology-codification-pipeline.md § 8` table — add 7 rows (one per detector). Per doc-code coherence rule.

**1.6** Update each rule's memory entry to flag Stage 4 status. Touch:
- `feedback_silent_ok_is_not_a_substitute_for_logging.md`
- `feedback_no_monkeypatching_in_tests.md`
- `feedback_auth_factory_pattern.md`
- `feedback_mcp_path_constants_from_settings.md`
- `feedback_mcp_write_tools_resolve_caller_root.md`
- `feedback_doc_code_coherence_rule.md`

Memory files live at `/Users/rapha/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/`. Engineer is authorized to edit these files.

### Phase 2 — Architect review + §11 close

Architect reviews the 7 detector findings against the repo. Triages each real finding (formalize / refactor / accept-with-rationale).

---

## 7. Open questions

(none active — design locked with user 2026-05-11)

---

## 8. Risks & mitigations

- **Detector noise.** First run may surface 50+ findings across the 7 detectors. *Mitigation:* severity `warning` (not `error`); architect triages once.
- **AST predicate over-detection.** Especially #3 (auth) and #5 (MCP worktree arg) — heuristic-based detection can false-positive. *Mitigation:* test the negative cases carefully; document the heuristic in the detector docstring; architect-followup if false positive rate > 20%.
- **Bash predicate brittleness.** Detector #6 (pipefail+grep-q) requires shell parsing. *Mitigation:* simple regex on `set -[eo].*pipefail` + `| grep -q` co-occurrence in the same file; ignore comments; acceptable simple-heuristic.

---

## 9. Success criteria

- 7 new `check_*` functions in `compliance.py` with colocated tests.
- All tests green.
- `noctus.dev.review` global-mode surfaces real findings (≥1 from at least 5 of the 7 detectors — verifies the predicate actually fires on real code).
- §8 table updated with all 7 entries.
- 6 memory entries updated with Stage 4 status flags.

---

## 10. Copy-paste commands

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
python -m pytest mcp/noctusai/tests/test_compliance_codification_batch.py -v
python mcp/noctusai/cli.py --review  # full review; observe new detectors firing
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

- **2026-05-11** — Project filed. Engineer P dispatch authorized (single engineer, batched scope, file-bound to compliance.py). Architect explicitly chose serial-batched over parallel-N-engineers because compliance.py is one file — see §1 + §2. Future codification batches become parallel once compliance.py is split into per-category modules (separate project).
- **2026-05-11 — Phase 1 complete (Engineer P, ready-for-commit).** Landed 6 net-new detectors + 31 tests + KB §8 amendments + 6 memory-entry Stage-4 status flags + 1 new memory file. Detector #2 from §4 table (`check_no_self_monkeypatch`) was already codified prior to this batch (compliance.py line ~1526) — engineer recognized the no-op + reaffirmed the Stage-4 status in its memory entry. Net detectors landed: 6 of 7 (1 was already codified).
  - **`check_no_silent_ok_comment`** — literal `# silent-ok` comment scan across production code roots. Self-allowlist for `compliance.py` (defines the detector + documents the rule; citation, not silenced exception). Calibration: file allowlist surfaced as needed during real-repo dry-run.
  - **`check_auth_dep_anti_pattern`** — AST scan routers for `Depends(ProductDependencies.{get_org_id,get_user_role,get_user_client})`. Imperative use permitted. Closes the 3rd-defense-layer that the 2026-05-06 design called out.
  - **`check_mcp_path_via_settings`** — AST scan `mcp/noctusai/tools/**/*.py` for `Path(__file__).parents[N]`. Singular `.parent` permitted (common in `__file__`-relative test setup).
  - **`check_mcp_write_tool_worktree_arg`** — AST scan MCP tool defs; write-prefix names without `worktree_path` param. Calibration: prefix-based match (not contains-based) + read-prefix guards (`check_`, `get_`, `list_`, `read_`, `fetch_`, `find_`, `scan_`, `outline_`) suppress false positives.
  - **`check_pipefail_grep_q`** — `| grep -q` in `scripts/*.sh` under `set -[eo].*pipefail`. Comment-line + trailing-comment stripping in place. NEW memory entry `feedback_pipefail_grep_q_footgun.md` filed capturing M's discovery 2026-05-11.
  - **`check_doc_tool_reference_drift`** — `bash scripts/<name>.sh <mode>` references in KB doc surfaces (initial scope: `methodology-codification-pipeline.md`). Mode regex requires `[A-Za-z_]`-leading token so flag-style args (`--force`) are skipped.
  - **Calibration findings flagged for Phase 2 triage:**
    - `check_no_silent_ok_comment`: 0 findings on the current repo (post-self-allowlist).
    - `check_auth_dep_anti_pattern`: 0 findings.
    - `check_mcp_path_via_settings`: 0 findings (Phase 3 cleanup already drained the recurrence).
    - `check_mcp_write_tool_worktree_arg`: 4 findings — `scaffold_interrogate`, `reserve_port_range`, `create_testing_ground` (all in scaffold.py), `review_session` (in session_review.py). Architect to triage: some may be legitimate read-side tools that the verb-prefix heuristic over-flagged; remediation either tightens prefix list or adds the missing `worktree_path` arg.
    - `check_pipefail_grep_q`: 2 findings — `scripts/verify-kb-sync.sh:96`, `scripts/cleanup-stale-worktrees.sh:292`. Both genuine SIGPIPE-141 candidates; remediate via pipeline split or `cat`-drain.
    - `check_doc_tool_reference_drift`: 0 findings (mode regex tightened to skip flag-style args after first dry-run surfaced false positives on `--force`).
  - **Tests:** 31 new tests in `test_compliance_codification_batch.py`, ≥3 per detector + edge cases (positive-fires, negative-doesn't-fire, async coverage, missing-target dirs, comment-line negative, word-boundary partial match). Full suite: 159/159 passing across `test_compliance.py` + `test_compliance_codification_batch.py` + `test_compliance_hygiene.py` + `test_compliance_prod.py`. `TestSeedCompliance::test_all_products_compliant` still passes (globals don't enter per-product score by preexisting design — additions don't regress the 100-gate).

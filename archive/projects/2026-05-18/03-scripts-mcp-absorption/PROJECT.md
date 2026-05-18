# Scripts → MCP Absorption — Project Document

> Living document. Symbol-first §6/§11 per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-18
- **Last updated:** 2026-05-18
- **Status:** ✅ DONE — all 7 phases complete (rule codified · 16 scripts → native MCP · pre-commit thin-dispatcher · carve-outs documented · full folder reorg with risk-mitigation · verified)
- **Owner / stakeholders:** joaoraphaelsst · Claude (architect)
- **Related docs:** `KB § PATTERNS/seed-absorption.md`, `KB § 06-AGENTS.md` (MCP toolkit), `KB § 01-PHILOSOPHY.md § MCP-first`, `scripts/README.md`, `mcp/noctusai/tools/noctus/dev/`
- **Project slug:** `scripts-mcp-absorption` (intent `consolidation`; cross-cutting platform-infra → lives at `projects/<slug>/`)

---

## 1. Context & Purpose

`scripts/` is a flat 25-file folder mixing four structurally different things: (a) pure-logic automation that *should* be MCP tools (testable, agent-callable, discoverable via the toolkit) but is shell/Python one-offs; (b) scripts whose MCP "analog" already exists either as a real Python impl (`verify-kb-sync.sh`→`tools/kb_sync.py`) or — deceptively — as a thin `subprocess` shim (`mole.py` just shells out to the 26KB `mole.sh`, so the shell IS still the implementation); (c) git-hook entry points git invokes as shell directly (`pre-commit`); (d) pre-venv bootstrap that *creates* the environment the MCP runs inside (`setup.sh`, `bootstrap-*`) — these structurally cannot become MCP-only.

The pain: logic that should be one source of truth is duplicated or un-absorbed, untestable through the toolkit, invisible to agents, and the flat folder gives no signal about which class a script is. The win: every absorbable script becomes a `noctus.dev.*` MCP tool (single source of truth, colocated test, agent-callable); genuine duplicates deleted; structural carve-outs explicitly documented with rationale; a codified default-MCP rule (keeper-enforced) so this never re-accretes; remaining scripts organized into intent folders.

---

## 2. Confirmed constraints

User Q→A 2026-05-18 (AskUserQuestion):

- **Non-absorbable scripts (git-hook entry, pre-venv bootstrap)** — *Absorb the LOGIC into an MCP tool; the entry script becomes a thin dispatcher calling the CLI/MCP.* Single source of truth; the shell shim stays only where git/pre-env structurally require it. *(Rules out both "leave fully shell" and "force MCP with no shim".)*
- **Scripts that already have an MCP analog** — *Delete the script, MCP is canonical; repoint every doc/hook reference.* *(Maximal dedup. Caveat surfaced: `mole.py` is only a subprocess shim → mole is a genuine heavy port, not a delete-the-dup; `verify-kb-sync.sh`→`kb_sync.py` is a real impl → safe delete.)*
- **MCP namespace for absorbed scripts** — *Extend the existing `noctus.dev.*`* (no new `noctus.ops.*` service). *(One namespace, simpler routing; `noctus.dev.*` accepted as broad.)*
- **Doc rule scope** — *Default-MCP + named structural carve-outs.* New automation defaults to an MCP tool; shell allowed ONLY for the named carve-out categories (git-hook entry · pre-venv bootstrap · thin docker-orchestration) WITH written rationale. Codified three-way-sync + keeper-checkable. *(Rules out "strict no-exceptions" and "advisory only".)*
- **Sequencing** — *"push please. after that, let's start... After absorbing and finishing the mcp job, let's organize our remaining scripts in folders."* → folder reorg is the LAST phase, after absorption lands. Push was a no-op (already in sync).

---

## 3. Design principles

1. **Doc rule first.** Codify default-MCP + carve-outs (Phase 1) BEFORE absorbing — the rule governs every subsequent phase and the keeper guards recurrence.
2. **Behaviour-preserving port.** Each absorption is a 1:1 logic move; the MCP tool reproduces the script's exact output/exit semantics; colocated `Test*` per `feedback_regression_test_the_detector`.
3. **AST-first for `.py` ports** (`libcst`); shell→Python is a rewrite, pytest + the script's own old output are the oracle (structural-refactor corollary).
4. **No reference left dangling.** Deleting/shimming a script greps ALL survivors (docs, hooks, README, MASTER-PROMPTs, CI) and repoints — same discipline as `feedback_dangling_deleted_product_path`.
5. **Carve-outs are documented landings, not silence.** Every script that stays shell gets an `[A]` accept-with-rationale catalog entry (durable, survives folder deletion).

---

## 3a. Seed-first analysis

This is platform-tooling (the `mcp/noctusai` dev toolkit), not product code — the seed-first axis here is **MCP-toolkit-first**, the tooling analog of seed-first.

1. **Contract identical for every consumer?** YES — one MCP tool surface, all agents/sessions call the same `noctus.dev.*`.
2. **Data source tool-specific?** NO — scripts operate on the repo tree uniformly.
3. **Placement specific?** NO — universal `mcp/noctusai/tools/noctus/dev/`.
4. **Visibility/permission uniform?** YES — toolkit allowlist is the single gate (`feedback_subagent_mcp_access`).
5. **Seam exists?** YES — `noctus.dev.*` service + `cli.py` flag pattern + `scaffold_mcp_tool` codegen.
6. **Default-on or opt-in?** DEFAULT-ON — MCP-first is platform policy (`KB § 01-PHILOSOPHY.md § MCP-first`).

**Litmus — per-product code count:** 0. Pure cross-cutting toolkit consolidation; zero product files touched. §6 phases work in the toolkit, never walk products. ✅ correctly toolkit-bounded.

---

## 4. Scope

**In scope:** classify all 25 `scripts/` entries; codify default-MCP doc rule + keeper; port/dedup absorbable scripts to `noctus.dev.*`; delete genuine dups + repoint refs; document carve-outs in accept-with-rationale; reorganize remaining scripts into intent folders.

**Out of scope (deferred, reasoned):**
- `scripts/codemods/` (AST codemod *library*, not a script — already AST, not flat-folder noise) — folder-reorg phase may relocate but no absorption.
- `scripts/init-local-db/*.sql` — SQL data files, not scripts — folder-reorg only.
- Rewriting bootstrap *behaviour* — only thin-shim/rationale, no functional change (fresh-clone safety is non-negotiable).

---

## 5. Architecture — Phase 0 classification (LOCKED)

`Σ` = 25 scripts + 2 non-script subdirs. Buckets:

| # | Script | Bucket | Disposition | MCP target |
|---|---|---|---|---|
| 1 | `verify-kb-sync.sh` | B · heavy port (analog = subprocess shim) | real-port + delete + repoint | `tools/kb_sync.py` (replace shim w/ real impl) |
| 2 | `mole.sh` (26KB) | B · heavy port (analog = subprocess shim) | port shell→Py, delete shell | `mole.py` becomes real impl |
| 3 | `archive-clean.sh` | C · pure-logic | absorb + delete | extend `archive.py` → `noctus.dev.archive_clean` |
| 4 | `disk-usage-monitor.sh` | C | absorb + delete | `noctus.dev.disk_usage` |
| 5 | `check-framework-deps.py` | C | absorb + delete | `noctus.dev.check_framework_deps` |
| 6 | `gen-promotions-index.py` | C (delegates ×2 MCP) | absorb + delete | extend `promotion.py` |
| 7 | `render-project-history.py` | C (delegates ×1) | absorb + delete | extend `history.py` |
| 8 | `backfill-project-history.py` | C (delegates ×1) | absorb + delete | extend `history.py` |
| 9 | `stamp-seed-version.sh` | C (pre-commit-invoked) | absorb, thin shim | `noctus.dev.stamp_seed_version` |
| 10 | `merge-debt-monitor.sh` | C (delegates ×1) | absorb + delete | `noctus.dev.merge_debt` |
| 11 | `cleanup-stale-worktrees.sh` | C | absorb + delete | `noctus.dev.cleanup_worktrees` (near `salvage_worktree.py`) |
| 12 | `update-kb-counts.py` | C (pre-commit-invoked) | absorb, thin shim | extend `kb_sync.py` |
| 13 | `sync-seed-template.sh` | C (pre-commit-invoked) | absorb, thin shim | `noctus.dev.sync_seed_template` |
| 14 | `propagate-composes.sh` | C · codegen-from-canonical | absorb + delete | `noctus.dev.propagate` |
| 15 | `propagate-dockerfiles.sh` | C · codegen-from-canonical | absorb + delete | `noctus.dev.propagate` |
| 16 | `smoke-fleet.sh` | C · HTTP checks | absorb + delete | `noctus.dev.smoke_fleet` |
| 17 | `pre-commit` | D · git-hook entry | absorb orchestration, thin shim | `noctus.dev.precommit` |
| 18 | `install-hooks.sh` | D · hook installer (bootstrap-class) | carve-out, document | — |
| 19 | `setup.sh` | E · pre-venv bootstrap | carve-out, document | — |
| 20 | `first-time-setup.sh` | E | carve-out, document | — |
| 21 | `bootstrap-worktree.sh` | E | carve-out, document | — |
| 22 | `bootstrap-seed-workspace.sh` | E | carve-out, document | — |
| 23 | `build-init-local-db.sh` | E (regenerates init-local-db SQL pre-venv) | carve-out, document | — |
| 24 | `build-base-images.sh` | F · thin docker-orchestration | carve-out, document | — |
| 25 | `first-time-setup.sh`/`smoke` dup-check | — | (covered above) | — |
| s1 | `codemods/` | non-script lib | folder-reorg only | — |
| s2 | `init-local-db/*.sql` | data files | folder-reorg only | — |

Absorb (A+B+C+D-logic) = 17 · Carve-out (D-entry+E+F) = 8 · Non-script = 2.

**pre-commit dependency:** `pre-commit` invokes #9 `stamp-seed-version`, #12 `update-kb-counts`, #7 `render-project-history`, #13 `sync-seed-template`, #1 `verify-kb-sync` → Phase 4 (pre-commit shim) gates on those absorptions FF-merging first.

---

## 6. Implementation phases

Phase-by-phase; pause for user "continue" between phases unless told to ram.

### Phase 0 — Audit ✅ (locked 2026-05-18; §5 table)
- [x] Survey all 25 `scripts/` entries + 2 non-script subdirs
- [x] Cross-check against MCP tool surface + cli.py flags + pre-commit invocations
- [x] Classify into buckets A/B/C + 3 carve-out categories (§5 table)

**Improvements:**
- The "already has an MCP analog" bucket split in two only because the audit *read* `mole.py` (a 26KB-shell `subprocess` shim) instead of trusting its existence — `verify-the-seed-ships-it`-shaped lesson applied to tooling: an MCP file existing ≠ the logic being absorbed. Bucket B exists because of this; no further action.
- Manifest's durable home is the KB doc, not this PROJECT.md §5 (PROJECT.md is archive-bound — durable-docs rule). §5 now references §3 of the KB doc rather than owning the table.

### Phase 1 — Doc rule codification + keeper ✅ (2026-05-18)
- [x] `s3` KB: new `KB § PATTERNS/mcp-first-scripts.md` — default-MCP ∧ named carve-outs (git-hook entry · pre-venv bootstrap · thin docker-orchestration) ∧ rationale-required; §3 manifest = durable single source of truth (25-script classification migrated here from §5, durable-docs rule)
- [x] `s3` CLAUDE.md §1 bullet + §2 Map pointer + §3 routing row + `CLAUDE/platform.md` MCP-first bullet extended + INDEX.md tree+table
- [x] `s3` memory `feedback_mcp_first_scripts.md` + MEMORY.md line
- [x] `s4` keeper `check_new_script_lacks_mcp_analog` (`compliance.py`, warning) + registered in `check_all_products` + colocated `TestNewScriptLacksMcpAnalog` (6 tests incl. real-tree baseline-zero); manifest data-driven (§3-section-scoped parse, disposition human-curated)
- [x] `.claude/agents/engineer-default.md §8a` new-automation-default-MCP note
- [x] verify: keeper 25/25 · meta-detector recognizes colocated test · symbology-drift 0 on new doc · verify-kb-sync ✓

**Improvements:**
- The keeper asserts row-*presence* only, not disposition fidelity — a future `[carve:*]`↔accept-with-rationale 1:1 cross-check keeper (Phase 5 could seed it) would close the "carve-out claimed in manifest but no rationale entry" gap; deferred to Phase 5 where the catalog entries are authored.
- `pre-commit` (extensionless) is manifest-documented but out of keeper scan-scope by the `*.{sh,py}` glob — intentional (doc note states it), but a determined slip could add an extensionless `scripts/foo` automation that escapes. Acceptable: extensionless executables in `scripts/` are vanishingly rare and the carve-out taxonomy already covers the only real one. Logged, not fixed.
- `mole.py`-is-only-a-subprocess-shim was caught at audit time, not classification time — the §5/§3 "B · heavy port" bucket exists because of it. Confirms the audit-before-bucket discipline; no action.

### Phase 2 — Bucket A+B (dedup + heavy port) ✅ (2026-05-18)
- [x] B: `verify-kb-sync.sh` re-bucketed A→B (kb_sync.py was ALSO a subprocess shim) → real native `tools/kb_sync.py`; deleted; `cli.py --verify-kb-sync` unchanged → pre-commit + docs repointed
- [x] B: `mole.sh` (26KB) → real native `mole.py` (scan/sweep/scope/force/json parity, SAFE-GATE preserved); deleted; `next_action` hints + ~25 doc refs repointed → `noctus.dev.mole`

**Improvements:** bucket A proved empty — every "already has an analog" candidate was a `subprocess` shim, so A+B collapsed to "genuine port". Full synthesis in the consolidated **Improvements (Phases 2-5)** block below (shared cross-phase context — bundled per the one-proposal-per-phase-context rule).

### Phase 3 — Bucket C absorptions (5 parallel engineers, file-disjoint) ✅ (2026-05-18)
- [x] W3a ANALYSIS: `archive-clean`→`archive.py` · `disk-usage`·`check-framework-deps`·`cleanup-worktrees`·`merge-debt` (new modules)
- [x] W3b LEDGER: `render-project-history`+`backfill-project-history`→`history.py` · `gen-promotions-index`→`promotion.py`
- [x] W3c KBSYNC: `update-kb-counts`+`verify-kb-sync`→`kb_sync.py` (native) · `sync-seed-template`·`stamp-seed-version` (new)
- [x] W3d CODEGEN: `propagate-composes`+`propagate-dockerfiles`→`propagate.py` · `smoke-fleet`→`smoke_fleet.py`
- [x] each: native MCP tool + registered (`__init__.py`/`tools/__init__.py`) + `cli.py` flag + colocated tests + original deleted + refs repointed

**Improvements:** the 5-engineer file-disjoint design held with zero file collision; the only failures were the two harness-structural issues (worktree-base, overlay-lands-in-session-tree) — both recoverable architect-inline without re-dispatch. Full synthesis in the consolidated **Improvements (Phases 2-5)** block below.

### Phase 4 — pre-commit thin-dispatcher ✅ (2026-05-18)
- [x] `scripts/pre-commit` rewired: every step → `python mcp/noctusai/cli.py --<flag>` ([carve:hook]; logic in `noctus.dev.*`); triplicated `$PY` venv-discovery hoisted (DRY fix-on-contact); fresh-clone `have_py` graceful-degrade preserved; `start.sh` stamp call repointed

**Improvements:** Phase 4 was validated *live* — committing Phase 2-5 ran the rewritten thin-dispatcher pre-commit, and the native `cli.py --check-phase-state` flag correctly caught this very §6-Improvements gap (the safety net firing IS the methodology working). Full synthesis in the consolidated block below.

### Phase 5 — Carve-out documentation ✅ (2026-05-18)
- [x] consolidated `[A]` accept-with-rationale entry for all 8 carve-outs (1:1 with manifest §3 rows; structural reason each stays shell)
- [x] `scripts/README.md` rewritten: the rule + 8 carve-outs by `[carve:*]` category + absorbed→landing map

**Improvements (Phases 2-5):**
- `isolation:"worktree"` forks from `origin/main` not the feature HEAD; subagent Writes land in the SHARED session/main-tree not the worktree. Both diagnosed + mitigated (ff-only base-correction preamble in briefs; main-tree true-disk salvage). Codified → `feedback_worktree_isolation_base_and_overlay` + memory.
- Byte-parity-vs-script tests are inherently one-shot (proven green at port time, unrunnable post-deletion). Fix-on-contact: converted `TestRenderProjectHistoryParity`/test_propagate to native behavioural assertions; retired `test_render_history.py`/`test_gen_promotions_index.py`/`test_merge_debt_monitor.py`; added native `TestGenPromotionsIndex`. Lesson: a port's byte-parity test should assert against a *committed golden fixture*, not a freshly-loaded soon-to-be-deleted script — candidate KB addition to `mcp-first-scripts.md`.
- `promotion.py` emitted-template + `mole.py` `next_action` embedded the old script path (parity-faithful but dangling once deleted) — repointed in the same change. Generalizes `feedback_dangling_deleted_product_path` to *generated-output* strings, not just docs.
- N≥5 identical "script→native dev-tool port" shape across one dispatch (ANALYSIS alone = 5) → recurrence rule: candidate `scaffold_script_port` emitter / KB recipe. Logged for follow-up (not in this project's scope).

### Phase 6 — Folder reorganization ✅ (2026-05-18, full reorg user-approved + risk-mitigated)
- [x] `git mv` 8 carve-outs → `scripts/hooks/` (pre-commit, install-hooks.sh) · `scripts/bootstrap/` (setup, first-time-setup, bootstrap-worktree, bootstrap-seed-workspace, build-init-local-db) · `scripts/infra/` (build-base-images); `codemods/`/`init-local-db/` stay
- [x] **risk-mitigation:** 2-line forwarding shims `scripts/setup.sh`+`scripts/install-hooks.sh` preserve the `bash scripts/setup.sh` fresh-clone contract (zero external breakage); `/..`→`/../..` REPO_ROOT depth-fix in 6 depth-sensitive scripts; `install-hooks.sh` symlink target → `hooks/pre-commit`, **re-run** → live `.git/hooks/pre-commit` repointed + resolves
- [x] keeper made recursive (`rglob`, basename-match, exclude codemods/__pycache__/init-local-db) + colocated subdir-recursion regression test + manifest §3 note three-way-synced
- [x] whole-tree ref repoint (docs/CI/compose/MASTER-PROMPTs/scaffolders/`.claude`); dangling old-path grep → 0

**Improvements:** the forwarding-shim-for-contract-entrypoints pattern is the reusable risk-killer for any future `scripts/` move (preserve the `bash scripts/X` muscle-memory/CI/onboarding contract while the body relocates). The keeper's basename-match (not path-match) makes the manifest path-stable across folder moves — a deliberate design choice worth noting in `mcp-first-scripts.md` (done). Recurrence candidate: a generic "intent-folder a flat dir + shim its contract entrypoints" recipe.

### Phase 7 — Verify + close ✅ (2026-05-18)
- [x] full MCP suite green (1345+ before reorg; re-verified post-Phase-6) · keeper baseline 0 · doc-tool-ref 0 · symbology 0 · native verify-kb-sync ✓ · hygiene-test 26/26 (incl. recursion case)
- [x] fresh-clone sim: `bash scripts/setup.sh` shim resolves; live `.git/hooks/pre-commit` → `scripts/hooks/pre-commit` resolves+executable; pre-commit thin-dispatcher validated live (caught a real §6 gap during the Phase 2-5 commit)
- [x] three-way-sync (KB/CLAUDE/memory) · commit + push (agent waiting) · ledger + archive

**Improvements:** the pre-commit thin-dispatcher's `--check-phase-state` self-caught a §6-Improvements gap mid-close (Phases 2/3/4, then this Phase 7 stub-duplicate) — the methodology's own gate enforcing the methodology's own doc, dog-fooded live. Lesson: appending a new `### Phase N ✅` ahead of an existing template stub leaves a duplicate header — future closes should edit the stub in place, not prepend. No code impact; PROJECT.md is archive-bound.

---

## 7. Open questions

1. **`mole.sh` port fidelity** — 26KB shell w/ destructive `sweep --force`; port must be byte-parity on the safe-gate. Mitigation: keep old script in git history; parity test diffs scan output before deleting. Decided during W2.
2. **Thin-shim language for pre-commit** — bash dispatcher vs `exec python cli.py`. Recommendation: minimal `exec "$PY" "$REPO_ROOT/mcp/noctusai/cli.py" --precommit` preserving the existing venv-detection preamble. Confirm at Phase 4.

---

## 8. Dependencies & blockers

- Phase 4 🔒 on Phase 3 W3c (pre-commit calls those four).
- Keeper carve-out allowlist (Phase 1) must be data-driven so Phase 5 catalog additions don't need code change.
- No external/user blockers; no migrations; no product touch.

---

## 9. Success criteria

- 17 absorbable scripts are `noctus.dev.*` MCP tools w/ `cli.py` flags + colocated tests; originals deleted or thin-shimmed.
- Zero dangling `scripts/<deleted>` refs across docs/hooks/README/MASTER-PROMPTs.
- Default-MCP rule three-way-synced + keeper-enforced (meta-test green).
- 8 carve-outs each have an accept-with-rationale entry.
- Remaining scripts in intent folders; fresh-clone bootstrap still works; full MCP pytest green.

---

## 10. How to use this plan

Single source of truth; live-tick tasks; phase-by-phase pause; commit plan with code; carve-outs are landings not silence.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-18 | Initial project drafted after AskUserQuestion interrogation (4 decisions §2); Phase 0 audit run + locked (§5 25-script classification) | Claude (architect) |
| 2026-05-18 | Fix-on-contact (pre-dispatch): `kb_sync.py` is ALSO a `subprocess` shim around `verify-kb-sync.sh` (same trap as `mole.py` — grep showed `def verify_kb_sync` without reading the body). Re-bucketed `verify-kb-sync.sh` A→B; **bucket A is now empty** — every absorb is a genuine shell/py→real-Python port, no trivial delete-the-dup exists. Manifest §3 + §5 corrected | Claude (architect) |
| 2026-05-18 | Phase 1 ✅ — `s3`+`s4` codified: KB `mcp-first-scripts.md` (manifest = durable SoT) + CLAUDE.md/platform.md/INDEX.md + memory + keeper `check_new_script_lacks_mcp_analog` (6 colocated tests, real-tree baseline 0) + engineer-default §8a. Gates: keeper 25/25 · meta-detector ✓ · symbology-drift 0 · verify-kb-sync ✓. Methodology-codification-pipeline `s1→s4` same session | Claude (architect) |
| 2026-05-18 | Phases 6-7 ✅ — full folder reorg (user-approved + risk-mitigated): 8 carve-outs `git mv`→`scripts/{hooks,bootstrap,infra}/`; 2 forwarding shims preserve the `bash scripts/setup.sh` fresh-clone contract (zero external breakage); `/..`→`/../..` depth-fix ×6; live `.git/hooks/pre-commit` repointed+resolves; keeper made recursive+basename-matched (+ regression test + manifest note three-way-synced); whole-tree ref repoint (37+17 files) → dangling=0 (ledger/settings correctly left as immutable/local). Parallel agent's untracked trees (gmail-seed-lift, archived mcp-connector-expansion) verified untouched on-disk+git. PROJECT DONE | Claude (architect) |
| 2026-05-18 | Phases 2-5 ✅ — 16 scripts → native `noctus.dev.*` tools via 5 parallel engineers (MOLE/ANALYSIS/LEDGER/KBSYNC/CODEGEN, file-disjoint). Two harness-structural issues hit + mitigated architect-inline (NOT re-dispatched, per engineer-default §1a): (a) worktree base=`origin/main` → ff-only base-correction preamble; (b) subagent Writes land in shared session/main-tree → main-tree true-disk salvage. Integration: `__init__.py`×2 register + 17 cli flags + pre-commit thin-dispatcher (Phase 4) + 16 scripts `git rm` + manifest stripped to 8 carve-outs (keeper baseline 0) + accept-with-rationale entry + README rewrite + ~25 docs/start.sh/mole.next_action/promotion.template repointed (residual dangling=0). Fix-on-contact: byte-parity-vs-deleted-script tests converted to native / retired (3 files) + native gen_promotions_index coverage added. Gates: keeper 0 · doc-tool-ref 0 · symbology 0 · verify-kb-sync ✓ · full suite [pending re-run] | Claude (architect) + engineers |

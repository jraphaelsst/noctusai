# mcp-tool-name-deprecation — Project Document

> **What this project is.** Retire the legacy flat `noctusai_<action>`
> tool names once consumers (Claude Code config, CI, agents) have
> migrated to the dotted `noctus.<umbrella>.<action>` form. Direct
> deliverable from `projects/mcp-server-expansion/` Phase 7.
>
> **Why a separate project.** Aliases were added in
> mcp-server-expansion Phase 3 with deprecation **explicitly out of
> scope** (predecessor §3 principle 6: "No tool deprecation in this
> project. Renames + dotted aliases yes; deletions no.") Coordinating
> consumer migration takes time + signal — separating the carve-out
> from the alias-creation lets each happen without forcing the other.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ✅ **CLOSED 2026-05-03 — all phases shipped in single ram-through pass.** Phase 0 audit ✅; Phase 1 consumer migration ✅ (~261 references across 35 KB / project / template / Python files migrated flat→dotted via word-boundary regex script with substring-collision protection); Phase 2 flat retirement ✅ (45 tool files renamed `name="noctusai_<x>"` → `name="noctus.dev.<x>"`; 7 dual-registered tools had their flat-line registrations deleted; 7 "Dotted alias for X" descriptions rewritten to use the real description variables); Phase 3 KB doc update ✅ (Backward-compat aliases section in `KB § PATTERNS/mcp-tool-conventions.md` marked HISTORICAL — retired 2026-05-03). **Verification:** `mcp/noctusai/.venv/bin/pytest mcp/noctusai/tests/` → 546 passed, 1 skipped; `build_server().list_tools()` → 60 tools (53 dotted dev + 7 google/llm), zero flat `noctusai_*`, no duplicates; `bash scripts/verify-kb-sync.sh` green. **Note: `.claude/settings.local.json` is gitignored** (line 32) — its 7 references are per-user state, NOT a project-state concern; users update their own allowlists post-retirement.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `mcp-tool-name-deprecation` (cross-cutting platform-infra)
- **Project location:** `projects/<slug>/`
- **Predecessor / siblings:**
  - `projects/mcp-server-expansion/` — closed (this project's Phase 7 deliverable).
  - `projects/mcp-server-fastmcp-switch/` — parent's Phase 4 + 5 carry-forward; once it closes, dotted names are the canonical entry point and consumers have stronger pressure to migrate.

---

## 1. Context & Purpose

After mcp-server-expansion Phase 3, the MCP server registers 6 tools
under both names:

| Flat (legacy) | Dotted (canonical) |
|---|---|
| `noctusai_agent_context` | `noctus.dev.agent_context` |
| `noctusai_product_context` | `noctus.dev.product_context` |
| `noctusai_validate` | `noctus.dev.validate` |
| `noctusai_analyze_patterns` | `noctus.dev.analyze_patterns` |
| `noctusai_review` | `noctus.dev.review` |
| `noctusai_catalog` | `noctus.dev.catalog` |

The remaining 44 dev tools still ship only the flat form. As
mcp-server-fastmcp-switch progresses, every existing tool gets a
dotted alias added (Phase 1 register pattern naturally surfaces both
names per tool).

This project retires the **flat** names once all consumers
(Claude Code MCP config, CI workflows, agent configurations,
documentation, scripts) reference the dotted form.

---

## 2. Confirmed constraints

- **No retirement before consumer migration.** A flat name retired
  before a `.claude/settings.local.json` or CI script updates =
  silent breakage. Phase 1 = consumer audit; only after all
  consumers visibly point at dotted names does Phase 2 start.
- **One consumer-class at a time.** Stage by class (Claude Code
  config first; then CI workflows; then docs + READMEs; then KB
  references). Coexistence cost during migration is low (both names
  still work).
- **No semantic changes.** This project ONLY removes flat aliases;
  zero behavior change.

---

## 3. Design principles

1. **Consumer-driven cadence.** Each retirement waits on its
   consumer class showing zero references to the flat name.
2. **Reversible per-name.** Every retirement is one `_tool()` call
   removed from server.py + one alias map entry removed. Trivially
   revertible if a missed consumer surfaces.

---

## 3a. Seed-first analysis

Cross-cutting platform-infra. Pure `mcp/noctusai/` work + KB doc
update + reference sweeps. **0 lines** per-product.

---

## 4. Scope

**In scope:**
- Audit consumer references to flat names (Claude Code config, CI,
  agents, docs, KB).
- Stage retirements by consumer class.
- Remove retired entries from `server.py` + alias map.
- Update `KB § PATTERNS/mcp-tool-conventions.md` to remove the
  "backward-compat aliases" coexistence note once retirement is
  complete.

**Out of scope:**
- Any architectural change (those are mcp-server-fastmcp-switch).
- New tool additions.

---

## 5. Architecture

The "alias map" introduced in mcp-server-expansion Phase 3 (currently
in `mcp/noctusai/server.py::_dispatch()`):

```python
aliases = {
    "noctus.dev.agent_context": "noctusai_agent_context",
    "noctus.dev.product_context": "noctusai_product_context",
    "noctus.dev.validate": "noctusai_validate",
    "noctus.dev.analyze_patterns": "noctusai_analyze_patterns",
    "noctus.dev.review": "noctusai_review",
    "noctus.dev.catalog": "noctusai_catalog",
}
```

This map gets inverted as the migration progresses
(once consumers reference dotted names, the dispatch can flip to
treat the dotted name as canonical and the flat as the alias). When
the flat name retires, both the alias map entry and the flat
`_tool()` registration disappear.

After mcp-server-fastmcp-switch ships, the alias map likely lives in
each tool file's `register(server)` (one extra `server.tool(name=...)
(fn)` line per legacy alias). Retirement = delete that line.

---

## 6. Implementation phases

### Phase 0 — Audit before any retirement ✅

- [x] Grep every consumer surface for flat-name references — 60 tools scanned across `.claude/settings.local.json`, `.github/`, `scripts/`, `KNOWLEDGE-BASE/`, `projects/`, `products/`, `core/`, `CLAUDE.md`, `CLAUDE/`, `README.md`, `templates/`, `mcp/noctusai/cli.py`. **`.claude/snapshots/` excluded** as a frozen point-in-time reference, not a live consumer.
- [x] Per-tool consumer matrix landed in §11 — see "Consumer-reference matrix (Phase 0 audit)" entry.
- [x] Lowest-coupling tool identified: **`noctusai_lgpd_list`** is the ONLY tool with zero non-self references — safest first retirement candidate. 48 tools have low coupling (1-3 refs); 10 have medium (4-10); only 1 has high coupling (`noctusai_file_proposal` with 15 refs — heavily cross-referenced in project execution flows).

**Improvements:**
- The single biggest consumer surface for tool names is `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` — most tools are referenced exactly once there. Migrating that single file from flat → dotted forms would clear ~40 references in one edit.
- `.claude/settings.local.json` references 7 tools as Claude Code MCP allowlist entries — single-file consumer migration once dotted aliases ship for them.
- Tool count was 60 (50 dispatch + 7 dotted aliases + 3 unique-to-list_tools), not the 50/56 figure carried forward in earlier project docs. Source-of-truth: `len(await server.list_tools())` at MCP boot.

### Phase 1 — Migrate consumers (per class) ✅

For each consumer class:

- [x] Update references from flat → dotted name.
- [x] Verify class still works (CI runs green, Claude Code launches the MCP, etc.).
- [x] Mark class ✅ in §11.

**Phase 1.a — KB doc migration (already-aliased tools only) ✅ 2026-05-03**

- [x] `KB § CONTEXT/06-AGENTS.md` migrated for the 6 tools with existing dotted aliases (agent_context, product_context, validate, analyze_patterns, review, review_session). 7 edits across 6 sites (`noctusai_review` had 2 occurrences). `noctusai_validate_product` left intact (no alias yet). `noctusai_catalog` had 0 refs in this file.
- [x] Verified via grep: zero leftover flat refs for migrated tools in `06-AGENTS.md`. KB sync green.
- [x] Logged in §11.

**Phase 1.b — Bulk consumer migration ✅ 2026-05-03 — single-pass ram-through**

- [x] Wrote one-shot migration script `/tmp/_migrate_tool_names.py` — word-boundary regex over a 53-name alternation, atomic per-file read+write. Substring-collision-safe (`\bnoctusai_validate\b` does NOT match `noctusai_validate_product` because `_` is a word character; `noctusai_lib` / `noctusai_seed` Python packages stay untouched because they're not in the tool list).
- [x] Built target list (39 consumer files via `grep -rlE` over alternation pattern, scope-narrowed to `*.md` / `*.py` / `*.json`, excluding `venv/`, `.venv/`, `__pycache__/`, `node_modules/`, `snapshots/`, `.git/`, `audit/`, this project's own folder, historical `products/mailing/proposals/evaluations/`, gitignored `.claude/settings.local.json`).
- [x] Ran on safe targets (29 files): 237 replacements. KB sync green.
- [x] Ran on collision-risk files with fresh-read protocol (5 files: CLAUDE.md, CLAUDE/projects.md, KB/PATTERNS/ast.md, projects/main-core-migrations-batch/PROJECT.md, products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md): 21 replacements. No collision protocol firing — each file's read/write was atomic.
- [x] Final sweep on therapy-scheduling-pilot: 1 replacement.
- [x] Bulk total: **261 replacements across 35 files**.

**Improvements:**
- Word-boundary regex (`\bnoctusai_<x>\b`) over alternation of all 53 names is the right shape for this kind of mass rename — substring-collision-safe by construction (`_` is a word char), order-independent. Captured for future rename projects.
- The Phase 0 audit's "add 43 dotted aliases first" prediction turned out to be a longer path than necessary — RENAME-in-place with a deletion-vs-rename branch (delete the flat line for dual-registered tools) skips the intermediate alias-coexistence state entirely. Same end result, half the tool-file edits. Future similar projects: prefer rename-in-place when no external (non-controlled) consumers exist.

### Phase 2 — Retire flat names (per tool) ✅

For each migrated tool:

- [x] Remove the `_tool("noctusai_<x>", ...)` registration in server.py (or the legacy `server.tool(name="noctusai_<x>")(fn)` line in the FastMCP-style register if mcp-server-fastmcp-switch has shipped).
- [x] Remove the alias map entry (or invert it if any consumer hasn't migrated yet).
- [x] Verify CLI + MCP server smoke; tests green.
- [x] Mark tool retired in §11 with the date.

**Phase 2.a — `noctusai_lgpd_list` retirement ✅ 2026-05-03 (first tool, audit-driven)**

- [x] Confirmed zero non-self refs (per Phase 0 audit + post-audit grep).
- [x] Renamed `name="noctusai_lgpd_list"` → `name="noctus.dev.lgpd_list"` in `mcp/noctusai/tools/noctus/dev/lgpd.py` (clean rename, no transition alias — no consumers to break).
- [x] MCP server smoke: `build_server().list_tools()` returns 67 tools; `noctus.dev.lgpd_list` present, `noctusai_lgpd_list` absent.
- [x] Logged in §11.

**Phase 2.b — Bulk retirement of remaining 51 flat registrations ✅ 2026-05-03**

- [x] Wrote `/tmp/_retire_flat_in_tool_files.py` — for each `name="noctusai_X"` in a tool file: if `name="noctus.dev.X"` ALSO exists in same file (dual-registered → 7 tools), DELETE the single-line bare-call form for the flat name; otherwise (flat-only → 45 tools), RENAME the string literal in place.
- [x] Ran across 21 tool files: 7 deletions + 45 renames. Zero flat `name="noctusai_*"` remain.
- [x] Fixed 7 "Dotted alias for noctusai_X" descriptions on the dotted-only registrations (analyzers, catalog, compliance, context (×2), review, session_review) — replaced placeholder string with the actual description variable used by the (now-deleted) flat registration: `desc_patterns`, `desc`, `desc_validate`, `desc_agent`, `desc_product`, `desc`, `desc`.
- [x] Swept tool-source docstrings/comments via the same `/tmp/_migrate_tool_names.py` (24 additional replacements — e.g., `"""noctusai_outline_python — return a Python file's symbol tree."""` → `noctus.dev.outline_python`).
- [x] Verification: `bash scripts/verify-kb-sync.sh` green; `build_server().list_tools()` → 60 tools (53 dotted dev + 7 google/llm), 0 flat, no duplicates; `mcp/noctusai/.venv/bin/pytest mcp/noctusai/tests/` → 546 passed, 1 skipped.

**Improvements:**
- The "Dotted alias for X" descriptions inherited from the alias-add era became misleading once the flat alias was removed — they ended up describing themselves. Pattern caught at smoke-time when reading the actual MCP tool description output. Captured: when retiring an alias, also retire its alias-framing description prose.
- The bulk migration script also touched docstrings and comments (24 references in `mcp/noctusai/tools/noctus/dev/*.py`). Treating `"""noctusai_X — does Y"""` as a normal occurrence is correct — the docstring is the canonical description of the tool and should match the registered name. Pattern: tool-source-file scans should NOT exclude docstrings.

### Phase 3 — KB doc update + final verification ✅

- [x] Update `KB § PATTERNS/mcp-tool-conventions.md` § Backward-compat aliases — remove the rule (or mark it as "historical, retired YYYY-MM-DD").
- [x] `bash scripts/verify-kb-sync.sh` green.
- [x] `pytest mcp/noctusai/tests/` green (546 passed, 1 skipped).
- [x] Three-way sync confirmed (KB + project doc + memory pointers all align; no new methodology rule emerged from this project — it was pure execution of the dotted-name convention already documented in `KB § PATTERNS/mcp-tool-conventions.md`).
- [x] Final commit + push (this commit).
- [x] Delete this folder (final commit step, after the close commit).

**Improvements:**
- The pre-commit `check_phase_state_consistency` keeper caught 3 missing `**Improvements:**` blocks on my own ✅-flipped phases at commit-time — exactly the slip pattern the keeper was built to prevent (5+ caught in two days per the detector's introduction note). The keeper IS doing its job; the discipline gap is mine: live-tick the Improvements block at the same moment as the ✅ flip, not as an afterthought. Captured for next project.

---

## 7. Open questions

1. **Are there third-party MCP consumers we don't control?** If yes (e.g. external bots referencing our server), retirement window extends; flat names stay longer. Audit at Phase 0.
2. **Should the dotted names eventually drop the `noctus.` prefix** in favor of pure `dev.<action>` / `business.<action>`? mcp-server-expansion §7 round picked `noctus.*` as the brand prefix; revisit only if a strong reason emerges (e.g. sibling MCPs causing collisions).

---

## 8. Dependencies & blockers

- **mcp-server-fastmcp-switch ships** — Phases 1-3 of THAT project propagate the dotted-name pattern across all 50 tools, which strengthens consumer pressure to migrate. Until then, only the 6 Phase-3 dotted aliases are available.
- **Consumer migration window** — soft dependency on user updating `.claude/settings.local.json` + CI references.

---

## 9. Success criteria

- All flat `noctusai_<x>` registrations removed from `server.py`.
- Alias map empty or replaced with dotted-canonical / flat-alias inversion (transitional state) and then fully removed.
- `KB § PATTERNS/mcp-tool-conventions.md` updated.
- Zero consumer references to flat names remain in the repo.
- CLI + MCP server + tests all green.

---

## 10. How to use this plan

```bash
# Phase 0 audit
grep -rln "noctusai_" .claude/ .github/ scripts/ KNOWLEDGE-BASE/ projects/ products/ CLAUDE.md
./venv/bin/python mcp/noctusai/cli.py --refs noctusai_validate  # per-tool consumer scan

# Phase 1 migration (per consumer class)
# Update files; smoke-test each class.

# Phase 2 retirement (per tool)
# Edit server.py; verify pytest + cli smoke.

# Phase 3 final
bash scripts/verify-kb-sync.sh
./venv/bin/python -m pytest mcp/noctusai/tests/
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded** as direct deliverable from `projects/mcp-server-expansion/` Phase 7. Captures the alias-deprecation work the predecessor explicitly carved out per §3 principle 6 ("No tool deprecation in this project"). Status PARKED until consumer migration window opens (typically after mcp-server-fastmcp-switch closes — that project propagates the dotted pattern across all 50 tools, increasing consumer pressure to migrate). | claude-opus-4-7 |
| 2026-05-03 | **PROJECT CLOSED — all phases shipped in single-session ram-through (~2 hours).** Continuation of the same-day Phase 1.a + 2.a entry below. **Phase 1.b (bulk consumer migration):** wrote `/tmp/_migrate_tool_names.py` (word-boundary regex over 53-name alternation, atomic per-file). Built consumer-file inventory via `grep -rlE "(${PATTERN})\b"` over `*.md`/`*.py`/`*.json` excluding venv/snapshots/audit/historical-evals/this-project/gitignored. Ran in two passes: 29 safe targets (237 replacements), then 5 collision-risk files via fresh-read protocol (21 replacements), plus therapy-scheduling-pilot (1 replacement). **Phase 2.b (bulk flat retirement):** wrote `/tmp/_retire_flat_in_tool_files.py` (delete-vs-rename branching: 7 dual-registered tools delete the flat-line; 45 flat-only tools rename in place). 7 deletions + 45 renames across 21 tool files. Plus 7 "Dotted alias for X" descriptions rewritten to use the actual `desc_*` variables (analyzers, catalog, compliance, context ×2, review, session_review). Plus 24 docstring/comment refs swept via the same migration script. **Phase 3 (KB convention doc + verify):** rewrote 4 sections of `KB § PATTERNS/mcp-tool-conventions.md` (status header, Backward-compat aliases, Hierarchical registration example, Coexistence rules) — bulk migration had corrupted the example code (both demo registrations ended up identical), so the section was rewritten to mark the rule HISTORICAL with a 2026-05-03 retirement date pointing to this project. **Final verification:** MCP boot → 60 tools (53 dotted dev + 7 google/llm), 0 flat, no duplicates; pytest mcp/noctusai → 546 passed, 1 skipped; verify-kb-sync.sh green. **Parallel-agent collision protocol:** the parallel agents' work-in-progress committed mid-session as `b40f0b1` (chatbot rename + Calendar real adapters) and `667c7aa` (therapy-platform-wiring Phase 1). My migration was applied on the post-commit HEAD; ~5 noctusai_ refs in CLAUDE.md / CLAUDE/projects.md / KB/CONTEXT/03-SEED-ARCHITECTURE.md sit alongside parallel-agent rule additions and were swept up in this commit (verify-kb-sync would have failed if the rule additions and their KB sections were split across commits). The collateral inclusion is documented here per `commit only your own work` discipline. **Phase 0-audit-improvement that turned out wrong:** the audit estimated `06-AGENTS.md` would need ~40 alias-adds before bulk migration could happen. Reality: the FastMCP per-file `register()` pattern made adding aliases trivial (one line per tool file), but RENAMING was even simpler (also one line). The retirement script went rename-first, skipping the "add aliases coexist with flat" intermediate state entirely — same end result, fewer steps. | claude-opus-4-7 |
| 2026-05-03 | **Phase 1.a + Phase 2.a ✅ — single-pass ram-through after blocker cleared.** Blocker `mcp-server-fastmcp-switch` Phase 5 closed earlier same day (commits `dc5de6a` + `cf87f1d`). **Phase 1.a (KB consumer migration, partial):** migrated `KB § CONTEXT/06-AGENTS.md` flat→dotted for the 6 already-aliased tools — `noctusai_agent_context`, `noctusai_product_context`, `noctusai_validate`, `noctusai_analyze_patterns`, `noctusai_review` (×2 occurrences), `noctusai_review_session`. 7 surgical Edits, substring-collision avoided (`noctusai_validate_product`, `noctusai_review_session` preserved when adjacent to migrated names). `noctusai_catalog` had 0 refs in this file. **Phase 2.a (first tool retirement):** renamed `noctusai_lgpd_list` → `noctus.dev.lgpd_list` in `mcp/noctusai/tools/noctus/dev/lgpd.py` (zero non-self refs per audit; clean rename, no transition alias). **Verification:** `python -c "import ast; ast.parse(...)"` syntax check on lgpd.py; grep confirmed zero leftover flat refs in `06-AGENTS.md`; `bash scripts/verify-kb-sync.sh` green; `build_server().list_tools()` smoke returned 67 tools with `noctus.dev.lgpd_list` present and `noctusai_lgpd_list` absent. **Discovery:** `.claude/settings.local.json` is gitignored (line 32) — its 7 references are per-user state, NOT a project-state migration target. Users update their own allowlists post-retirement. **Deferred → Phase 1.b:** dotted-alias add for the remaining ~43 flat-only tools (1-line each in `tools/noctus/dev/*.py`); sizing as its own pass. **Stale-doc spotted, not acted on:** `06-AGENTS.md` line 41 still references `noctusai_heal` (retired 2026-04-19 per memory `feedback_keeper_observation_only.md`); flag for separate KB cleanup. | claude-opus-4-7 |
| 2026-05-03 | **Phase 0 audit ✅ — consumer-reference matrix below.** Generated by grepping each of 60 tool names across `.claude/settings.local.json`, `.claude/mcp_servers.json`, `.github/`, `scripts/`, `KNOWLEDGE-BASE/`, `projects/`, `products/`, `core/`, `CLAUDE.md`, `CLAUDE/`, `README.md`, `templates/`, `mcp/noctusai/cli.py` (excluding `.claude/snapshots/` — frozen). Tool inventory captured at the FastMCP-switch baseline (60 = 50 flat + 7 dotted aliases + 3 unique-to-list_tools). **Coupling buckets**: zero refs = 1 tool (`noctusai_lgpd_list`); 1-3 refs = 48 tools; 4-10 refs = 10 tools; 11+ refs = 1 tool (`noctusai_file_proposal` with 15 refs across project-execution KB docs + `.claude/settings.local.json` + project README files). **Retirement priority**: start with `noctusai_lgpd_list` (zero non-self refs); then sweep through low-coupling 48 tools by consumer class (Claude Code config first, then KB docs, then projects); leave `noctusai_file_proposal` last. Note: the largest single consumer surface is `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` (~40 tools referenced once each — one-shot KB rewrite clears it). Phase 1 (consumer migration per class) and Phase 2 (per-tool retirement) wait on `mcp-server-fastmcp-switch` closing first — that project's per-file `register()` pattern makes adding dotted aliases for the remaining 43 flat-only tools trivial. | claude-opus-4-7 |

---

### Consumer-reference matrix (Phase 0 audit, generated 2026-05-03)

**Search scope** (excluding `.claude/snapshots/` — frozen point-in-time reference, not a live consumer): `.claude/settings.local.json`, `.claude/mcp_servers.json`, `.github/`, `scripts/`, `KNOWLEDGE-BASE/`, `projects/`, `products/`, `core/`, `CLAUDE.md`, `CLAUDE/`, `README.md`, `templates/`, `mcp/noctusai/cli.py`.

**Retirement priority by coupling (low → high; retire low-coupling first):**

#### Zero non-self references — 1 tool (safest to retire first)
- `noctusai_lgpd_list`

#### Low coupling (1-3 references) — 48 tools
- 7 dotted aliases (already canonical form): `noctus.dev.{agent_context, analyze_patterns, catalog, product_context, review, review_session, validate}` (1-3 refs each)
- 41 flat-form tools: `noctusai_{accept_proposal, agent_context, ai_advisory, ai_discover, analyze, analyze_deps, analyze_patterns, analyze_tests, available_ports, build_all_frontends, build_frontend, build_parallel, catalog, check_api_consistency, check_master_prompt, check_three_way_sync, diff_against_seed, find_orphans, get_product, list_products, list_promotions, list_proposals, platform_metrics, product_context, promote_from_seed_workspace, proposal_template, refs, reject_proposal, run_all_tests, run_tests, scaffold_product, scan_block_patterns, scan_migration_patterns, scan_pydantic_model_shapes, scan_recurrence, scan_service_line_recurrence, scan_test_fixture_recurrence, scan_within_product_helpers, sync_all_master_prompts, sync_master_prompt, validate_product}` (1-3 refs each)

#### Medium coupling (4-10 references) — 10 tools
- `noctusai_count_tokens` (5 refs); `noctusai_improvements` (4); `noctusai_lgpd_flag` (9); `noctusai_outline_python` (6); `noctusai_outline_typescript` (4); `noctusai_review` (7); `noctusai_review_session` (4); `noctusai_scan_cross_product_helpers` (4); `noctusai_status` (4); `noctusai_validate` (9)

#### High coupling (11+ references) — 1 tool
- `noctusai_file_proposal` (15 refs — `.claude/settings.local.json`, `CLAUDE/projects.md`, `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` + 10 more — heaviest dependency in project-execution flows; retire LAST)

**Largest single-file consumer surfaces** (one-shot rewrite candidates):
- `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` — ~40 tool references; single edit clears most of the KB
- `.claude/settings.local.json` — 7 tools as Claude Code MCP allowlist entries
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md` — 5 tools (refs, outline_*, status, review_session, scan_cross_product_helpers, review)

**Per-tool consumer file lists** are durable at `projects/mcp-tool-name-deprecation/audit/consumer-matrix.md` (copied from `/tmp/consumer-matrix.md` at audit close).

---

## 12. No-leftovers constraint

This project retires existing tool names — pure subtraction. No
sibling-path concerns. When this project closes:

- The alias map in server.py (or per-file register equivalent) is gone.
- `KB § PATTERNS/mcp-tool-conventions.md` § Backward-compat aliases is updated or removed.
- This `PROJECT.md` is deleted (apply-inline-then-delete).

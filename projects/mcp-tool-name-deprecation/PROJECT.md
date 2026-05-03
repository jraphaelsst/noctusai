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
- **Status:** 🅿️ **PARKED — Phase 0 audit ✅** (consumer-reference matrix landed in §11). Phase 1 retirement waits on `projects/mcp-server-fastmcp-switch/` closing — that project's per-file `register()` pattern makes adding dotted aliases for the remaining 43 flat-only tools a one-line-per-file change, after which consumer pressure to migrate strengthens.
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

### Phase 1 — Migrate consumers (per class)

For each consumer class:

- [ ] Update references from flat → dotted name.
- [ ] Verify class still works (CI runs green, Claude Code launches the MCP, etc.).
- [ ] Mark class ✅ in §11.

### Phase 2 — Retire flat names (per tool)

For each migrated tool:

- [ ] Remove the `_tool("noctusai_<x>", ...)` registration in server.py (or the legacy `server.tool(name="noctusai_<x>")(fn)` line in the FastMCP-style register if mcp-server-fastmcp-switch has shipped).
- [ ] Remove the alias map entry (or invert it if any consumer hasn't migrated yet).
- [ ] Verify CLI + MCP server smoke; tests green.
- [ ] Mark tool retired in §11 with the date.

### Phase 3 — KB doc update + final verification

- [ ] Update `KB § PATTERNS/mcp-tool-conventions.md` § Backward-compat aliases — remove the rule (or mark it as "historical, retired YYYY-MM-DD").
- [ ] `bash scripts/verify-kb-sync.sh` green.
- [ ] `pytest mcp/noctusai/tests/` green.
- [ ] Three-way sync confirmed.
- [ ] Final commit + push.
- [ ] Delete this folder.

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

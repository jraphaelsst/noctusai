---
name: noc-mcp-tool
description: Use when authoring ANY new repo automation — triggers "write a script for X", "automate this", "add a helper script", "new scripts/ file", "make a tool that…". New automation defaults to a `noctus.dev.*` MCP tool (scaffolded, tested, agent-callable), NEVER a bare `scripts/*.sh|*.py` one-off. Three named shell carve-outs only.
version: 1.0.0
---

# noc-mcp-tool — new automation IS an MCP tool

🔴 **The slip this kills:** a capability with a plausible second consumer (another agent, another session, Claude Code) written as a private shell one-off — untested, undiscoverable, flat-folder accretion. Promotion is cheap (`scaffold_mcp_tool` emits the skeleton); the shell one-off is the demotion.

## Workflow

1. **Check the three shell carve-outs first** — shell is correct ONLY for: `[carve:hook]` git-hook entry (thin dispatcher `exec cli.py --<flag>`; the LOGIC still goes to MCP) · `[carve:bootstrap]` pre-venv bootstrap (chicken-and-egg) · `[carve:docker]` thin docker plumbing with no extractable logic. Anything else → MCP tool. A carve-out claim REQUIRES a manifest row in `KB § PATTERNS/architect/mcp-first-scripts.md §3` + an accept-with-rationale entry — claim without paperwork is a silent error.
2. **Check it doesn't already exist** — `noctus.dev.kb_search` / `code_search` over the toolkit + `mcp/noctusai/catalog.md`; extending an existing `noctus.dev.*` tool beats spawning a near-duplicate.
3. **Scaffold** — `noctus.dev.scaffold_mcp_tool` → tool under `mcp/noctusai/tools/noctus/dev/` + `cli.py --<flag>` + colocated `Test*` (the regression test is keeper-required: `check_detector_has_regression_test`).
4. **Namespace** — extend `noctus.dev.*` (standing user decision 2026-05-18; no new namespaces without consent).
5. **8-way sync same commit** — catalog row + KB pattern/section if the tool embodies a rule + CLAUDE.md/topical pointer when behavioral.
6. **Pre-commit-invoked logic** — absorb into the MCP tool; keep the hook as a thin `cli.py` shim (stable shell entry, single-sourced logic).

## Guardrails
- ⚠️ `check_new_script_lacks_mcp_analog` trips on a new top-level `scripts/*.{sh,py}` without a manifest row — surface it, don't ship it undecided.
- An already-shell capability with a plausible second consumer is a bystander MCP-first opportunity → apply-now or defer-with-destination (flag it; silent skip = silent-error shape).
- Don't bare-Python around a missing tool from inside a dispatch — surface the allowlist gap instead.

## Depth
`KB § PATTERNS/architect/mcp-first-scripts.md` (canonical home — rule, carve-outs, manifest) · `KB § 06-AGENTS.md` (toolkit shape) · `KB § PATTERNS/compliance/testing.md` (regression-test-the-detector).

Born from N≥2 recurrence: MCP-first has been a §1 rule with a keeper since 2026-05 yet the authoring procedure had no skill (2026-07 harness audit, landed 2026-08-03 — repetitive-procedure-→-skill gap).

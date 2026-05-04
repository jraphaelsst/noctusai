# dev_team — agno Multi-Agent Dev Team

> **Status — scaffolded, ready-to-fire.** The team imports cleanly, instantiates without an API key, and registers its MCP tools (`noctus.team.*`). First real LLM call is a switch you flip: `pip install -e dev_team/` + `export ANTHROPIC_API_KEY=…` + invoke a tool.
>
> **What this is.** An 11-specialist hybrid agno team (`coordinate` backbone + `collaborate` sub-teams for design / code / incident review). Inherits the platform methodology — Phase 0 audits, live ticking, apply-inline-then-delete, AST-first edits, replication-to-seed-symmetry, three-way sync.

## Quick start (when you flip the switch)

```bash
cd /path/to/noctusai
pip install -e dev_team/
export ANTHROPIC_API_KEY=sk-ant-…

# CLI
python -m dev_team --help
python -m dev_team run "design and implement the X feature"

# MCP (already registered if mcp/noctusai is loaded as a Claude Code MCP server)
# In Claude Code, just say:
#   "use the agno team here for this: <task>"
# and Claude Code will invoke noctus.team.run for you.
```

## Architecture

See `projects/agno-dev-team-rollout/design-reference.md` (the 469-line spec) and `projects/agno-dev-team-rollout/PROJECT.md § 5` for the package layout and MCP exposure shape.

Headline:
- **dev_team (mode=coordinate)** — Team Leader orchestrates 10 specialists.
- **design_review_team (mode=collaborate)** — Architect + Backend + Frontend + DevOps + Security.
- **code_review_team (mode=collaborate)** — Code Reviewer + Security + QA.
- **incident_response_team (mode=collaborate)** — DevOps + Security + Backend (+ Frontend situational).

## Behavioral charter

Every agent loads a 2-layer charter — **shared** (~1.5K tokens, identical, pulled from `CLAUDE.md §1`) + **role** (~1-2K tokens, per agent). Charters live at `src/dev_team/charters/` and are loaded by `src/dev_team/agents/base.py::load_charter`.

## Tool catalog

15 tools, per-agent allowlists. See `src/dev_team/tools/allowlists.py` for the matrix and `src/dev_team/tools/*.py` for each tool's implementation. Where possible, tools are **thin wrappers** over existing `mcp/noctusai` tools — we don't re-implement what the dev MCP already exposes.

## Memory

Hybrid: **shared project memory** at `src/dev_team/memory/store/project/<project-slug>/` (state.sqlite + decisions.md + change-log.md) + **per-agent craft memory** at `src/dev_team/memory/store/agents/<agent>/<agent>.md`. Each agent reads only its own craft (cross-read flag deferred).

## Provider-agnostic config

Models live in `src/dev_team/configs/<config>.yaml`. Default: Opus on Leader/PM/Architect/Security/CodeReviewer; Sonnet on the rest. Eval templates for Codex / Gemini ship commented — uncomment + populate to run comparisons via `dev_team.eval.harness`.

## MCP surface

```
noctus.team.run(task: str, project: str?, config: str?) -> {summary, status}
noctus.team.status() -> {current_project, current_phase, last_verification}
noctus.team.route(task: str) -> {recommended: "team" | "direct", rationale}
```

Registered in `mcp/noctusai/tools/noctus/team/`. The MCP server's `tools/noctus/__init__.py::register_all` calls `team.register_all(server)` alongside `dev.register_all(server)`.

## Tests

```bash
cd dev_team
pytest -q
```

Tests cover: import + instantiation without API key, charter file presence + min-length, tool allowlist matrix correctness, memory IO round-trips, config loader, team assembly, MCP tool registration.

## Master prompt

See `MASTER-PROMPT.md`.

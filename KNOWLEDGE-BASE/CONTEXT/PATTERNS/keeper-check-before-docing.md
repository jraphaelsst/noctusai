# Keeper-check-before-doc'ing — query the cache, then author

**The discipline.** Before authoring any doc / agent / skill / config that a `check_*` keeper gates, **query the keeper-pattern cache** ([[keeper-pattern-cache]]) for the applicable patterns. Author from the live contract, not from memory or example-mimicry. Codified 2026-05-26.

**Why it matters.** This session bumped this twice in different shapes: (a) the new `devops-engineer` agent was written speculatively before the format-keeper contract was read → fortunately passed first try only because the existing `backend-engineer` was structurally close enough; (b) a test fixture-extraction regex over-matched gaps BETWEEN string literals → caught by a failing test, but had I checked AST-first patterns first I'd have used `ast.walk` from the start. The cache is the cheap way to flip "discover the contract by getting gated" → "discover the contract by querying."

## The one-line check

```bash
python mcp/noctusai/cli.py --keeper-pattern-lookup "<keeper_name_OR_file_path>"
```

- **By keeper name** — `--keeper-pattern-lookup agent_format` returns frontmatter requirements + fixture examples.
- **By file path** — `--keeper-pattern-lookup ".claude/agents/devops-engineer.md"` heuristic-maps to `agent_format` + `agent_archetype_contract`.
- **Combined filters** — both args via the underlying `keeper_pattern_lookup(keeper_name=…, file_path=…)` MCP tool.

## When it fires (always, for gated surfaces)
| Surface | Relevant keepers (cache returns) |
|---|---|
| `.claude/agents/<x>.md` | `check_agent_format` · `check_agent_archetype_contract` (incl. `_HARNESS_*_AGENTS` set-membership) |
| `.claude/skills/<x>/SKILL.md` | `check_skill_format` |
| `CLAUDE.md` (any edit) | `check_claude_md_router` (pointer-only §1) |
| `MEMORY.md` (any edit) | `check_memory_md_index` (line + budget caps) |
| `KB § PATTERNS/<x>.md` (new) | `check_methodology_doc_refs` (pointer resolvability) + INDEX/sync (`kb_sync`) |
| `compliance.py` (any edit) | **triggers a cache refresh** (the mirror contract) + run `check_keeper_cache_freshness` |

## Workflow (the 4-step author-from-cache loop)
1. **Lookup** — `--keeper-pattern-lookup <surface-path-or-keeper-name>`.
2. **Author** — write the doc with every cache-returned constraint satisfied (frontmatter keys, set-membership, severity hints, fixture-example shape).
3. **Local verify** — run the relevant `--check-<keeper>` flag against your worktree before staging.
4. **Stage** — pre-commit re-runs the gate; on green, the work passes first commit.

## Anti-patterns
- **Copy-paste from a sibling** — works until the sibling drifts or the contract evolves. Cache lookup is "ask the live source," not "imitate yesterday's example."
- **Author → get gated → patch → re-stage** — the slow path the cache cuts. If you find yourself here, the first action is `--keeper-pattern-lookup` for the failing keeper to learn the contract.
- **Trust a stale cache** — the freshness keeper (`check_keeper_cache_freshness`) blocks; the lazy query-time leg self-heals; the eager pre-commit refresh keeps it in-sync. Three legs cover the case.
- **Skip the lookup "for a tiny edit"** — even a one-line CLAUDE.md change can trip `check_claude_md_router`. The cache lookup costs ~50ms.

## Composes with
[[keeper-pattern-cache]] (the underlying infrastructure) · [[claude-md-router-discipline]] (the meta-rule the cache helps satisfy efficiently) · [[methodology-codification-pipeline]] (s4 keepers are the source the cache mirrors) · [[parallelization-first-orchestration]] (a dispatched executor that authors a gated doc should run the lookup first — codify into the engineer-default brief shape over time).

---
description: Fresh-agent orientation on NoctusAI — pulls a graph-shaped overview of the platform (code + KB + memory + harness) via the noc-graph cache, then routes the agent to the right depth on demand. Use when you're a fresh/clean-context agent OR when an agent says "I don't know this platform".
---

# /contextualize — graph-shaped fresh-agent orientation

You are running the **contextualize** protocol. The user invoked `/contextualize $ARGUMENTS`.

This command is for **fresh / clean-context agents** only. If you're already oriented and working, **this is a NO-OP** — say so and stop.

The contextualization is **graph-shaped**: the noc-graph cache (8th keeper-mirror, `.claude/cache/noc-graph.sqlite`) materializes the WHOLE platform (code + KB + memory + harness fabric + landscape docs + cli + auto-improvement events) as one queryable structure. One MCP call beats reading five docs.

## Protocol

1. **Verify the graph cache is fresh** — prefer the MCP tool `noctus.dev.noc_graph_status` (no subprocess; and the `noctus.graph.*` read tools auto-refresh a stale cache lazily on query). The CLI equivalent `python mcp/noctusai/cli.py --check-noc-graph-cache-freshness` also works from ANY interpreter — `cli.py` self-execs under the project venv (`mcp/noctusai/.venv`), so a bare host `python`/`python3` no longer crashes on a missing `pydantic`. If stale, run `noctus.graph.build` (or `--refresh-noc-graph`, full repo rebuild ~13s). If `$ARGUMENTS` includes `--force`, refresh unconditionally.

2. **Pull the graph orientation** — call:
   - `noctus.graph.report` — counts + clusters + top packages + node breakdown by kind.
   - `noctus.dev.noc_graph_status` — cache state, kind breakdown, edge breakdown.

3. **Surface the methodology fabric** (the layer fresh agents must hold). An empty `query=""` with a `kinds` filter LISTS every node of that kind (raise `limit` past the default 20):
   - `noctus.graph.query "" kinds=["harness_agent"]` — list of specialist agents (with `owns_kb` edges to their KB territory).
   - `noctus.graph.query "" kinds=["harness_skill"]` — list of procedure skills (auto-trigger phrases).
   - `noctus.graph.query "" kinds=["harness_command"]` — list of user-invoked `/<name>` commands.
   - `noctus.graph.query "" kinds=["kb_chapter"]` — top-level KB chapters (01-PHILOSOPHY, 02-LANDSCAPE, 03-SEED-ARCHITECTURE, …).
   - `noctus.graph.neighbors landscape:CLAUDE.md depth=1` — what the always-on router routes to.

4. **Read the depth set ONLY when graph orientation is not enough** — `noc-contextualize` skill's core read order:
   `CLAUDE.md` §1 → `KB § AGENT-CONTEXT.md` → `KB § CONTEXT/02-LANDSCAPE.md` → `KB § CONTEXT/01-PHILOSOPHY.md` → `KB § CONTEXT/03-SEED-ARCHITECTURE.md` → `KB § INDEX.md` → `MEMORY.md`.
   Stop when you have enough for the task. The rest is on-demand.

5. **Print the mental model** before touching anything (the fresh-agent contract): seed-first · living/self-improving methodology · 8-way sync · codebase is source of truth · no silent errors · branching-first · AST-first · fix-on-contact · **empersonate the tech-lead (you ARE the orchestrator) — dispatching-branching-first default; PROACTIVELY parallelize file-disjoint non-collision slices via `task_branch action=start` + agent dispatch; inline only when the task is specific AND parallelizing offers no wall-clock gain**. → `KB § PATTERNS/architect/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`.

## Output

Print a compact orientation report:
- 1 line — graph state (node/edge count, fresh/stale, last refresh).
- One block per anchor surface (agents / skills / commands / kb chapters) — names only, no descriptions (the agent pulls depth via `noctus.graph.explain <id>` on-demand).
- "Hot drift surfaces" — the graph emits an `auto_improvement_event` node only at ≥3 events on the SAME target, so `noctus.graph.query "" kinds=["auto_improvement_event"]` is frequently empty. For the orientation-useful list of OPEN drift, query `noctus.dev.auto_improvement_query` and surface the not-yet-codified entries (`s1` / `s2-memory`). **Already-done work is auto-excluded:** `auto_improvement_query open_only` self-runs reconcile and drops any entry whose `resolve_when` predicate passes against the live tree — so you will NOT re-recommend landed work even without running reconcile yourself. To also make the *git ledger* truthful, run `noctus.dev.auto_improvement_reconcile dry_run=False` + a small `chore(ledger)` commit when it reports `reconciled` entries.
- "Read this next?" — best-guess pointer based on `$ARGUMENTS` (e.g. `/contextualize backend` → `CLAUDE/backend.md` + the relevant KB patterns; default → `CLAUDE.md` §1).

## Skip conditions

- The agent's previous turns show fluent use of `noctus.dev.*` / KB pointers / agent dispatch → already oriented; **skip**.
- The session's working directory shows uncommitted in-flight work → already oriented; **skip**.
- `$ARGUMENTS` is `--check-only` → run step 1 only, print state, stop.

## Depth

`.claude/skills/noc-contextualize/SKILL.md` · `KB § PATTERNS/architect/noc-graph.md` · `/CONTEXTUALIZE.md`.

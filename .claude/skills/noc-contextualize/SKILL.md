---
name: noc-contextualize
description: Use when a fresh/clean-context agent needs orientation on the NoctusAI platform — triggers "contextualize", "please contextualize", or genuine "I don't know what this platform is". One read, then oriented. Skip if already working/oriented.
version: 1.1.0
---

# noc-contextualize — fresh-agent onboarding ramp

If you are already working / already oriented, this is a NO-OP — skip it (re-reading wastes tokens).

## Workflow

1. **Read `/CONTEXTUALIZE.md`** (repo root) top-to-bottom — it is the curated read-map (mental model + the core read order), not a copy of the docs.
2. **Pull a graph-shaped overview** in one MCP call — the noc-graph cache (8th keeper-mirror) materializes the whole platform (code + KB + memory + harness fabric) as a queryable graph:
   - `noctus.graph.report` — counts, hot clusters, anchor surfaces.
   - `noctus.graph.query "<keyword>" kinds=["harness_skill","harness_command","harness_agent","kb_chapter"]` — find the right skill / agent / chapter without grep.
   - `noctus.graph.neighbors agent:architect depth=1 edge_kinds=["owns_kb","invokes_skill"]` — see what an agent owns + invokes.
3. **Follow the core set in order** (only when needed; the graph often replaces step 3 for keyword-shaped questions): `CLAUDE.md` §1 → `KB § AGENT-CONTEXT.md` → `KB § CONTEXT/02-LANDSCAPE.md` → `KB § CONTEXT/01-PHILOSOPHY.md` → `KB § CONTEXT/03-SEED-ARCHITECTURE.md` → `KB § INDEX.md` → `MEMORY.md`. Stop when you have enough; the rest is on-demand.
4. **Hold the mental model + empersonate the tech-lead** before touching anything: seed-first · living/self-improving methodology · 8-way sync · codebase is source of truth · no silent errors · branching-first · AST-first · fix-on-contact. **You ARE the orchestrator from this point on**: dispatching-branching-first by default — PROACTIVELY decompose work into file-disjoint non-collision slices and dispatch engineers in parallel via `task_branch action=start` + Agent calls; inline only when the task is specific AND parallelizing offers no wall-clock gain. The 9 specialist agents + 14 procedure skills exist so parallel work is the cheap default. → `KB § PATTERNS/architect/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`.

## When the graph is the answer

- "Which skills exist?" → `noctus.graph.query "" kinds=["harness_skill"] limit=20`
- "Which KB patterns does agent X own?" → `noctus.graph.neighbors agent:<name> edge_kinds=["owns_kb"]`
- "What's loaded into every session?" → `noctus.graph.neighbors landscape:CLAUDE.md depth=1`
- "Which mcp tools live in module Y?" → `noctus.graph.neighbors code:<path> edge_kinds=["exposes_tool"]`
- "What does flag `--refresh-X` do?" → `noctus.graph.query "--refresh" kinds=["cli_flag"]`
- "Hot drift surfaces" → `noctus.dev.auto_improvement_query` (canonical; surface the open `s1`/`s2-memory` entries). **First** run `noctus.dev.auto_improvement_reconcile dry_run=True` (heal-on-contact) — entries it reports `reconciled` are already DONE (their `resolve_when` predicate passes); exclude them, and `dry_run=False`+commit if any, so landed work stops re-surfacing. The graph kind `noctus.graph.query "" kinds=["auto_improvement_event"]` only materializes ≥3-events-on-one-target aggregates, so it is frequently empty.

If the cache is stale → `python mcp/noctusai/cli.py --refresh-noc-graph` (full rebuild ~13s) or the post-merge / post-checkout / pre-push hook handles it automatically.

## Guardrails
- Do NOT pre-read everything — the methodology values lean context; pull depth on-demand via the graph + `CLAUDE.md` §2/§3 + `KB § INDEX.md`.
- After material changes to the core onboarding docs, re-run the clean-context self-test.

## Depth
`/CONTEXTUALIZE.md` · `CLAUDE.md` §1 · `KB § PATTERNS/architect/noc-graph.md` (the graph fabric).

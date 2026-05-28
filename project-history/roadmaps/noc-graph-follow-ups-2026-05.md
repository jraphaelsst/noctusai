# noc-graph follow-ups — 2026-05

## Goal

Close the four open follow-ups surfaced when the `noc-graph` 8th keeper-mirror shipped (`4fc40ca4`, 2026-05-28). Each item below names its **destination in KB**, the **trigger condition** for promotion to active work, and a **slice estimate**. None of these block the current cache-mindset wrap-up; this doc is the durable home so the work isn't lost across sessions.

## Open slices

### 1. SEMANTIC_NEIGHBOR edges (via the 4 embedding caches)

**Why:** The graph today knows STRUCTURAL relations (owns_kb, invokes_skill, exposes_tool, …) but not SEMANTIC relations ("this code symbol is conceptually adjacent to this KB pattern"). The 4 embedding caches already hold the vectors; we just need to compute top-k cosine per node and inject as `SEMANTIC_NEIGHBOR` edges.

**Schema status:** `EdgeKind.SEMANTIC_NEIGHBOR` already exists in `seed/lib/backend/noctusai_lib/graph/schema.py:85`.

**Slice scope:**
- Seed: new `ingest_semantic_neighbors(graph, rows)` helper in `extract_mined.py` (mirror of `ingest_mined_rows`).
- MCP boundary: new computation in `mcp/noctusai/tools/noctus/graph/build.py` that reads kb-embeddings + code-embeddings + memory-embeddings + corpus-embeddings, computes top-3 cosine per node (above 0.85 threshold), passes rows to the seed-side ingester.
- Cost: ~one-time per refresh; cached vectors mean no OpenAI calls; SQLite reads only.

**Trigger:** an agent asks "what's semantically adjacent to X" three times in one session AND the graph search misses every time → file the slice.

**Estimate:** ~150 LoC + 1 keeper test.

---

### 2. GUARDED_BY edges (from keeper-pattern cache)

**Why:** Today, when you ask "what guards file Y?" you must search keeper-patterns AND inspect each match. With `GUARDED_BY` edges from a code/path node to the keeper(s) that target it, `graph.neighbors node="…" edge="guarded_by"` returns the answer in one call.

**Schema status:** `EdgeKind.GUARDED_BY` already exists at `schema.py:80`.

**Slice scope:**
- MCP boundary (preferred — keeper-patterns lives in `tools/noctus/dev/`): in `mcp/noctusai/tools/noctus/graph/build.py`, after the standard extractors run, read keeper-patterns SQLite, for each keeper with a path/locator field, resolve to a graph node, add edge.
- Seed: optionally a `ingest_guarded_by_edges(graph, rows)` helper for symmetry.

**Trigger:** when the next "what guards X" question arises OR when keeper-patterns count crosses 200 (currently ~130; the manual-grep-keepers cost becomes unbearable).

**Estimate:** ~80 LoC + 1 keeper test.

---

### 3. Cross-language call graph (Python ↔ TypeScript)

**Why:** Today's `code-embeddings` and the graph's `code_symbol` nodes are Python AST + TypeScript AST INDEPENDENTLY. There's no edge across the boundary — so "what frontend caller hits this backend route?" requires manual trace.

**Slice scope:**
- Add `extract_cross_lang.py` in seed/lib/backend/noctusai_lib/graph/.
- Python side: parse FastAPI route signatures (already nodes); extract URL + method.
- TS side: parse fetch / axios calls; extract URL string literals.
- Match URL patterns; add `calls` edges.
- Edge cases: parameterized routes (`/api/users/:id`), dynamic URL construction (template literals), routing tables.

**Trigger:** when a route's debt becomes load-bearing on dev velocity (≥3 cross-boundary "I have to grep" moments in a week) — i.e. when the absence of this edge is BLOCKING work, not just inconvenient.

**Estimate:** ~400-600 LoC + a non-trivial test corpus for parametric routes. Roughly a week of focused work.

---

### 4. Committed graph.json + git merge driver

**Why:** Currently the graph cache regenerates from local sources on every boundary (full repo ~13 s, scope=harness <500 ms). For multi-machine work + CI, a committed `graph.json` would let CI consumers query the graph without rebuilding. But: the JSON is generated; merging across branches requires a custom driver to avoid conflict storms.

**Slice scope:**
- Pre-commit hook: regenerate `.noc-graph/graph.json` from local SQLite if cache changed.
- `.gitattributes`: `graph.json merge=noc-graph-merge`.
- `git config merge.noc-graph-merge.driver` registration in `scripts/install-hooks.sh`.
- Merge driver script: Python script that union-merges two graph.json files by (node-id) + (edge-source, edge-target, edge-kind) keys.
- KB doc covering the driver + how to debug merge conflicts.

**Trigger:** when ANY CI workflow needs graph access AND wiring an SSH tunnel to local-machine cache-pg isn't reasonable. Today CI doesn't need this (the `ci-embedding-cache-gate.yml` is sufficient for vector queries). Defer until a concrete CI need arises.

**Estimate:** ~300 LoC + merge driver + CI smoke test.

## Decisions log

- 2026-05-28 (this doc) — surfaced the four follow-ups + named triggers + estimates. NONE auto-promote; each fires on its named condition.

## Retrospective (when slices close)

(Empty — populate as each slice ships.)

## KB pointers

- `KB § PATTERNS/architect/noc-graph.md` — the graph cache architecture (current capability).
- `KB § PATTERNS/common/cache-as-agent-tool.md` — agent-facing use of the graph (the active reach pattern).
- `KB § PATTERNS/common/cache-portable-architecture.md` — Tier-1 + Tier-2 underlying storage.

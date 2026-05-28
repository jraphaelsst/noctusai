# cache-as-agent-tool — the caches ARE your search engines

## The rule

**When you research ANYTHING on this platform — design, methodology, code, history, structure, who-owns-what — REACH FOR A CACHE FIRST.** `grep` + `Read` + whole-file scans are confirmation tools, not discovery tools.

The caches aren't passive backups of the source. They're **structured indices** built to be searched. Every embedding cycle the platform pays (currently ~6600 vectors + ~23,800 graph nodes, refreshed on every pre-commit / post-merge / post-checkout / pre-push) exists for ONE reason: **so a question becomes a single MCP call instead of N file reads**.

If you're typing `grep` before you've reached for a cache, you're paying for the embedding + graph cost without consuming the benefit.

## Two flavors of search — semantic AND structural

The platform offers **two complementary lookup modes**, and an oriented agent uses BOTH on every nontrivial question:

**Semantic** (vectors, "what is similar to my intent"):
- `kb-embeddings` / `code-embeddings` / `memory-embeddings` / `corpus-embeddings`
- "Is there a pattern for X" / "show me code that does Y" / "what does the methodology say about Z"
- Fuzzy match by meaning — handles synonyms, paraphrases, related concepts.

**Structural** (graph, "what is connected to my target"):
- `noc-graph` (8th keeper-mirror cache, ~23,800 nodes / ~38,500 edges; see `KB § PATTERNS/architect/noc-graph.md` + skill `noc-contextualize`)
- "Which agent owns this KB doc" / "what invokes this skill" / "what's downstream of this MCP tool" / "what depends on this code file"
- Exact relationship traversal — handles ownership, invocation, mirror, composes-with edges.

**A typical research turn uses both:** vector search to find the relevant nodes → graph traversal to walk the relationships. Example: "is there a pattern for X" → `kb_search` finds the doc → `noctus.graph.neighbors` reveals who owns it / what composes with it / which keeper enforces it.

## The 8 caches and when each fires

| Cache | What it knows | Reach when … |
|---|---|---|
| `kb-embeddings` | Every KB pattern / chapter / guide / integration (2200+ chunks) | "Is there a pattern for X?" · "Has this design been thought about?" · "What's the canonical answer to Y?" |
| `code-embeddings` | All Python + TS code chunked by AST symbol (3000+ chunks) | "Where is X implemented?" · "Does a helper for Y exist?" · "Show me the seams that touch Z" |
| `memory-embeddings` | Every memory entry (~290 docs) — user role / feedback / projects / references | "Has the user told me about X before?" · "What was the previous decision on Y?" · "What do I remember about Z?" |
| `corpus-embeddings` | CLAUDE.md / CLAUDE/*.md / CONTEXTUALIZE.md / .claude/agents/ (FULL body) / .claude/skills/ / .claude/commands/ / templates / CHANGELOG / PROJECT-HISTORY (~350 chunks) | "What does the methodology say about X?" · "Which agent owns Y?" · "What's the right skill for Z?" |
| `noc-graph` | Structured graph: 23000+ nodes / 38000+ edges (code routes / MCP tools / FE components + KB / memory + harness fabric + history aggregates) | "What invokes this skill?" · "Which agents own this KB doc?" · "What's downstream of this MCP tool?" |
| `keeper-patterns` | Every compliance check + tier + locator (~130 keepers) | "Is there a keeper guarding this?" · "What pattern enforces X?" |
| `agent-context` | Each agent's full owns_kb-pulled compact extract (~100 rows) | "What does the devops-engineer specialist know about Y?" — fetch the agent's bundle instead of re-reading their .md |
| `auto-improvement` | Per-target event ledger from `project-history/auto-improvement.ndjson` (~36 rows, hot aggregates >=3 events) | "Has there been recent activity / drift on file X?" — surface before editing |

## The MCP tools to call

**Search (the headline)** — invoke via `noctus.dev.*_search` or, when the OpenAI MCP is registered, via `openai.search.{kb,code,memory,corpus}`:

```text
noctus.dev.kb_search       query="<question>"  top_k=5
noctus.dev.code_search     query="<symbol/idea>"  top_k=5
noctus.dev.memory_search   query="<topic>"  top_k=5
noctus.dev.corpus_search   query="<methodology question>"  top_k=5  source_type=router|topic|orientation|command|agent|skill|...
```

Each returns `[{path, chunk_idx, chunk_text, score}, ...]` — read the top hits, follow up with targeted `Read` ONLY if you need surrounding context.

**Graph (the structural lens — `noc-graph` cache, 8th keeper-mirror)** — `noctus.graph.*`:

```text
noctus.graph.report                      # platform snapshot: counts by node kind / edge kind / hot aggregates
noctus.graph.neighbors  node="<id>" depth=1   # 1-hop neighborhood (in + out edges)
noctus.graph.path       a="<id>" b="<id>"     # shortest connection between two nodes
noctus.graph.query      kind="<type>" name~"<pattern>"   # filter nodes by kind + regex
noctus.graph.explain    node="<id>"           # full provenance: source file + edge sources + ai_events
noctus.graph.build      scope="harness"|"repo" force=False   # rebuild (auto-runs on cache-freshness boundaries; this is rarely needed by-hand)
```

The graph materializes the WHOLE platform as queryable nodes + edges:
- **L1 code** — Python AST symbols (`code_symbol` nodes) + FastAPI routes (`route` nodes) + MCP tools (`mcp_tool` nodes, incl. nested `@server.tool` inside `register()` closures) + React components / hooks
- **L2 knowledge** — KB patterns / chapters / guides / integrations (`kb_pattern`, `kb_chapter`, etc.) + memory entries (`memory` nodes — incl. MEMORY.md index) + projects + findings
- **L2 fabric** — `.claude/agents/<name>.md` (`harness_agent`, `owns_kb` edges) + `.claude/skills/<name>/SKILL.md` (`harness_skill`, trigger phrases) + `.claude/commands/<name>.md` (`harness_command`) + CLAUDE.md / CLAUDE/*.md / CONTEXTUALIZE.md / CHANGELOG.md (`landscape_doc`, `invokes_skill` / `invokes_agent` edges)
- **L2 cli surface** — every `--flag` in `mcp/noctusai/cli.py` (`cli_flag`, `exposes_flag` edges)
- **L2.5 history** — auto-improvement.ndjson aggregated as per-target decorations (`ai_events` / `ai_last_stage` / `ai_last_ts`) + hot-aggregate nodes for >=3 events on the same target
- **L3 mined** (additive, conf<1.0) — `mined_recurrence` edges from hound.scan / scan_cross_product_helpers / seed.scan_fusions

Edge taxonomy: `owns_kb` · `invokes_skill` · `invokes_agent` · `exposes_tool` · `exposes_flag` · `guarded_by` · `referenced_by_event` · `mirrors` · `mined_recurrence` · `semantic_neighbor` (planned).

**Use the graph when the question is structural:**
- "Which agent owns this KB doc" → `graph.neighbors node="kb_pattern:…" edge="owns_kb"` (reverse direction)
- "What does this MCP tool guard" → `graph.neighbors node="mcp_tool:…" edge="guarded_by"`
- "Which skill does CLAUDE.md route to for X" → `graph.path a="landscape_doc:CLAUDE.md" b="harness_skill:…"`
- "Has there been recent activity on this file" → `graph.explain node="…"` surfaces ai_events decorations
- "Show me everything in the harness layer" → `graph.query kind="harness_agent|harness_skill|harness_command"`
- "What's the platform snapshot" → `graph.report` (great first-call for fresh agents — same data as `/contextualize` skill)

The `/contextualize` slash command + the `noc-contextualize` skill (v1.1.0+) ARE built on graph queries — a fresh-agent orientation that returns the platform shape in one MCP call, instead of composing 5 scans per turn.

`KB § PATTERNS/architect/noc-graph.md` is the full architecture doc for the graph cache.

**Row caches** (no embedding, exact lookups) — call the dedicated MCPs:

```text
noctus.dev.keeper_pattern  # query the keeper catalog
noctus.dev.agent_context   # fetch a specialist's full owns_kb-built bundle
noctus.dev.auto_improvement # surface recent drift events on a target
```

## Cost model (why this matters)

A `noctus.dev.kb_search` hits the local SQLite + one embed-of-query OpenAI call: **~50-150ms, ~$0.00002/query**. A `grep` is fast but returns lexical matches only — synonym misses, no semantic clustering. A `Read` of an unfamiliar file pulls 100s of tokens into the context budget for content you may not need.

Order of operations (in this exact priority):

1. **Search a cache** — pay ~100ms, get the top-k most semantically relevant chunks
2. **`grep` for the exact term** if the search hit names something you need to confirm verbatim
3. **`Read` with narrow line ranges** at the addresses the search/grep surfaced
4. **`Read` whole file** — only if (1) - (3) confirm you need the surrounding context

Skipping step 1 means you've paid the platform's embedding cost without consuming the benefit AND you've eaten extra context budget.

## Anti-patterns (the don'ts)

- ❌ `grep -r "SomeIdea" KNOWLEDGE-BASE/` — use `kb_search query="SomeIdea"` first; semantic match wins.
- ❌ Reading a whole pattern doc to answer "is there a pattern for X" — `kb_search` returns the answer with score in 100ms.
- ❌ Reading `.claude/agents/<name>.md` whole-file when you need the agent's owned-KB summary — `agent_context` gives you the cached bundle.
- ❌ `find . -name "*.py" | xargs grep` for an idea — `code_search` returns AST-chunked symbols semantically ranked.
- ❌ Re-asking the user something they've already explained — `memory_search query="<topic>"` first.
- ❌ Composing 5 separate KB-doc reads to orient yourself in a fresh session — `noctus.graph.report` + `/contextualize` give you the platform shape in one call.

## When `grep` / `Read` ARE right

- **Exact-token confirmation** after a semantic hit ("the cache said this function exists here — is it really at line 247?").
- **Lossless string match** when synonyms aren't a concern (file paths, error strings, specific identifiers you already know).
- **Narrow re-reads** of chunks the search surfaced.
- **Whole-file edits** — once you've found WHAT to edit via search, you Read + Edit the file like normal.

The principle is **search to discover, grep/read to verify**.

## How this composes with the rest of the methodology

- **`KB § PATTERNS/common/cache-portable-architecture.md`** — the underlying storage (Tier-1 worktree-shared SQLite + Tier-2 prod pgvector mirror). Implementation detail; the agent-facing rule is the one in THIS doc.
- **`KB § PATTERNS/common/cache-auto-freshness.md`** — the refresh contract that guarantees cache hits are CURRENT.
- **`KB § PATTERNS/common/cache-locking-discipline.md`** — WAL mode that makes concurrent search-from-many-sessions safe.
- **`KB § PATTERNS/architect/noc-graph.md`** — the graph cache + `/contextualize` reach for orientation.
- **`KB § PATTERNS/common/kb-vector-search.md`** — the vector-search-as-additive principle (markdown stays canonical; vectors are enrichment).
- **`KB § PATTERNS/common/agent-context-architecture.md`** — why `.claude/agents/<name>.md` is L1-index + cache holds the depth.

## History

- 2026-05-28 — codified after the two-tier cache architecture shipped (`a99c7410`). The user surfaced the gap: "the caches exist, future agents should USE them to help their work, not just refresh them." This doc converts the cache layer from a passive storage system into an active agent-facing tool.

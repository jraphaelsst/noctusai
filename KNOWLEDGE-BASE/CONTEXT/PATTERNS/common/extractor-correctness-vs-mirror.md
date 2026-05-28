# Extractor-correctness vs. mirror-freshness — the residual cache-layer gap

**What it is.** A named distinction between **structural mirror correctness** (the keeper-mirror contract: cache `source_sha` matches the live aggregate) and **extractor logic correctness** (the cache contents actually represent the source faithfully). Born 2026-05-28 alongside the 7→8-way sync promotion, when codifying `.claude/cache/` as a first-class methodology surface surfaced the question: "what does an in-sync cache GUARANTEE?"

## The two layers

| Layer | What it guarantees | Failure mode | Enforced by |
|---|---|---|---|
| **Structural mirror** (8-way surface #8) | `cached.source_sha == live.aggregate_sha` — the cache was rebuilt against the current input set | Stale cache returns OLD answers from a previous tree state | `check_<name>_cache_freshness` keepers + 4 git hooks (`pre-commit` + `post-merge` + `post-checkout` + `pre-push`) running `refresh_all_caches(only_stale=True)` |
| **Extractor correctness** (residual gap) | The extractor's logic actually produces the RIGHT nodes/edges/embeddings from the input | Fresh cache returns NEW-but-WRONG answers — a buggy mapper silently mis-represents the source | Per-extractor pytest suite (e.g. `mcp/noctusai/tests/test_graph_*.py`, `mcp/noctusai/tests/test_kb_embeddings.py`) — NOT a keeper |

A cache can be **structurally fresh AND semantically wrong** — the mirror contract doesn't catch this. The 8-way sync closes the structural gap; this doc names the residual logic gap and points at the right test surface.

## Why this distinction matters

The `cache-as-agent-tool` rule promotes caches to the live agent read path. An agent calling `noctus.graph.neighbors()` trusts the result the same way a developer trusts `git log` — assumed-correct, not verified-per-call. Two failure modes:

1. **Stale cache** → agent reads ANSWER-FROM-LAST-WEEK. Mitigation: structural mirror. Detectable by hash compare. SOLVED.
2. **Buggy extractor** → agent reads ANSWER-FROM-AN-EXTRACTOR-THAT-DOESN'T-UNDERSTAND-THE-SOURCE. Mitigation: extractor unit tests. UNDETECTABLE by hash compare (the hashes match, the content is just wrong).

Conflating these is a category error. A green `check_all_cache_freshness` is necessary-not-sufficient for cache trust. The test suite for the extractor is the second leg.

## What the extractor-correctness layer looks like in practice

Each cache has an extractor module (some pure Python, some seed-lib-backed). Each needs its own test surface:

| Cache | Extractor | Test surface |
|---|---|---|
| `keeper-patterns.sqlite` | `compliance.py` AST parse | `test_compliance.py` + the keeper baseline file |
| `agent-context.sqlite` | `agent_context.py` bundling | `test_agent_context.py` |
| `auto-improvement.sqlite` | `auto_improvement.py` ndjson parse | `test_compliance_codification_batch.py` |
| `kb-embeddings.sqlite` | `kb_embeddings.py` chunking + OpenAI embed | `test_kb_embeddings.py` |
| `code-embeddings.sqlite` | `code_embeddings.py` AST chunking | `test_code_embeddings.py` |
| `corpus-embeddings.sqlite` | `corpus_embeddings.py` heterogeneous source enumerate | `test_corpus_embeddings.py` |
| `memory-embeddings.sqlite` | `memory_embeddings.py` MEMORY.md + memory dir parse | `test_memory_embeddings.py` (TODO if missing) |
| `noc-graph.sqlite` | `noc_graph_cache.py` + the `graph_build` extractors | `test_graph_*.py` family (build, edges, queries) |

When you add a new cache, you ship BOTH legs: (a) a `check_<name>_cache_freshness` keeper wired into `check_all_cache_freshness` (8-way structural), and (b) a per-extractor test file (residual logic).

## Composes with

- [`eight-way-sync`](eight-way-sync.md) — the structural-mirror leg this doc complements. The 8-way carries the freshness contract; this doc carries the named gap above it.
- [`cache-as-agent-tool`](cache-as-agent-tool.md) — the rule that elevates caches to the read path AND raises the stakes for both legs.
- [`cache-auto-freshness`](cache-auto-freshness.md) — the 4-hook contract that automates the structural leg.
- [`keeper-pattern-cache`](keeper-pattern-cache.md) — the mirror contract template every keeper-mirror cache inherits.

## Anti-patterns

- **DON'T** conclude "cache is correct" from a green freshness keeper alone. Structural mirror ⇒ "cache reflects current source"; it does NOT ⇒ "cache reflects source correctly".
- **DON'T** skip the per-extractor test suite when adding a new cache. The 8-way promotion gave us the structural leg as a one-line addition; the logic leg is the test file you write the same commit.
- **DON'T** silently fix an extractor bug without updating the test that should have caught it. Every extractor-correctness firing IS a test-surface gap — add the regression case.
- **DON'T** promote `.claude/cache/<new>.sqlite` to first-class surface #N without a test surface for its extractor.

## History

- 2026-05-28: codified alongside the 7→8-way sync promotion. The promotion forced the question: "if `.claude/cache/` is now a methodology surface, what does that surface GUARANTEE?" The answer separated structural-mirror (the new surface guarantees this) from extractor-correctness (a separate test-surface concern). Named so future cache additions ship both legs by default.

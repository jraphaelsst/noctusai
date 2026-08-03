# Cache platform — family index (§1 consolidation)

> **Family-line pattern:** CLAUDE.md §1 carries ONE line for this family; the member rules live here **verbatim**. This is a lossless MOVE, not a summary — the bytes below are the bytes that were in §1. Each member keeps its own depth doc; this index is the router hop between the §1 family line and those docs. Consolidated 2026-08-03 (harness-audit re-author; §1 had reached 79 always-on rules). → `KB § PATTERNS/common/methodology-gc.md`

Two cache rules stay standalone in §1 because they are per-turn behavioral defaults, not platform mechanics: **cache-first search** (`cache-as-agent-tool.md`) and **keeper-check before doc'ing** (`keeper-pattern-cache.md`).

## Members (verbatim from §1)

- **KB vector search — markdown canonical, vector DB is enrichment.** 4th keeper-mirror cache (`.claude/cache/kb-embeddings.sqlite`, sqlite-vec + OpenAI embed via seed lib); ADDITIVE semantic-search + `kb_neighbors`/`kb_similar`/`kb_validate_owns_kb`/generic `vector_*` primitives. Markdown stays canonical. Keeper `check_kb_vector_canonical` advisory-only. → `KB § PATTERNS/common/kb-vector-search.md`
- **noc-graph — structured graph of the platform.** 8th keeper-mirror (`.claude/cache/noc-graph.sqlite`); materializes code+KB+memory+harness+landscape+cli+history as queryable nodes/edges; fresh agents reach `/contextualize` + `noctus.graph.*` instead of composing 5 scans; keeper `check_noc_graph_cache_freshness` advisory-only. → `KB § PATTERNS/architect/noc-graph.md` · skill `noc-contextualize`
- **Cache-locking discipline — WAL + busy_timeout on every keeper-mirror SQLite cache.** WAL = readers never block the writer; busy_timeout = a contending writer waits instead of erroring `database is locked` (WAL doesn't serialize writer-vs-writer). Single helper `cache_backend.apply_locking_pragmas`. → `KB § PATTERNS/common/cache-locking-discipline.md`
- **Cache auto-freshness — two-tier + heal-on-contact.** Structural caches refresh pre-commit AND self-heal on check (`settle_structural_caches`, zero-OpenAI); embedding caches warn-only. → `KB § PATTERNS/common/cache-auto-freshness.md`
- **Cache-portable architecture — TWO-TIER persistent + machine-portable.** Tier-1 local (shared by all worktrees of this repo); Tier-2 prod pgvector mirror; auto-pull-on-empty for fresh-clone bootstrap. → `KB § PATTERNS/common/cache-portable-architecture.md`
- **Vectorize → embed → cache (the unified pipeline).** Any vectorize/embed/cache slice follows the SAME 3-leg pipeline: (1) caching-architecture decision (extend before spawn), (2) embed via `noctusai_lib.integrations.llm` (cost-log), (3) cache with source-sha invariant + 3-leg mirror contract. → `KB § PATTERNS/common/vectorize-embed-cache-framework.md`

## Why a family line

These 6 rules shared one framework, and a session that needs one of them typically needs the rest — so a single router hop costs a lookup and returns 5 always-on lines of budget. The forcing function is the router keeper's rule-COUNT ceiling; the procedure is `/gc` step 5. → `KB § PATTERNS/common/claude-md-router-discipline.md`


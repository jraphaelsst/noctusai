# Proposal: cache_deploy_mirror schema-drift surface

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** surface
**Origin:** project:cache-pg-vps-bringup:phase-2-mirror
**Generated:** 2026-05-26 18:31
**Severity:** high
**Effort:** medium
**Affected products:** none (methodology + tooling — `mcp/noctusai/tools/noctus/dev/cache_deploy_mirror.py`)
**Status:** pending  <!-- BLOCKING: awaits tech-lead accept/reject/adapt -->

---

## 1. Context

Phase 2 mirror execution surfaced a substantial drift between the schemas `cache_deploy_mirror._TABLE_MAP` ASSUMES and the schemas the local SQLite caches actually carry. The tool was written + tested without ever validating against the real local SQLite shape; only `keeper-patterns` happens to align with the assumed shape.

**Partial mirror succeeded**: `keeper-patterns` → 132 rows live in prod `noctus_cache.cache_keeper_patterns`.

**4 of 5 caches BLOCKED** on schema mismatches.

The compose change (host-loopback `127.0.0.1:5432:5432`) IS in place + verified working. SSH tunnel from local → cache-pg → psycopg2 connect succeeds end-to-end. The blocker is purely the tool's column mapping, not the connectivity path.

Per the dispatch-with-PROJECT-and-notes protocol §1c, this is an alt-route mid-flight → STOP + surface + BLOCK on tech-lead decision.

---

## 2. Situation (the 4 schema mismatches)

### 2.1 agent_context (architectural mismatch — disaggregated vs aggregated)

Local sqlite:
```
agent_context(agent_name, section_kind, section_path, section_value, source_sha, cached_at)
```
The local form is **disaggregated** — one row per agent×section. ~100 rows for 9 agents.

`cache_deploy_mirror` expects:
```
agent_context(agent_name, bundle_json, source_sha, cached_at)
```
The mirror expects **aggregated** — one row per agent with a JSON bundle.

**Mismatch class:** architectural. Mirror would need to re-aggregate sections into JSON on the fly.

### 2.2 auto_improvement (column rename + missing column)

Local sqlite:
```
auto_improvement(rowid_alias, ts, agent, scope, kind, target, description, status, source_ref, cached_at)
```

Mirror expects:
```
auto_improvement(ts, agent, scope, kind, target, description, status, source_ref, source_sha)
```

Local has `cached_at`, mirror expects `source_sha`. They are NOT the same thing — `source_sha` is the ledger file's sha (immutable per-build); `cached_at` is when this row was written to cache.

**Mismatch class:** minor — either add `source_sha` to local (sourced from ndjson's sha) OR drop `source_sha` from prod schema (already accepted that mirror updates `cached_at`).

### 2.3 kb_chunks (vector lives in a sibling table)

Local sqlite:
```
kb_chunks(rowid_alias, path, chunk_idx, chunk_text, source_sha, cached_at)
kb_embeddings_json(...)   ← separate table; the actual vector data lives here
```

Mirror expects (per init DDL):
```
cache_kb_embeddings(id, path, chunk_idx, chunk_text, embedding vector(1536), source_sha, cached_at)
```

The local design splits chunks (text) from embeddings (binary). The mirror wants one wide row with both.

**Mismatch class:** moderate — mirror needs to JOIN the two local tables to produce the prod row.

### 2.4 code_chunks (column rename + extra column + vector split)

Local sqlite:
```
code_chunks(rowid_alias, path, chunk_idx, symbol_name, kind, chunk_text, source_sha, cached_at)
code_embeddings_json(...)  ← vector data
```

Mirror expects:
```
cache_code_embeddings(id, path, symbol, chunk_idx, chunk_text, embedding vector(1536), source_sha, cached_at)
```

Differences: `symbol_name` → `symbol` (rename) · `kind` column not in prod schema · vector lives in a separate local table.

**Mismatch class:** moderate — same JOIN-pattern as kb_chunks + a column rename + a column drop.

---

## 3. Proposed Solution

### 3.1 Linkage

The tool was authored against an ASSUMED schema — never validated end-to-end before today. First real mirror execution surfaced the gap. Fixing the tool to match the actual schemas is the structural path; adapting prod schema to match local is the alternative path; deferring is the third path.

### 3.2 Application instructions (the 3 routes for your accept/reject/adapt)

**Route X: Fix `cache_deploy_mirror` to match the real schemas (recommended)**
- Open a new project `cache-deploy-mirror-schema-alignment`.
- Update `_TABLE_MAP` + per-cache mirror functions to handle the actual local schemas (disaggregation, JOINs, column renames).
- Drop `source_sha` column from `noctus_cache.cache_auto_improvement` prod table (or compute it from cached_at).
- Drop `embedding` column from `cache_kb_embeddings` + `cache_code_embeddings` prod tables (vectors live separately) — OR change mirror to JOIN local `*_chunks` + `*_embeddings_json` and populate the unified prod row.
- Add `kind` column to `cache_code_embeddings` prod table to match local.
- Update tests to validate against real-shape fixtures.
- Re-run mirror end-to-end.

**Route Y: Adapt local SQLite schemas to match prod (NOT recommended)**
- Refactor the 4 cache modules (`agent_context.py` / `auto_improvement.py` / `kb_embeddings.py` / `code_embeddings.py`) to use the assumed schemas (bundle_json + embedding column + symbol rename + source_sha addition).
- Requires migrating existing local data + retesting every consumer.
- Risk: high — these are the 5 keeper-mirror caches in active use; schema migration is the canonical risky operation.

**Route Z: Defer the mirror, accept keeper-patterns-only for now**
- Phase 2 closes with 132/4726 rows mirrored. The cache is functional (lazy warm via consumers).
- Phase 3 (GH Actions) proceeds with the compose change + tunnel still in place; CI uses an empty-but-schema-ready cache that warms on first miss.
- Open the schema-alignment work as a roadmap item (`cache-deploy-mirror-schema-alignment`).

### 3.3 Seed APIs / shared lib involved

- `cache_deploy_mirror.py` — the tool to fix in Route X
- `cache_backend_postgres.py` — pgvector type registration (separate issue — see §3.4)
- `agent_context.py` · `auto_improvement.py` · `kb_embeddings.py` · `code_embeddings.py` — local cache modules; Route Y would refactor these

### 3.4 Sibling issue surfaced

`pgvector Python package not installed; vector type registration skipped for cache 'kb-embeddings'` — but `pgvector==0.4.2` IS installed in venv (verified earlier this session). This is the `cache_backend_postgres` module's import of pgvector failing silently inside the worktree's runtime, despite the package being available in the primary venv. Worktree env divergence (`feedback_self_branch_invisible_to_running_env.md` pattern). Likely fix: import-side hardening. Not blocking Route X but related.

### 3.5 Alternatives considered (within Route X)

- Mirror only what works (Route Z) — accepted as fallback in §3.2.
- Build a separate `cache_deploy_mirror_v2` and deprecate the old — adds churn; better to fix in place.

---

## 4. Effects (if Route X accepted)

- **Behavior:** mirror runs end-to-end. 4726+ rows transferred per session.
- **Risk profile:** safer — schemas aligned, no more silent assumption breakage.
- **Ergonomics:** subsequent Phase 3 CI gates can rely on a populated prod cache (faster CI; no per-runner re-embed).
- **Coverage:** tests grow to validate against real-shape fixtures (the missing validation that let this drift through originally).

---

## 5. Acceptance Criteria (when you decide)

- [ ] Route picked (X / Y / Z / Other)
- [ ] If X: project `cache-deploy-mirror-schema-alignment` opened with §4a Dispatch routing
- [ ] If Y: project `cache-schema-refactor` opened (high-risk migration plan)
- [ ] If Z: this slice closes with the keeper-patterns mirror as Phase 2 deliverable; schema alignment goes to roadmap

---

## 6. Related files

- `mcp/noctusai/tools/noctus/dev/cache_deploy_mirror.py` (the tool to fix in Route X)
- `mcp/noctusai/tools/noctus/dev/agent_context.py` (local schema source of truth)
- `mcp/noctusai/tools/noctus/dev/auto_improvement.py:_SCHEMA` (local schema source of truth)
- `mcp/noctusai/tools/noctus/dev/kb_embeddings.py` (local schema source of truth)
- `mcp/noctusai/tools/noctus/dev/code_embeddings.py` (local schema source of truth)

---

**Tech-lead action needed:** pick a route (X recommended) + decide whether to land the partial mirror (132 keeper-patterns rows) as Phase 2 deliverable, or wait until full mirror works.

# Code embeddings — fifth keeper-mirror cache (cross-product recurrence radar)

**What it is.** A semantic-search layer over the **code corpus** (Python + TypeScript), built on the same vector platform as `kb-embeddings`. Fifth keeper-mirror cache (after keeper-pattern + agent-context + auto-improvement + kb-embeddings). The vector DB at `.claude/cache/code-embeddings.sqlite` is an **enrichment index** — never a content store. Born 2026-05-26 (W2-E3' of the automation-orchestration-2026-05 roadmap).

**Sister pattern.** Mirrors `KB § CONTEXT/PATTERNS/common/kb-vector-search.md` exactly: same 3-leg mirror contract, same two-layer stack (OpenAI text-embedding-3-small via seed lib + sqlite-vec storage), same warning-severity discipline. **Markdown stays canonical for docs; code-on-disk stays canonical for code** — vectors are search indices, not storage.

## Why this exists

Cross-product duplication discovery is structurally weak with grep (different identifiers, similar shape) and structurally weak with the Python-only AST scanners (no TS surface, no embedding-friendly index). The `kb-embeddings` cache (4th) covers documentation; THIS one covers code. Together they form the two-half semantic layer over the repo:

| Cache | Corpus | Use case |
|---|---|---|
| `kb-embeddings.sqlite` | `KNOWLEDGE-BASE/**/*.md` | Fuzzy-intent KB discovery |
| `code-embeddings.sqlite` | `mcp/`, `noctusai_lib/`, `products/seed/` `.py/.ts/.tsx` | Cross-product recurrence radar |

## What's shipped

| MCP tool | Purpose |
|---|---|
| `noctus.dev.code_search(query, top_k, kind?)` | Semantic search over code — fuzzy-intent queries → ranked symbols |
| `noctus.dev.code_neighbors(path, symbol_name?, top_k)` | Find code symbols semantically nearest to a given anchor — cross-product recurrence radar |
| `noctus.dev.code_similar_to_text(text, top_k, kind?)` | Pre-authoring radar — find existing symbols before writing a new helper |
| `noctus.dev.code_embeddings_refresh(force?, paths?)` | Re-populate the cache; per-file source_sha guard |
| `noctus.dev.code_embeddings_list()` | Distinct files in the cache (verify coverage) |

CLI: `--refresh-code-embeddings [--force]` · `--code-search <query> [--top-k N]` · `--check-code-embeddings-cache-freshness`.

## 3-leg mirror contract

Same shape as the four sibling caches:

| Leg | Mechanism |
|---|---|
| Eager pre-commit refresh | `scripts/hooks/pre-commit` step 9c — when staged paths match `(mcp|noctusai_lib|products/seed)/.+\.(py|ts|tsx)$`, `cli.py --refresh-code-embeddings` runs (non-blocking on provider failure). |
| Lazy query-time refresh | Per-file source_sha guard in `refresh()`; mismatched → rebuilds before answering. |
| Loud freshness gate | `check_code_embeddings_cache_freshness` (severity `warning`) — fails as warning at `validate` when stale or orphan rows present. |

**Why warning, not high.** Code search is **advisory** — a stale cache returns slightly outdated rankings; everything else still works. The agent can always fall back to grep / `scan_recurrence` / `scan_block_patterns`. Don't block commits over a degraded discovery layer.

## Chunking strategy

| File type | Chunking | Rationale |
|---|---|---|
| `*.py` | Module-level `FunctionDef` / `AsyncFunctionDef` / `ClassDef` via stdlib `ast` | Fine-grained units that match how code is referenced. Methods on a class are reachable via the class chunk; going finer explodes chunk count without improving discovery. |
| `*.py` (unparseable) | Whole-file fallback | Better a coarse signal than no signal. |
| `*.py` (no top-level defs) | Whole-file | E.g. `__init__.py` that only registers things. |
| `*.ts`, `*.tsx` | One chunk per file | TS AST in Python = heavier dep than this surface warrants. Pragmatic baseline; future slice can refine via tree-sitter-typescript if quality demands. |

**Per-chunk metadata** (richer than KB chunks):
- `symbol_name` (the def/class name, or `""` for file-level)
- `kind` ∈ `{function, async_function, class, file}` — supports filtered queries (e.g. "only classes")

## Schema

```sql
-- Always present (chunk metadata, both engines).
CREATE TABLE code_chunks (
  rowid_alias   INTEGER PRIMARY KEY AUTOINCREMENT,
  path          TEXT NOT NULL,          -- repo-rel, e.g. 'mcp/noctusai/tools/.../foo.py'
  chunk_idx     INTEGER NOT NULL,
  symbol_name   TEXT NOT NULL,          -- '' for file-level
  kind          TEXT NOT NULL,          -- 'function' | 'async_function' | 'class' | 'file'
  chunk_text    TEXT NOT NULL,          -- the literal chunk (LLM reads THIS)
  source_sha    TEXT NOT NULL,
  cached_at     TEXT NOT NULL
);

-- Fast path: sqlite-vec virtual table (rowid joined to code_chunks).
CREATE VIRTUAL TABLE code_vec USING vec0(embedding float[1536]);

-- Fallback path: JSON column (when sqlite-vec absent).
CREATE TABLE code_embeddings_json (
  chunk_rowid  INTEGER PRIMARY KEY,
  embedding    TEXT NOT NULL  -- JSON-serialized list[float]
);
```

## Tracked source roots

Configured in `_CODE_ROOTS = ("mcp", "noctusai_lib", "products/seed")`. Skip list (`_SKIP_PARTS`):

`__pycache__` · `node_modules` · `venv` · `.venv` · `.git` · `dist` · `build` · `.pytest_cache` · `.mypy_cache` · dotfiles.

To add a new root: edit `_CODE_ROOTS` in `code_embeddings.py` AND extend the pre-commit hook's `STAGED_CODE` regex.

## Use cases (the value layer)

### 1. Cross-product recurrence radar

```python
from tools.noctus.dev import code_embeddings as ce
# I'm reviewing products/erp/services/digest_window.py — what else looks like it?
neighbors = ce.code_neighbors("products/erp/services/digest_window.py", "compute_window", top_k=5)
# → ranked list of similar functions across all products. Score >0.7 = strong recurrence signal.
```

Combats the **DRY recurrence rule** (`N=3+ MUST formalize`) at **discovery time**, not at refactor time.

### 2. Pre-authoring radar (combat duplication at write time)

```python
# I want to write a helper that "validates a Brazilian CPF number". Does one exist?
hits = ce.code_similar_to_text("validate a Brazilian CPF number", top_k=5)
# If a hit scores >0.7, reuse / extend instead of writing fresh.
```

### 3. Fuzzy code navigation when names are unknown

```python
# "Where's the thing that splits a WhatsApp message into multiple bubbles?"
hits = ce.search("split a long whatsapp reply into multiple message bubbles")
# Returns the actual symbol regardless of its name (which I forgot).
```

## Cost discipline

Same as kb-embeddings: every `refresh()` that writes rows logs to `project-history/vector-costs.ndjson` via `vector_costs.log_refresh_batch()` (namespace `code-embeddings`). Estimated tokens = `total_rows × (MAX_CHUNK_CHARS // 4)`; replace with provider's actual `usage.total_tokens` if the seed lib starts surfacing it.

The first full refresh of noc's code corpus is the biggest single embed batch we run; subsequent refreshes are per-file source_sha gated → essentially free until code changes.

## Composes with

- `KB § CONTEXT/PATTERNS/common/kb-vector-search.md` — sister cache (docs corpus).
- `KB § CONTEXT/PATTERNS/common/keeper-pattern-cache.md` — first cache; same 3-leg mirror contract template.
- `KB § CONTEXT/PATTERNS/architect/project-execution.md § Recurrence rule` — the rule this cache discovers signals for.
- `KB § CONTEXT/PATTERNS/common/vector-calibration.md` — reasoning-driven threshold tuning if score distributions look off.

## Anti-patterns (do NOT do)

- **DON'T treat the vector DB as authoritative content.** It indexes back to the source-on-disk; if the cache disagrees with the file, the file wins. Refresh the cache.
- **DON'T add a new code root without updating both** `_CODE_ROOTS` AND the pre-commit hook's `STAGED_CODE` regex. The auto-refresh leg will silently skip files outside the regex.
- **DON'T use `code_search` for exact-identifier lookups.** That's grep's job. Use it for fuzzy-intent ("find helpers that do X").
- **DON'T promote to severity `high`.** Vector search is advisory; blocking commits over discovery degradation breaks the no-silent-errors principle by introducing a false-positive blocker.

## Deferred next-slices (named triggers in this doc so future-us doesn't lose the thread)

| Future tool | Status | What it does |
|---|---|---|
| `code_cluster` | deferred | k-means topic clusters over the code corpus — surfaces "natural groupings" the seed should be aware of. |
| `code_recurrence_promote` | ✅ **shipped 2026-05-26** | Closes the cross-product recurrence loop: `scan(threshold, top_k_per_file, limit)` walks every anchor in the cache → dedupes pairs → groups by score-band (strong ≥0.9 / medium ≥0.8 / weak ≥0.7); `promote(matches)` writes each as an `s1-emergent` `improvement` entry to `auto-improvement.ndjson` with `target = "code-recurrence:<p1>::<s1> ≈ <p2>::<s2>"` (canonical order; idempotency key). `codification_radar` then surfaces s2/s3 candidates on its next cluster pass. KB § CONTEXT/PATTERNS/common/code-embeddings.md § Use case 1 wires here. |
| TS AST chunking | deferred | When file-level recall drops, add tree-sitter-typescript for finer TS chunks. |

### Pipeline now closed

```
code_embeddings (W2-E3')
        ↓ scan() — walks anchors corpus-wide
code_recurrence_promote (THIS slice, 2026-05-26)
        ↓ promote() — writes s1-emergent to auto-improvement.ndjson
codification_radar (W2-E4')
        ↓ cluster() — surfaces s2/s3 candidates when N≥3 cluster
architect — absorbs to seed (DRY recurrence rule)
```

The full DRY recurrence-discovery → codification loop is now AUTOMATIC end-to-end.

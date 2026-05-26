# Cache-locking discipline — WAL mode on every keeper-mirror SQLite cache

**What it is.** The contract: every SQLite-backed keeper-mirror cache opens with `PRAGMA journal_mode=WAL` so readers don't block writers and a hung writer doesn't lock-storm the whole platform. Born 2026-05-26 (post-verify-pass codification) after a hung kb-embeddings refresh held the rollback-journal lock for ~30 min and blocked every other reader trying to touch the cache.

## The lesson

The 5 keeper-mirror caches (`keeper-patterns`, `agent-context`, `auto-improvement`, `kb-embeddings`, `code-embeddings`) were all opened with default sqlite3 settings — **rollback-journal mode**. In rollback mode, a writer holds an exclusive lock for the duration of its transaction. If the writer hangs (network call to OpenAI taking minutes; OS swap; process freeze), every reader gets `OperationalError: database is locked` until the writer dies OR completes.

This bit during the 2026-05-26 verify pass: the original kb-embeddings refresh hit an OpenAI rate-limit and stalled for 30+ min, blocking every parallel reader. The fix wasn't to kill the writer faster (it eventually progressed) — the fix was to **change the locking model** so reads don't fight writes.

## The fix

```python
def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # fallback to default journal if WAL unavailable
    return conn
```

Applied uniformly to every keeper-mirror cache's `_connect()`. Idempotent (no-op if already WAL). Falls through silently if WAL isn't available (graceful degrade — never crash on the lock-mode setting).

## Why WAL works

In **WAL (Write-Ahead Logging) mode**:
- **Readers never block writers** — they read the snapshot from the main DB file; the writer appends to the WAL file.
- **Writers never block readers** — writes go to the WAL file independently of read positions.
- The cost: an extra file (`*-wal` + `*-shm`) alongside the main DB; periodic checkpointing folds WAL into the main file.

Acceptable trade-off for our 5 caches:
- They're gitignored already.
- They're small (≤100MB even at peak code-embeddings size).
- They're read-heavy + occasional write-burst (refresh runs) — exactly WAL's strength.

## Surfaces this protects

Every cache `_connect()` writes go through the same pattern:
- `mcp/noctusai/tools/noctus/dev/kb_embeddings.py`
- `mcp/noctusai/tools/noctus/dev/code_embeddings.py`
- `mcp/noctusai/tools/noctus/dev/auto_improvement.py`
- `mcp/noctusai/tools/noctus/dev/agent_context_cache.py`
- `mcp/noctusai/tools/noctus/dev/keeper_pattern_cache.py`

When adding a NEW SQLite-backed cache, the WAL pragma is now part of the **base contract** — not an optimization to remember.

## Anti-patterns

- **DON'T** silently fall back to rollback mode without a try-except + comment. The graceful-degrade keeps the cache functional on systems where WAL doesn't work; the comment ensures future maintainers don't think it was an oversight.
- **DON'T** force WAL with `journal_mode=WAL` as a non-pragma write — must be `PRAGMA`.
- **DON'T** assume WAL means "no locking ever." Writes still serialize. Two concurrent writers will still queue. WAL only removes reader↔writer contention.

## Composes with

- [`keeper-pattern-cache`](keeper-pattern-cache.md) — first keeper-mirror cache; sets the 3-leg contract that all 5 now inherit.
- [`agent-context-architecture`](agent-context-architecture.md) — second cache; same contract.
- [`scoped-auto-improvement`](scoped-auto-improvement.md) — third cache.
- [`kb-vector-search`](kb-vector-search.md) — fourth cache.
- [`code-embeddings`](code-embeddings.md) — fifth cache.
- [`dont-block-on-background`](dont-block-on-background.md) — the broader pattern this evolved from (don't idle-poll a hung writer; the lock-storm is what made the polling worse).

## History

2026-05-26 verify-pass surfaced the lock-storm: `database is locked` from a hung writer blocked 3 parallel readers. Fix-on-contact: WAL mode on all 5 caches in one commit (`9b21c090`). Now standard for any new cache.

# Cache-locking discipline — WAL + busy_timeout on every keeper-mirror SQLite cache

**What it is.** The contract: every SQLite-backed keeper-mirror cache opens via the single helper `cache_backend.apply_locking_pragmas(conn)`, which sets **two** pragmas together — `journal_mode=WAL` (readers never block the single writer) **and** `busy_timeout` (a *contending writer* waits-and-retries instead of immediately raising `database is locked`). Born 2026-05-26 (WAL leg, after a hung kb-embeddings refresh held the rollback-journal lock for ~30 min and blocked every reader) and completed 2026-05-30 (busy_timeout leg, after a pre-push refresh fan-out collided with a live MCP reader on the Tier-1-shared `kb-embeddings.sqlite` — WAL alone does NOT serialize writer-vs-writer).

## The lesson

The 5 keeper-mirror caches (`keeper-patterns`, `agent-context`, `auto-improvement`, `kb-embeddings`, `code-embeddings`) were all opened with default sqlite3 settings — **rollback-journal mode**. In rollback mode, a writer holds an exclusive lock for the duration of its transaction. If the writer hangs (network call to OpenAI taking minutes; OS swap; process freeze), every reader gets `OperationalError: database is locked` until the writer dies OR completes.

This bit during the 2026-05-26 verify pass: the original kb-embeddings refresh hit an OpenAI rate-limit and stalled for 30+ min, blocking every parallel reader. The fix wasn't to kill the writer faster (it eventually progressed) — the fix was to **change the locking model** so reads don't fight writes.

## The fix

One helper is the **single source of truth** — `cache_backend.apply_locking_pragmas`. Every cache `_connect()` calls it instead of inlining the pragmas (this also retired the prior N=9 duplication of the raw WAL line):

```python
# cache_backend.py — the single source of truth
CACHE_BUSY_TIMEOUT_MS = 5000

def apply_locking_pragmas(conn, *, timeout_ms=CACHE_BUSY_TIMEOUT_MS):
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # tmpfs / readonly fallback — non-fatal
    conn.execute(f"PRAGMA busy_timeout={int(timeout_ms)}")

# every cache _connect()
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    apply_locking_pragmas(conn)
    return conn
```

Idempotent. The WAL leg falls through silently if WAL is unavailable (graceful degrade); `busy_timeout` always applies. **Why both legs are needed:** WAL removes reader↔writer contention but a *second writer* still gets `SQLITE_BUSY` immediately — `busy_timeout` makes it wait up to `timeout_ms` for the lock instead of erroring.

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

Every cache connection routes through `cache_backend.apply_locking_pragmas` — 9 call sites:
- `cache_backend.py` (`SqliteCacheBackend.connect`) — the backend abstraction.
- `_embedding_corpus.py` (`connect_cache`) — the shared embedding-cache opener (kb / code / corpus / memory embeddings).
- `auto_improvement.py` · `agent_context_cache.py` · `keeper_pattern_cache.py` · `noc_graph_cache.py` — structural caches.
- `cache_deploy_mirror.py` — the Tier-2 deploy mirror's local connection.
- `graph/build.py` (×2) — read-side connections to the embedding + keeper caches.

When adding a NEW SQLite-backed cache, call `apply_locking_pragmas(conn)` — the WAL + busy_timeout pair is the **base contract**, not an optimization to remember.

## Anti-patterns

- **DON'T** silently fall back to rollback mode without a try-except + comment. The graceful-degrade keeps the cache functional on systems where WAL doesn't work; the comment ensures future maintainers don't think it was an oversight.
- **DON'T** force WAL with `journal_mode=WAL` as a non-pragma write — must be `PRAGMA`.
- **DON'T** assume WAL means "no locking ever." Writes still serialize — WAL only removes reader↔writer contention. Two concurrent writers DO contend; `busy_timeout` is what makes the loser *wait* instead of erroring `database is locked` (this is the 2026-05-30 leg — WAL without busy_timeout was the latent bug).
- **DON'T** inline `PRAGMA journal_mode=WAL` in a new cache's `_connect()`. Call `apply_locking_pragmas(conn)` — a raw WAL line without the busy_timeout sibling is the exact regression this discipline now guards against.

## Composes with

- [`keeper-pattern-cache`](keeper-pattern-cache.md) — first keeper-mirror cache; sets the 3-leg contract that all 5 now inherit.
- [`agent-context-architecture`](agent-context-architecture.md) — second cache; same contract.
- [`scoped-auto-improvement`](scoped-auto-improvement.md) — third cache.
- [`kb-vector-search`](kb-vector-search.md) — fourth cache.
- [`code-embeddings`](code-embeddings.md) — fifth cache.
- [`dont-block-on-background`](dont-block-on-background.md) — the broader pattern this evolved from (don't idle-poll a hung writer; the lock-storm is what made the polling worse).

## History

2026-05-26 verify-pass surfaced the lock-storm: `database is locked` from a hung writer blocked 3 parallel readers. Fix-on-contact: WAL mode on all 5 caches in one commit (`9b21c090`). Now standard for any new cache.

2026-05-30 surfaced the writer-vs-writer gap WAL didn't cover: a pre-push embedding-refresh fan-out collided with a live MCP-server reader on the Tier-1-shared `kb-embeddings.sqlite` → `kb-embed: sqlite3.OperationalError: database is locked` (the refresh leg failed; the push itself succeeded, the cache self-healed on a manual retry). Fix-on-contact: extracted the single `apply_locking_pragmas` helper (WAL + busy_timeout), wired all 9 raw-WAL sites to it (retiring the N=9 duplication), + 5 regression tests. The pre-push refreshers still fan out concurrently; busy_timeout makes that safe.

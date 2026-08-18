# cache-portable-architecture — two-tier persistent cache

## The problem this solved

Before this pattern, each worktree had its own `.claude/cache/` directory (gitignored). Every
fresh worktree started with an EMPTY cache. The pre-commit cache-refresh rule (universal: every
boundary, every cache) then re-embedded the entire corpus from scratch — ~30 minutes of
OpenAI roundtrips per fresh worktree, before the first commit could land. **The SQLite layer
persisted within a worktree. The LOCATION made it ephemeral across worktrees.**

A second symptom: cloning the repo to a new computer = empty cache = ~30 min embed tax on
first commit (or operator query). The cache layer was not portable.

## The architecture

**Two tiers, both load-bearing.**

### Tier 1 — Local fast path
**Location:** `<git-common-dir>/noctusai/cache/*.sqlite`

`git rev-parse --git-common-dir` resolves to the SAME path from every worktree (the primary
tree's `.git/`, which linked worktrees stub-point back to). One physical SQLite per cache,
ALL worktrees consume it directly. No copies, no symlinks. WAL mode (already in place per
cache-locking-discipline) handles concurrent reads + serialized writes across parallel
sessions.

Survives as long as the repo's `.git/` exists. Deleted only when the user removes the repo.

### Tier 2 — Remote authoritative
**Location:** Prod pgvector at `noctus-cache-pg:5432` (already in place via the
prod-cache-container pattern).

Machine-portable: lives in the production fleet, accessible over SSH tunnel. Survives across
clones to ANY computer. The source of truth across machines.

**Sync directions** (both reuse the per-cache schema knowledge in
`cache_deploy_mirror._TABLE_MAP`):
- Local → Remote: `noctus.dev.cache_deploy_mirror` (existing — runs on every deploy)
- Remote → Local: `noctus.dev.cache_pull` (new — for fresh-clone bootstrap)

### Auto-pull on empty (default ON)

When `cache_backend.cache_path()` resolves a cache file and finds the local path missing,
it attempts a Tier-2 pull from prod (best-effort, silent failure leaves the cache empty,
the standard refresh flow then rebuilds locally). Sentinel-gated (per-process AND
on-disk) so a missing remote (no tunnel / no DSN) costs ONE resolution attempt per
process, never repeats.

Opt out via `NOCTUS_DISABLE_AUTO_CACHE_PULL=1` (CI / offline / first-machine-without-tunnel).

## Concurrent-refresh discipline (the dogpile fix)

Tier-1 means ALL worktrees share `<git-common-dir>/noctusai/cache/*.sqlite`. N parallel pre-commits → N writers serialize on the same SQLite file + N concurrent OpenAI embedding queries hit rate limits in parallel. The 2026-05-28 dogpile observed three concurrent pre-commits stalling for 31 min on shared `kb-embeddings.sqlite`.

**The guard:** `cache_backend.acquire_refresh_lock(cache_name)` — single-writer lock per cache via `fcntl.flock`. Each CLI refresh handler wraps its body:

```python
with acquire_refresh_lock("kb-embeddings") as ok:
    if not ok:
        print("kb embeddings refresh skipped — another process holds the lock.")
        sys.exit(0)
    # ... do the refresh ...
```

**Properties:**
- **Non-blocking by default** (`timeout=0`) — second writer SKIPS cleanly. Trust the in-flight refresh; next freshness boundary revisits.
- **`flock` is kernel-tracked** — a crashed refresher does NOT strand the lock; the kernel releases on process death.
- **Lock file is a sibling sentinel** (`<cache>.refresh.lock` next to the SQLite). SQLite + WAL state untouched.
- **Refresh ENTRY only** — concurrent SEARCH / READ still flows freely (WAL handles those, per cache-locking-discipline).
- **`timeout>0` available** for callers that must wait (e.g. pre-push final-gate); CI / hooks default to skip-cleanly.

Composes with `cache-locking-discipline.md` (WAL for read concurrency) — these are orthogonal locks: WAL=read safety, `acquire_refresh_lock`=write coordination.

## Flow on a new machine

```bash
git clone github.com/jraphaelsst/noctusai
cd noctusai
bash scripts/install-hooks.sh

# First cache touch (pre-commit / scan / search) detects empty local
# + reachable remote → auto-pulls from prod pgvector → populates
# <git-common-dir>/noctusai/cache/ → works at local speed thereafter.

# OR explicitly:
python mcp/noctusai/cli.py --cache-pull
```

⚠️ `--cache-pull-only=<names>` is a **modifier** for `--cache-pull`, not a
command — passing it alone parses fine and pulls nothing.

🔴 This flow was **broken from the start until 2026-08-18** — the pull wrote
an invented schema for all seven caches and would have reported `ok: true`
over an unreadable cache on exactly the fresh clone it exists to serve. Fixed
+ gated by a round-trip test; the failure and the structural fix are written
up in `KB § PATTERNS/devops/cache-deploy-mirror.md § 2026-08-18`. If you are
bootstrapping a machine, check the `warnings` key in the result: a pull can
succeed and still hand back a degraded cache.

## Legacy migration (one-time, idempotent)

`cache_backend.cache_path()` runs a one-time migration on first invocation per repo_root:
copies `<worktree>/.claude/cache/*.sqlite` (and the WAL / SHM sidecars) from ALL existing
worktrees into the new shared location, picking the newest file per cache name. Uses `copy2`
(not `move`) so OLD code on un-pulled worktrees keeps working against `.claude/cache/`. A
future cleanup commit removes the legacy dirs once everyone is on the new code.

Sentinel: `<git-common-dir>/noctusai/cache/.migrated-from-claude-cache`.

## The 11 sites consolidated

Every cache-path resolution sites was independently constructing
`REPO_ROOT / ".claude" / "cache" / "<name>.sqlite"`. They now all go through
`cache_backend.cache_path()` (SQLite files) or `cache_backend.cache_dir()`
(ndjson / sidecar files):

| Module | Resolution |
|---|---|
| `kb_embeddings.py`, `code_embeddings.py`, `memory_embeddings.py`, `corpus_embeddings.py` | `cache_path("<name>")` |
| `keeper_pattern_cache.py`, `agent_context_cache.py`, `auto_improvement.py` | `cache_path("<name>")` |
| `noc_graph_cache.py::cache_path()` | delegates to `cache_backend.cache_path("noc-graph")` |
| `cache_telemetry.py`, `brief_ledger.py` (NDJSON ledgers) | `cache_dir() / "<name>.ndjson"` |

One resolver. One location. Eight caches + two ledgers.

## What this pattern does NOT do

- **It does NOT change SQLite schemas.** Each cache module owns its DDL. Tier-1 just moves the
  file location.
- **It does NOT re-embed on auto-pull.** Vectors transfer verbatim from pgvector → JSON →
  SQLite.
- **It does NOT block on a missing remote.** Auto-pull is best-effort; the standard refresh
  flow handles cache absence by rebuilding locally.
- **It does NOT cover `noc-graph` in the pull direction yet.** The graph is cheap to rebuild
  from local sources (~13 s full repo); pulling it would add complexity for no time savings.

## Composes with

- `KB § PATTERNS/common/cache-auto-freshness.md` — the per-boundary refresh rule.
- `KB § PATTERNS/common/cache-locking-discipline.md` — WAL mode for concurrent access.
- `KB § PATTERNS/devops/prod-cache-container.md` — the Tier-2 pgvector container.
- `KB § PATTERNS/devops/prod-deploy-safety-gates.md` — covers `cache_deploy_mirror` (the Local → Remote sync direction) alongside the pre-deploy gate composite. (No standalone `cache-deploy-mirror.md` KB doc today; the tool's docstring + that pattern doc are the authority.)
- `KB § PATTERNS/common/push-time-embedding-gate.md` — the universal-refresh rule the cost
  of which this pattern eliminates for fresh worktrees.

## History

- 2026-05-28 — codified after a 50-minute pre-commit stall on a fresh worktree exposed the
  per-worktree `.claude/cache/` design as the root cause. Two-tier architecture shipped:
  Tier-1 relocation + migration in the same commit; Tier-2 cache_pull + auto-pull-on-empty
  alongside. Replaces the abandoned "inherit cache by symlink" first-cut proposal (which
  perpetuated per-worktree state rather than fixing it).

"""Shared embedding-cache infrastructure — the N=4 consolidation (v4.0).

Until v4.0 each of the 4 embedding caches (kb / code / memory / corpus)
carried its own copy of: chunker, embedder wrapper, cosine helper, vector-
pack helper, WAL+sqlite-vec connect, schema templates, refresh loop, search
loop. The N=4 recurrence triggered the formalization rule — this module is
the single source.

Public surface:
  EMBEDDING_DIM, MAX_CHUNK_CHARS, MIN_CHUNK_CHARS — knobs.
  HAS_VEC                                          — runtime flag.
  chunk_markdown(text) -> list[str]                — markdown-structural.
  embed_sync(text) -> list[float]                  — sync wrap of seed lib.
  cosine(a, b) -> float                            — pure-Python.
  pack_vec(vec) -> bytes                           — little-endian float32.
  connect_cache(cache_path) -> sqlite3.Connection  — WAL + sqlite-vec.

For the per-corpus modules (kb / memory / corpus — markdown-shaped):
  MarkdownCorpus dataclass + refresh_markdown_corpus + search_markdown_corpus

code-embeddings stays its own module because its chunker is AST-based for
.py and whole-file for .ts/.tsx — a different shape from markdown — but
adopts the shared embed/cosine/pack/connect helpers.

KB § PATTERNS/common/kb-vector-search.md (the first incarnation),
KB § PATTERNS/common/memory-embeddings.md / corpus-embeddings.md.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import math
import os
import sqlite3
import struct
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, TypeVar

from .cache_backend import apply_locking_pragmas
from ._llm_bootstrap import ensure_llm_configured

_T = TypeVar("_T")


# ── Knobs ──────────────────────────────────────────────────────────────────
EMBEDDING_DIM = 1536      # OpenAI text-embedding-3-small.
MAX_CHUNK_CHARS = 1800    # ~450 tokens; well under the 8191-token model limit.
MIN_CHUNK_CHARS = 200     # below this, don't emit (too short to be useful).


# ── sqlite-vec optional ────────────────────────────────────────────────────
try:
    import sqlite_vec  # type: ignore[import-not-found]
    HAS_VEC = True
except ImportError:
    sqlite_vec = None  # type: ignore[assignment]
    HAS_VEC = False


# ── Time + sha helpers (shared) ────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


# ── Async-from-sync bridge ─────────────────────────────────────────────────
def run_coro_blocking(coro):
    """Run an awaitable to completion from sync code, regardless of whether
    the caller is itself inside a running event loop.

    🔴 `asyncio.run()` RAISES `RuntimeError: asyncio.run() cannot be called
    from a running event loop` when a loop already exists — which is exactly
    the MCP-server case (FastMCP drives every tool inside its own loop). The
    CLI path has no loop, so the bare `asyncio.run()` only ever worked there;
    every embedding-refresh MCP tool silently errored on the real embed path.
    Use a fresh loop in a worker thread when a loop is already running, and
    `asyncio.run` directly otherwise (CLI / direct-import case).

    Mirrors `scaffold._run_coro_blocking` — the single canonical bridge for
    "sync MCP tool needs to await a seed coroutine".
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ── Proactive rate-limit throttle ──────────────────────────────────────────
# OpenAI's own guidance for avoiding 429s is to pace PROACTIVELY rather than
# only reacting with backoff: "calculate your rate limit and add a delay equal
# to its reciprocal" (https://platform.openai.com/docs/guides/rate-limits ·
# cookbook How_to_handle_rate_limits). The refresh loops call embed_sync() per
# chunk with no spacing, so a full-corpus refresh fires hundreds of requests
# back-to-back and trips the limit (the 0.4s retry-storm seen 2026-05-30).
#
# `embed_sync` is the SINGLE funnel for every embed (kb/code/corpus/memory
# refresh loops + query paths), so one min-interval gate here paces them all.
# Default = reciprocal-of-target + margin, per the user's example (a 500ms-cap
# rate becomes 550ms). Tune with NOCTUS_EMBED_MIN_INTERVAL_MS=0 to disable
# (e.g. a high-tier key that won't 429), or raise it on a tighter quota.
_DEFAULT_EMBED_MIN_INTERVAL_MS = 550
_last_embed_monotonic = 0.0


def _embed_min_interval_s() -> float:
    raw = os.environ.get("NOCTUS_EMBED_MIN_INTERVAL_MS")
    try:
        ms = float(raw) if raw is not None else _DEFAULT_EMBED_MIN_INTERVAL_MS
    except ValueError:
        ms = _DEFAULT_EMBED_MIN_INTERVAL_MS
    return max(0.0, ms / 1000.0)


def _throttle_embed() -> None:
    """Block until at least `_embed_min_interval_s()` has elapsed since the
    previous embed call. No-op when the interval is 0. Process-local (one
    refresh runs in one process); not a distributed limiter.

    Shared by BOTH `embed_sync` (one text) and `embed_batch_sync` (many texts
    in one HTTP request) — the gate paces HTTP ROUND-TRIPS, not chunks, so a
    100-chunk batch call consumes the same one throttle slot a single-chunk
    call would."""
    global _last_embed_monotonic
    interval = _embed_min_interval_s()
    if interval <= 0:
        return
    now = time.monotonic()
    wait = interval - (now - _last_embed_monotonic)
    if wait > 0:
        time.sleep(wait)
    _last_embed_monotonic = time.monotonic()


# ── Embedding (sync wrap) ──────────────────────────────────────────────────
def embed_sync(text: str) -> list[float]:
    """Sync-wrap the async `noctusai_lib.integrations.llm.generate_embedding`.

    Loop-safe (see `run_coro_blocking`): works both under the MCP server's
    running loop and from the loop-free CLI.

    Self-configures the LLM (see `ensure_llm_configured`): the funnel satisfies
    its OWN `configure_llm()` precondition instead of offloading it to callers,
    so every embed path works in-process — CLI, the live MCP server, pre-push
    hooks, tests. (Offloading it to callers was the source of the recurring
    "LLM not configured" drift: only the CLI ran the bootstrap.)

    Proactively rate-limited (see `_throttle_embed`): consecutive embeds are
    spaced ≥ NOCTUS_EMBED_MIN_INTERVAL_MS apart so a full-corpus refresh paces
    itself under the OpenAI limit instead of relying on 429 backoff.

    Single-text — used for QUERY-time embeds (search()) where there is only
    ever one text. Refresh LOOPS should call `embed_batch_sync` instead (see
    its docstring for why per-chunk single calls self-inflict rate limits).
    """
    from noctusai_lib.integrations.llm import generate_embedding
    ensure_llm_configured()
    _throttle_embed()
    return run_coro_blocking(generate_embedding(text))


# ── Batch size knob ─────────────────────────────────────────────────────────
# OpenAI's /embeddings endpoint accepts an array `input` of up to 2048 items
# per request, with a combined-token budget well above what this default
# risks (the largest chunk shape in this repo — code_embeddings' 6000-char
# AST chunks — is ~1500 tokens; 64 * 1500 = 96k tokens, comfortably under the
# per-request ceiling). Conservative default; tune per-environment via
# NOCTUS_EMBED_BATCH_SIZE without a code change (mirrors the
# NOCTUS_EMBED_MIN_INTERVAL_MS pacing knob above).
_DEFAULT_EMBED_BATCH_SIZE = 64


def _embed_batch_size() -> int:
    raw = os.environ.get("NOCTUS_EMBED_BATCH_SIZE")
    try:
        n = int(raw) if raw is not None else _DEFAULT_EMBED_BATCH_SIZE
    except ValueError:
        n = _DEFAULT_EMBED_BATCH_SIZE
    return max(1, n)


def iter_batches(items: list[_T], batch_size: int | None = None) -> Iterator[list[_T]]:
    """Slice `items` into consecutive chunks of ≤ `batch_size` (default:
    `_embed_batch_size()`, env-tunable). Generic — used to batch (idx, text)
    pairs for the embed-corpus refresh loops."""
    n = batch_size if batch_size is not None else _embed_batch_size()
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ── Batch embedding (sync wrap) ─────────────────────────────────────────────
def embed_batch_sync(texts: list[str]) -> list[list[float]]:
    """Sync-wrap `noctusai_lib.integrations.llm.generate_embeddings_batch` —
    ONE HTTP round-trip for MANY texts.

    **This is the fix for the 2026-08 pre-push retry-storm.** Every refresh
    loop (code/kb/corpus/memory embeddings) used to call `embed_sync()` once
    PER CHUNK: 508 chunks meant 508 separate OpenAI requests, each
    independently paced+retried — self-inflicted 429s (OpenAI itself was
    healthy the whole time; a single direct embed call always succeeded).
    The `/embeddings` endpoint accepts an ARRAY `input`, so calling this once
    per `iter_batches()` slice collapses N chunks into `ceil(N/batch_size)`
    requests — 508 chunks at the default batch size of 64 is 8 requests, not
    508.

    Same self-configuring + pacing contract as `embed_sync` (see its
    docstring): `ensure_llm_configured()` + `_throttle_embed()` — the
    throttle gates ONE HTTP round-trip regardless of how many texts ride
    inside it, so a batch of 64 consumes the same one pacing slot a single
    chunk would.

    Order-preserving: `result[i]` embeds `texts[i]`. Returns `[]` for an
    empty list without making any call (no-op — preserves the per-chunk
    source_sha idempotency contract: an unchanged file's chunks never reach
    this function at all, since the caller's source_sha guard skips the
    whole file upstream)."""
    if not texts:
        return []
    from noctusai_lib.integrations.llm import generate_embeddings_batch
    ensure_llm_configured()
    _throttle_embed()
    return run_coro_blocking(generate_embeddings_batch(texts))


# ── Real-usage capture ─────────────────────────────────────────────────────
# The provider (openai_provider.generate_embedding) already records the REAL
# `usage.total_tokens` from the API response via `record_usage`, which
# dispatches a UsageEvent to `config.usage_sink`. The dev cost ledger
# (vector-costs.ndjson) historically logged only a `len//4` ESTIMATE — useless
# for calibrating real production cost. `capture_embedding_usage()` installs a
# scoped sink that accumulates the ground-truth usage for every embed inside the
# block (chaining to any pre-existing sink so production logging is untouched),
# so refreshers can log `actual_tokens` + `actual_cost_usd` alongside the
# estimate. KB § PATTERNS/common/vectorize-embed-cache-framework.md.


class UsageAccumulator:
    """Sums real provider usage across the embeds inside a capture block."""

    def __init__(self) -> None:
        self.calls: int = 0
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.cost_usd: float = 0.0

    @property
    def has_data(self) -> bool:
        """True iff at least one embed reported a real token count."""
        return self.calls > 0 and self.total_tokens > 0


def install_capture_sink(acc: UsageAccumulator) -> Callable[[], None]:
    """Install a chaining capture sink that feeds `acc`; return a restore fn.

    Lower-level primitive for linear batch flows (kb/code refreshers) that
    can't easily wrap their embed loop in a `with` block: call before the loop,
    invoke the returned callable after it (ideally in a `finally`). The
    capturing sink chains to any pre-existing sink so production logging is not
    dropped. Returns a no-op restore when the LLM config is unavailable.
    """
    try:
        from noctusai_lib.integrations.llm.client import get_llm_config
        config = get_llm_config()
    except Exception:
        return lambda: None

    prev_sink = getattr(config, "usage_sink", None)

    class _CaptureSink:
        async def record(self, event: Any) -> None:
            try:
                acc.calls += 1
                acc.total_tokens += int(getattr(event, "total_tokens", 0) or 0)
                acc.prompt_tokens += int(getattr(event, "prompt_tokens", 0) or 0)
                acc.cost_usd += float(getattr(event, "cost_estimate_usd", 0.0) or 0.0)
            finally:
                # Chain to the previous sink so production usage logging is
                # not dropped while we observe.
                if prev_sink is not None:
                    try:
                        await prev_sink.record(event)
                    except Exception:
                        pass

    config.usage_sink = _CaptureSink()

    def _restore() -> None:
        config.usage_sink = prev_sink

    return _restore


@contextmanager
def capture_embedding_usage() -> Iterator[UsageAccumulator]:
    """Capture the REAL provider usage for every embed within the block.

    Installs a chaining UsageSink on the active LLM config for the duration,
    accumulating `total_tokens` / `prompt_tokens` / `cost_estimate_usd` from
    each `UsageEvent` the provider emits, then restores the previous sink.

    Usage::

        with capture_embedding_usage() as usage:
            vec = embed_sync(text)        # or many embeds
        log_refresh_batch(..., actual_tokens=usage.total_tokens,
                          actual_cost_usd=usage.cost_usd)

    Never raises from the sink path — capture is best-effort observability and
    must not break the embed it observes. Degrades to `has_data == False` when
    the LLM config is unavailable (e.g. fake provider with no usage).
    """
    acc = UsageAccumulator()
    restore = install_capture_sink(acc)
    try:
        yield acc
    finally:
        restore()


# ── Cosine ─────────────────────────────────────────────────────────────────
def cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. ~10ms for 1536-D × 500 vectors."""
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ── Top-K similarity ranking ────────────────────────────────────────────────


def top_k_similar(
    query_vec: list[float],
    candidates: Iterable[tuple[list[float], _T]],
    *,
    k: int = 5,
    min_score: float = 0.0,
) -> list[tuple[float, _T]]:
    """Return the top-K ``(score, item)`` pairs ranked by cosine similarity.

    Generic over the payload type ``T`` — consumers pass ``(vec, any_dict)``
    pairs and get back ``(score, any_dict)`` pairs sorted high-to-low.

    Parameters
    ----------
    query_vec:
        The query embedding.
    candidates:
        Iterable of ``(vector, item)`` pairs.  ``item`` is opaque — returned
        as-is alongside the score.
    k:
        Maximum number of results to return.
    min_score:
        Pairs with ``cosine(query_vec, vec) < min_score`` are excluded.
        Defaults to 0.0 (includes all non-negative similarities).

    Returns
    -------
    List of ``(score, item)`` tuples sorted by score descending, length ≤ k.
    """
    scored: list[tuple[float, _T]] = []
    for vec, item in candidates:
        score = cosine(query_vec, vec)
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:k]


# ── Vector pack ────────────────────────────────────────────────────────────
def pack_vec(vec: list[float]) -> bytes:
    """sqlite-vec stores vectors as little-endian float32 BLOBs."""
    return struct.pack(f"{len(vec)}f", *vec)


# ── Connect (WAL + sqlite-vec) ─────────────────────────────────────────────
def connect_cache(cache_path: Path) -> sqlite3.Connection:
    """Open the SQLite cache with WAL journal + sqlite-vec extension loaded
    (when available). Idempotent — safe to call multiple times."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row
    apply_locking_pragmas(conn)
    if HAS_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


# ── Markdown chunker ───────────────────────────────────────────────────────
def chunk_markdown(text: str) -> list[str]:
    """Split a markdown doc into chunks at H2 boundaries, then char-cap.

    Each chunk preserves the H1 title as a prefix for context (so a chunk
    can be retrieved standalone without losing what doc it's from).
    """
    lines = text.splitlines()
    title = ""
    for line in lines[:30]:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Split at H2 boundaries.
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    if not sections:
        sections = [lines]

    chunks: list[str] = []
    for sec in sections:
        body = "\n".join(sec).strip()
        if not body:
            continue
        prefixed = f"{title}\n\n{body}" if title and not body.startswith(title) else body
        while len(prefixed) > MAX_CHUNK_CHARS:
            cut = prefixed.rfind("\n", MIN_CHUNK_CHARS, MAX_CHUNK_CHARS)
            if cut < 0:
                cut = MAX_CHUNK_CHARS
            chunks.append(prefixed[:cut].strip())
            prefixed = (f"{title}\n\n" if title else "") + prefixed[cut:].strip()
        if len(prefixed) >= MIN_CHUNK_CHARS:
            chunks.append(prefixed.strip())
    return chunks


# ── Schema templates ───────────────────────────────────────────────────────
def meta_schema_sql(
    chunks_table: str,
    extra_columns: Optional[dict[str, str]] = None,
) -> str:
    """DDL for cache_meta + the per-corpus chunks table.

    extra_columns: {col_name: sql_type_with_constraints} appended BEFORE the
    standard (path, chunk_idx, chunk_text, source_sha, cached_at) — used by
    corpus-embeddings for source_type, by code-embeddings for symbol_name.
    """
    extra_cols_sql = ""
    extra_indexes_sql = ""
    if extra_columns:
        for col, decl in extra_columns.items():
            extra_cols_sql += f"  {col}         {decl},\n"
            extra_indexes_sql += (
                f"CREATE INDEX IF NOT EXISTS "
                f"idx_{chunks_table}_{col} ON {chunks_table}({col});\n"
            )
    return f"""
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS {chunks_table} (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
{extra_cols_sql}  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{chunks_table}_path ON {chunks_table}(path);
{extra_indexes_sql}"""


def vec_schema_sql(vec_table: str) -> str:
    return f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {vec_table} USING vec0(
  embedding float[{EMBEDDING_DIM}]
);
"""


def json_fallback_schema_sql(json_table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {json_table} (
  chunk_rowid  INTEGER PRIMARY KEY,
  embedding    TEXT NOT NULL
);
"""


def init_schema(
    conn: sqlite3.Connection,
    chunks_table: str,
    vec_table: str,
    json_table: str,
    extra_columns: Optional[dict[str, str]] = None,
) -> None:
    """Create the chunks table + BOTH sibling embedding tables.

    Before 2026-08-14 this created ONLY the current process's engine table
    (`if HAS_VEC: vec else: json`). `sqlite-vec` is an opportunistically
    pip-installed, UNPINNED package (absent from every requirements.txt /
    pyproject.toml in this repo) — present in `mcp/noctusai/.venv` (the
    MCP-server + pre-push venv) but not in the repo-root `venv` or a fresh
    CI checkout. A cache refreshed across environments with different
    `HAS_VEC` values over its lifetime therefore only ever got ONE of its
    two sibling tables created, so a later delete running under the OTHER
    environment had nowhere to clean up the previous generation's rows —
    both tables silently drifted into disjoint halves of the corpus (see
    `delete_embedding_rows` below + KB § PATTERNS/devops/
    cache-deploy-mirror.md — the 2026-08-14 cache-mirror-join-drift root
    cause). Creating BOTH tables unconditionally here closes that gap.

    `json_table` is a PLAIN table (zero extension dependency) — always
    safe to create. `vec_table` is a vec0 VIRTUAL table — only creatable
    when the sqlite-vec extension is loaded on this connection (HAS_VEC).
    """
    conn.executescript(meta_schema_sql(chunks_table, extra_columns))
    conn.executescript(json_fallback_schema_sql(json_table))
    if HAS_VEC:
        conn.executescript(vec_schema_sql(vec_table))
    conn.commit()


def delete_embedding_rows(
    conn: sqlite3.Connection,
    *,
    vec_table: str,
    json_table: str,
    rowids: list[int],
) -> None:
    """Delete `rowids` from BOTH sibling embedding tables, unconditionally.

    NOT gated on the current process's `HAS_VEC` alone (the pre-2026-08-14
    bug) — a row may have been WRITTEN by a different process/environment
    than the one running this delete (the pre-push githook's venv vs. the
    long-lived MCP-server venv vs. CI can each have a different sqlite-vec
    availability), so cleaning only "this process's" engine strands the
    OTHER engine's rows as permanent orphans referencing a since-deleted
    chunk rowid. `json_table` is always reachable (plain table). The
    `vec_table` delete only runs when `HAS_VEC` — a documented residual
    boundary: an environment without the extension cannot reach a vec0
    virtual table at all, so it cannot clean vec-side orphans it did not
    create. In practice the canonical write path (pre-push + the MCP
    server) both run under the sqlite-vec-capable venv, so this covers
    the dominant case. KB § PATTERNS/devops/cache-deploy-mirror.md.
    """
    if not rowids:
        return
    placeholders = ",".join("?" * len(rowids))
    conn.execute(
        f"DELETE FROM {json_table} WHERE chunk_rowid IN ({placeholders})", rowids
    )
    if HAS_VEC:
        conn.execute(
            f"DELETE FROM {vec_table} WHERE rowid IN ({placeholders})", rowids
        )


def backfill_cross_engine_embeddings(
    conn: sqlite3.Connection,
    *,
    chunks_table: str,
    vec_table: str,
    json_table: str,
) -> dict[str, Any]:
    """One-time LOSSLESS repair for the 2026-08-14 cache-mirror-join-drift
    incident.

    Root cause (see `delete_embedding_rows`): every chunk's embedding lives
    in EXACTLY ONE sibling table (never both, never neither — verified
    empirically across all 4 local caches before this fix shipped). This
    copies every embedding that exists ONLY in `json_table` across into
    `vec_table` — same vector, decoded+re-packed, ZERO re-embed / zero
    OpenAI spend — so both engines become self-consistent supersets of
    every LIVE chunk's embedding. It then prunes rows in either sibling
    table that reference a chunk rowid no longer present in `chunks_table`
    (genuine garbage from a since-superseded doc generation).

    Requires `HAS_VEC` (the copy target is a vec0 virtual table) — returns
    `status='skipped-no-vec'` otherwise (a no-op, not an error: run this
    from an environment with sqlite-vec loaded, e.g. `mcp/noctusai/.venv`).
    Idempotent — safe to re-run (rows already in `vec_table` are skipped).

    Returns `{ok, status, copied_json_to_vec, deleted_orphan_json,
    deleted_orphan_vec, chunks_total}`.
    """
    if not HAS_VEC:
        return {
            "ok": True, "status": "skipped-no-vec",
            "copied_json_to_vec": 0, "deleted_orphan_json": 0,
            "deleted_orphan_vec": 0, "chunks_total": 0,
        }

    live_rowids = {
        r[0] for r in conn.execute(
            f"SELECT rowid_alias FROM {chunks_table}"
        ).fetchall()
    }
    existing_vec_rowids = {
        r[0] for r in conn.execute(f"SELECT rowid FROM {vec_table}").fetchall()
    }

    copied = 0
    for chunk_rowid, embedding_json in conn.execute(
        f"SELECT chunk_rowid, embedding FROM {json_table}"
    ).fetchall():
        if chunk_rowid in existing_vec_rowids or chunk_rowid not in live_rowids:
            continue
        try:
            vec = json.loads(embedding_json)
        except (TypeError, ValueError):
            continue
        conn.execute(
            f"INSERT INTO {vec_table}(rowid, embedding) VALUES (?, ?)",
            (chunk_rowid, pack_vec(vec)),
        )
        copied += 1

    # Prune true garbage — sibling rows whose chunk no longer exists (a doc
    # generation superseded since that row was written).
    deleted_json = conn.execute(
        f"DELETE FROM {json_table} WHERE chunk_rowid NOT IN "
        f"(SELECT rowid_alias FROM {chunks_table})"
    ).rowcount
    deleted_vec = conn.execute(
        f"DELETE FROM {vec_table} WHERE rowid NOT IN "
        f"(SELECT rowid_alias FROM {chunks_table})"
    ).rowcount

    conn.commit()
    return {
        "ok": True, "status": "repaired",
        "copied_json_to_vec": copied,
        "deleted_orphan_json": deleted_json,
        "deleted_orphan_vec": deleted_vec,
        "chunks_total": len(live_rowids),
    }


# ── Markdown corpus spec + refresh + search ────────────────────────────────

@dataclass
class MarkdownCorpus:
    """The parameter pack each per-corpus module passes to refresh / search.

    `enumerate_sources` yields `(rel_path: str, abs_path: Path,
    extras: dict[str, str])` triples. `extras` populates the configured
    `extra_columns` (e.g. `{"source_type": "agent"}` for corpus-embeddings;
    empty dict for kb / memory which have no extras).
    """
    cache_path: Path
    chunks_table: str
    vec_table: str
    json_table: str
    enumerate_sources: Callable[[], Iterable[tuple[str, Path, dict]]]
    extra_columns: dict[str, str] = field(default_factory=dict)


def _delete_rows_for_path(conn: sqlite3.Connection, corpus: MarkdownCorpus, rel: str) -> None:
    """Wipe stale rows for one source path from both engines' tables."""
    cur = conn.execute(
        f"SELECT rowid_alias FROM {corpus.chunks_table} WHERE path=?", (rel,)
    )
    old_rowids = [r[0] for r in cur.fetchall()]
    if not old_rowids:
        return
    delete_embedding_rows(
        conn,
        vec_table=corpus.vec_table,
        json_table=corpus.json_table,
        rowids=old_rowids,
    )
    conn.execute(f"DELETE FROM {corpus.chunks_table} WHERE path=?", (rel,))


def prune_orphan_chunks(
    conn: sqlite3.Connection,
    *,
    chunks_table: str,
    vec_table: str,
    json_table: str,
    live_rels: Iterable[str],
    exclude_organ: bool = False,
) -> list[str]:
    """Delete rows for source paths absent from `live_rels` (the on-disk set).

    The single source for orphan-pruning across all embedding caches (kb /
    code / markdown-corpus) — formalized at N=3 per the recurrence rule.
    Callers MUST invoke this ONLY on a full pass (no `paths=` scope), else a
    scoped refresh would delete every out-of-scope row.

    `exclude_organ=True` skips `kind='organ'` rows: W4 organs share the
    `code_chunks` table but carry a bundle source_sha and live OUTSIDE the
    tracked roots, so they're absent from `live_rels` and would be falsely
    pruned. Returns the list of pruned paths.
    """
    organ_filter = " AND COALESCE(kind,'') != 'organ'" if exclude_organ else ""
    base_filter = " WHERE COALESCE(kind,'') != 'organ'" if exclude_organ else ""
    cached = [
        r[0] for r in conn.execute(
            f"SELECT DISTINCT path FROM {chunks_table}{base_filter}"
        ).fetchall()
    ]
    live = set(live_rels)
    pruned: list[str] = []
    for orphan in (set(cached) - live):
        rowids = [
            r[0] for r in conn.execute(
                f"SELECT rowid_alias FROM {chunks_table} WHERE path=?{organ_filter}",
                (orphan,),
            ).fetchall()
        ]
        delete_embedding_rows(
            conn, vec_table=vec_table, json_table=json_table, rowids=rowids
        )
        conn.execute(
            f"DELETE FROM {chunks_table} WHERE path=?{organ_filter}", (orphan,)
        )
        pruned.append(orphan)
    return pruned


def refresh_markdown_corpus(
    corpus: MarkdownCorpus,
    *,
    force: bool = False,
    paths: Optional[list[str]] = None,
    cost_namespace: Optional[str] = None,
) -> dict[str, Any]:
    """Re-populate the corpus's embeddings cache.

    Per-file `source_sha` skip when unchanged. Atomic per-doc — partial
    embed failure rolls back that doc's rows. Other corpora are unaffected.

    When `cost_namespace` is given (e.g. ``"corpus-embeddings"`` /
    ``"memory-embeddings"``), the REAL provider token usage is captured across
    the whole batch and logged to the vector-costs ledger (estimate + actual).
    Omit it to preserve the prior no-logging behaviour.

    Returns: ``{ok, status, refreshed, skipped, errors, rows_written}``.
    """
    conn = connect_cache(corpus.cache_path)
    init_schema(
        conn,
        chunks_table=corpus.chunks_table,
        vec_table=corpus.vec_table,
        json_table=corpus.json_table,
        extra_columns=corpus.extra_columns,
    )

    refreshed: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    total_rows = 0

    # Capture the REAL provider token usage across the batch (ground truth for
    # the cost ledger). No-op when cost_namespace is None.
    _usage = UsageAccumulator()
    _restore_usage = install_capture_sink(_usage) if cost_namespace else (lambda: None)

    sources = list(corpus.enumerate_sources())
    if paths:
        wanted = set(paths)
        sources = [s for s in sources if s[0] in wanted]

    for rel, abs_path, extras in sources:
        sha = sha_file(abs_path)
        if not force:
            cur = conn.execute(
                f"SELECT DISTINCT source_sha FROM {corpus.chunks_table} "
                f"WHERE path=? LIMIT 1",
                (rel,),
            )
            row = cur.fetchone()
            if row and row["source_sha"] == sha:
                skipped.append(rel)
                continue

        _delete_rows_for_path(conn, corpus, rel)

        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append({"path": rel, "error": f"read: {e}"})
            continue

        chunks = chunk_markdown(text)
        if not chunks:
            continue

        ts = now_iso()
        per_doc_ok = True
        per_doc_rowids: list[int] = []

        # Build the INSERT column list dynamically based on extra_columns.
        extra_col_names = list(corpus.extra_columns.keys())
        insert_cols = (
            extra_col_names
            + ["path", "chunk_idx", "chunk_text", "source_sha", "cached_at"]
        )
        placeholders = ",".join("?" * len(insert_cols))
        insert_sql = (
            f"INSERT INTO {corpus.chunks_table}({','.join(insert_cols)}) "
            f"VALUES ({placeholders})"
        )

        # Batch the embed calls — ONE HTTP round-trip per `iter_batches()`
        # slice instead of one PER CHUNK (the 2026-08 retry-storm root
        # cause: N chunks used to mean N independently-paced-and-retried
        # requests). A batch failure fails ALL chunks in that slice
        # together, preserving the existing per-DOC all-or-nothing rollback
        # below (this doc's earlier-batch rows are rolled back too — a doc's
        # cached rows are never left partially embedded).
        for batch in iter_batches(list(enumerate(chunks))):
            batch_texts = [c for _idx, c in batch]
            try:
                vecs = embed_batch_sync(batch_texts)
            except Exception as e:  # noqa: BLE001
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0], "error": str(e)[:200],
                })
                per_doc_ok = False
                break
            if len(vecs) != len(batch):
                errors.append({
                    "path": rel, "chunk_idx": batch[0][0],
                    "error": f"batch embed returned {len(vecs)} vectors for {len(batch)} inputs",
                })
                per_doc_ok = False
                break
            dim_bad = next((i for i, v in enumerate(vecs) if len(v) != EMBEDDING_DIM), None)
            if dim_bad is not None:
                errors.append({
                    "path": rel, "chunk_idx": batch[dim_bad][0],
                    "error": f"unexpected dim {len(vecs[dim_bad])} (want {EMBEDDING_DIM})",
                })
                per_doc_ok = False
                break

            for (idx, chunk), vec in zip(batch, vecs):
                extra_values = [extras.get(col) for col in extra_col_names]
                row_values = (
                    *extra_values, rel, idx, chunk, sha, ts,
                )
                cur = conn.execute(insert_sql, row_values)
                row_id = cur.lastrowid
                per_doc_rowids.append(row_id)
                if HAS_VEC:
                    conn.execute(
                        f"INSERT INTO {corpus.vec_table}(rowid, embedding) VALUES (?, ?)",
                        (row_id, pack_vec(vec)),
                    )
                else:
                    conn.execute(
                        f"INSERT INTO {corpus.json_table}(chunk_rowid, embedding) "
                        f"VALUES (?, ?)",
                        (row_id, json.dumps(vec)),
                    )
                total_rows += 1

        if not per_doc_ok and per_doc_rowids:
            delete_embedding_rows(
                conn,
                vec_table=corpus.vec_table,
                json_table=corpus.json_table,
                rowids=per_doc_rowids,
            )
            conn.execute(
                f"DELETE FROM {corpus.chunks_table} WHERE path=?", (rel,)
            )
        if per_doc_ok:
            refreshed.append(rel)

    # Orphan prune (full passes only) — drop rows for sources no longer on
    # disk. Shared helper; scoped refreshes (`paths=`) never prune.
    pruned: list[str] = []
    if not paths:
        pruned = prune_orphan_chunks(
            conn,
            chunks_table=corpus.chunks_table,
            vec_table=corpus.vec_table,
            json_table=corpus.json_table,
            live_rels={rel for rel, _abs, _extras in sources},
        )

    conn.commit()
    conn.close()
    _restore_usage()

    # Cost instrumentation — log real provider usage alongside the estimate.
    # Opt-in via cost_namespace; skipped when nothing was embedded.
    if cost_namespace and total_rows > 0:
        try:
            from . import vector_costs as _vc
            _estimated_tokens = total_rows * (MAX_CHUNK_CHARS // 4)
            _actual_tokens = _usage.total_tokens if _usage.has_data else None
            _actual_cost = _usage.cost_usd if _usage.has_data else None
            _vc.log_refresh_batch(
                namespace=cost_namespace,
                model="text-embedding-3-small",
                doc_count=len(refreshed),
                chunk_count=total_rows,
                estimated_tokens=_estimated_tokens,
                provider="openai",
                source_ref=f"session:{now_iso()[:10]}",
                actual_tokens=_actual_tokens,
                actual_cost_usd=_actual_cost,
            )
        except Exception:  # noqa: BLE001 — never block refresh on logging
            pass

    status = "refreshed" if refreshed else ("in-sync" if not errors else "errors")
    return {
        "ok": not errors,
        "status": status,
        "refreshed": refreshed,
        "skipped": skipped,
        "errors": errors,
        "rows_written": total_rows,
        "pruned": pruned,
    }


def search_markdown_corpus(
    corpus: MarkdownCorpus,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    where_clause: Optional[str] = None,
    where_params: Optional[list] = None,
) -> list[dict]:
    """Embed `query`, return top-K matching chunks ranked by cosine similarity.

    Optional `where_clause` (without WHERE keyword) + `where_params` scopes
    the search — used by corpus-embeddings for `source_type=?` filtering.

    Returns: `[{<extra columns…>, path, chunk_idx, chunk_text, score, engine}]`
    ordered by score desc. Lazy-degrade: empty list if cache missing or
    embedding API unreachable.
    """
    if not corpus.cache_path.exists():
        return []
    try:
        q_vec = embed_sync(query)
    except Exception:
        return []

    conn = connect_cache(corpus.cache_path)
    init_schema(
        conn,
        chunks_table=corpus.chunks_table,
        vec_table=corpus.vec_table,
        json_table=corpus.json_table,
        extra_columns=corpus.extra_columns,
    )

    extra_select = ",".join(f"c.{c}" for c in corpus.extra_columns)
    extra_cols_csv = extra_select + ", " if extra_select else ""
    where_sql = f" AND ({where_clause})" if where_clause else ""
    params_extra = where_params or []

    results: list[dict] = []
    if HAS_VEC:
        q_blob = pack_vec(q_vec)
        sql = (
            f"SELECT {extra_cols_csv}c.path, c.chunk_idx, c.chunk_text, v.distance "
            f"FROM {corpus.vec_table} v "
            f"JOIN {corpus.chunks_table} c ON c.rowid_alias = v.rowid "
            f"WHERE v.embedding MATCH ? AND k = ?{where_sql} "
            f"ORDER BY v.distance"
        )
        cur = conn.execute(sql, (q_blob, top_k, *params_extra))
        for r in cur.fetchall():
            score = 1.0 / (1.0 + float(r["distance"]))
            if score >= min_score:
                hit = {col: r[col] for col in corpus.extra_columns}
                hit.update({
                    "path": r["path"], "chunk_idx": r["chunk_idx"],
                    "chunk_text": r["chunk_text"], "score": score,
                    "engine": "sqlite-vec",
                })
                results.append(hit)
    else:
        sql = (
            f"SELECT {extra_cols_csv}c.path, c.chunk_idx, c.chunk_text, j.embedding "
            f"FROM {corpus.chunks_table} c "
            f"JOIN {corpus.json_table} j ON j.chunk_rowid = c.rowid_alias"
        )
        if where_clause:
            sql += f" WHERE {where_clause}"
            rows = conn.execute(sql, tuple(params_extra)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        scored = []
        for r in rows:
            try:
                v = json.loads(r["embedding"])
            except (TypeError, ValueError):
                continue
            score = cosine(q_vec, v)
            if score >= min_score:
                scored.append((score, r))
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, r in scored[:top_k]:
            hit = {col: r[col] for col in corpus.extra_columns}
            hit.update({
                "path": r["path"], "chunk_idx": r["chunk_idx"],
                "chunk_text": r["chunk_text"], "score": score,
                "engine": "fallback-cosine",
            })
            results.append(hit)
    conn.close()
    return results


def aggregate_source_sha(sources: Iterable[tuple[str, Path, dict]]) -> str:
    """Aggregate sha over every source file's content + extras — for the
    freshness keeper."""
    h = hashlib.sha256()
    for rel, abs_path, extras in sorted(sources, key=lambda s: s[0]):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        for k, v in sorted(extras.items()):
            h.update(f"{k}={v}".encode("utf-8"))
            h.update(b"\0")
        if abs_path.exists():
            h.update(abs_path.read_bytes())
    return h.hexdigest()[:12]


__all__ = [
    "EMBEDDING_DIM", "MAX_CHUNK_CHARS", "MIN_CHUNK_CHARS", "HAS_VEC",
    "now_iso", "sha_file",
    "chunk_markdown", "embed_sync", "embed_batch_sync", "iter_batches",
    "cosine", "top_k_similar", "pack_vec", "connect_cache",
    "meta_schema_sql", "vec_schema_sql", "json_fallback_schema_sql",
    "init_schema", "delete_embedding_rows", "backfill_cross_engine_embeddings",
    "MarkdownCorpus", "refresh_markdown_corpus", "search_markdown_corpus",
    "aggregate_source_sha",
]

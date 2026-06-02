"""noc-graph cache — the 8th keeper-mirror cache.

What it mirrors
    The materialized knowledge graph built by ``noctusai_lib.graph.build_graph``
    — modules / classes / functions / routes / mcp tools / React components /
    hooks / KB patterns / memory / agents / skills / commands / cli flags +
    edges between them (imports, kb_pointers, owns_kb, exposes_tool,
    auto_triggers, …). Sibling of the 7 existing caches; carries the same
    3-leg mirror contract (eager pre-commit + post-merge + post-checkout
    refresh + lazy keeper).

What it stores
    SQLite tables under ``.claude/cache/noc-graph.sqlite``:
        - ``cache_meta``        — aggregate_source_sha, last_refresh, scope, counts
        - ``noc_graph_nodes``   — one row per node (id PK + kind / path / meta)
        - ``noc_graph_edges``   — one row per edge (source, target, kind)
        - ``noc_graph_files``   — one row per source file (path PK + source_sha
                                  + node_ids JSON) for incremental rebuilds

Why SQLite (not just graph.json)
    - O(log N) lookup by id / kind / product / path.
    - Indexed neighbor traversal (edges.source + edges.target).
    - Per-file source_sha enables incremental rebuilds (rebuild only
      changed files; merge into the existing graph).
    - Concurrent reader-friendly (WAL mode); query tools can mmap.

The .json / .html outputs under ``.noc-graph/`` are now DERIVED from this
cache — they stay around as portable artifacts (open in a browser; pipe to
visualization tooling) but the cache is the source of truth.

KB § PATTERNS/architect/noc-graph.md.
KB § PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

from settings import REPO_ROOT


# ── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS noc_graph_nodes (
  id          TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  kind        TEXT NOT NULL,
  path        TEXT,
  line        INTEGER,
  end_line    INTEGER,
  product     TEXT,
  cluster     INTEGER,
  confidence  REAL NOT NULL,
  meta_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_noc_graph_nodes_kind    ON noc_graph_nodes(kind);
CREATE INDEX IF NOT EXISTS idx_noc_graph_nodes_product ON noc_graph_nodes(product);
CREATE INDEX IF NOT EXISTS idx_noc_graph_nodes_path    ON noc_graph_nodes(path);

CREATE TABLE IF NOT EXISTS noc_graph_edges (
  rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
  source      TEXT NOT NULL,
  target      TEXT NOT NULL,
  kind        TEXT NOT NULL,
  confidence  REAL NOT NULL,
  weight      REAL NOT NULL DEFAULT 1.0,
  meta_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_noc_graph_edges_source ON noc_graph_edges(source);
CREATE INDEX IF NOT EXISTS idx_noc_graph_edges_target ON noc_graph_edges(target);
CREATE INDEX IF NOT EXISTS idx_noc_graph_edges_kind   ON noc_graph_edges(kind);

CREATE TABLE IF NOT EXISTS noc_graph_files (
  path        TEXT PRIMARY KEY,
  source_sha  TEXT NOT NULL,
  cached_at   TEXT NOT NULL,
  node_ids_json TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path(repo_root: Optional[Path] = None) -> Path:
    from .cache_backend import cache_path as _cp
    return _cp("noc-graph", repo_root=repo_root)


def _connect(cache_p: Path) -> sqlite3.Connection:
    from .cache_backend import apply_locking_pragmas
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_p))
    conn.row_factory = sqlite3.Row
    apply_locking_pragmas(conn)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


# ── Source-sha aggregation (for the freshness keeper) ──────────────────────


def _source_files(repo_root: Path) -> list[Path]:
    """The set of files the graph derives from — input universe."""
    paths: list[Path] = []
    # Code corpus
    skip = {"node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".git"}
    code_roots = [
        repo_root / "seed",
        repo_root / "mcp",
        repo_root / "products",
    ]
    for root in code_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            if path.suffix in (".py", ".pyi", ".ts", ".tsx"):
                paths.append(path)

    # KB + harness + landscape + memory index + history + cli
    for sub in ("KNOWLEDGE-BASE", ".claude/agents", ".claude/skills", ".claude/commands", "CLAUDE"):
        d = repo_root / sub
        if d.exists():
            for p in d.rglob("*.md"):
                if any(part in skip for part in p.parts):
                    continue
                paths.append(p)
    for name in ("CLAUDE.md", "CONTEXTUALIZE.md", "CHANGELOG.md", "VERSION"):
        p = repo_root / name
        if p.exists():
            paths.append(p)
    for projects_md in (repo_root / "projects").rglob("PROJECT.md") if (repo_root / "projects").exists() else []:
        if "archive" in projects_md.parts:
            continue
        paths.append(projects_md)
    cli_path = repo_root / "mcp" / "noctusai" / "cli.py"
    if cli_path.exists():
        paths.append(cli_path)
    ai = repo_root / "project-history" / "auto-improvement.ndjson"
    if ai.exists():
        paths.append(ai)
    ph = repo_root / "project-history" / "PROJECT-HISTORY.md"
    if ph.exists():
        paths.append(ph)
    # branch-tree.ndjson AND its mirror (branch-tree.mirror.ndjson) are EXCLUDED:
    # both are tracking METADATA (not graph-input content) and a pointer push MUST
    # NOT trigger a noc-graph rebuild. Excluded by construction (never appended to
    # the source list above). Contract: KB § CONTEXT/PATTERNS/architect/branch-tree-tracking.md
    # §3 "Cache-sync discipline".  Exclusion lives HERE (config, not a keeper bypass).
    return paths


def compute_source_sha(repo_root: Optional[Path] = None) -> str:
    """Aggregate sha256 over (repo-relative-path, content) for all source files."""
    root = repo_root or REPO_ROOT
    h = hashlib.sha256()
    files = sorted(_source_files(root), key=lambda p: p.as_posix())
    for p in files:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()[:12]


# ── Per-bucket sub-sha (for incremental rebuilds) ──────────────────────────
#
# The graph derives from 7 disjoint input buckets, each fed by a distinct set
# of extractors. The ONLY expensive bucket is ``code`` (the AST walk over the
# whole seed / mcp / products tree — the 1-2 min cost). The other six are
# bounded markdown / ndjson walks measured in single-digit seconds.
#
# Incremental rebuild therefore caches the ``code`` bucket: when its sub-sha is
# unchanged, the persisted ``code:*`` nodes/edges are reused as-is and the AST
# walk is skipped, while the cheap knowledge tier + the global finalization
# (history decoration, R3 mined edges, dedup, Louvain cluster, meta) ALWAYS
# re-run. Reuse-of-code ≡ recompute-of-code by construction (the code bucket is
# independent of every other bucket), so full and incremental produce the same
# final graph for the same tree — proven by the parity test.
#
# Sub-shas for ALL seven buckets are still computed + persisted so the decision
# logic is per-bucket explicit and ``noc_graph_status`` can report which bucket
# busted the cache.

# Bucket names in canonical order.
_BUCKETS: tuple[str, ...] = (
    "code", "kb", "harness", "landscape", "memory", "cli", "history",
)


def _bucket_of_path(rel: str) -> str | None:
    """Classify a repo-relative source path into its extractor bucket.

    Mirrors which extractor consumes the file in ``build_graph`` — NOT the
    coarse ``_source_files`` grouping (e.g. PROJECT-HISTORY.md + CHANGELOG.md
    + VERSION are consumed by ``walk_landscape``, so they land in
    ``landscape``; only auto-improvement.ndjson is the ``history`` bucket).
    Returns ``None`` for a path no bucket consumes.
    """
    # cli — the single cli.py flag-surface file.
    if rel == "mcp/noctusai/cli.py":
        return "cli"
    # code — .py/.pyi/.ts/.tsx under the walked code roots.
    if rel.split("/", 1)[0] in ("seed", "mcp", "products") and rel.rsplit(".", 1)[-1] in (
        "py", "pyi", "ts", "tsx"
    ):
        return "code"
    # kb — every markdown chapter / pattern under KNOWLEDGE-BASE.
    if rel.startswith("KNOWLEDGE-BASE/"):
        return "kb"
    # harness — the methodology fabric.
    if rel.startswith((".claude/agents/", ".claude/skills/", ".claude/commands/")):
        return "harness"
    # history — the auto-improvement event ndjson.
    if rel == "project-history/auto-improvement.ndjson":
        return "history"
    # memory — resolved at compute time (lives outside the repo tree); handled
    # separately in compute_bucket_shas (the MEMORY.md root is not a repo file).
    # landscape — CLAUDE.md + CLAUDE/*.md + CONTEXTUALIZE.md + CHANGELOG.md +
    # VERSION + PROJECT-HISTORY.md + projects/*/PROJECT.md.
    if rel in ("CLAUDE.md", "CONTEXTUALIZE.md", "CHANGELOG.md", "VERSION"):
        return "landscape"
    if rel.startswith("CLAUDE/") and rel.endswith(".md"):
        return "landscape"
    if rel == "project-history/PROJECT-HISTORY.md":
        return "landscape"
    if rel.startswith("projects/") and rel.endswith("/PROJECT.md"):
        return "landscape"
    return None


def _memory_files(repo_root: Path) -> list[Path]:
    """The memory bucket's source files (MEMORY.md + topic .md), if discoverable."""
    try:
        from noctusai_lib.graph.build import _discover_memory_root
    except ImportError:
        return []
    mem_root = _discover_memory_root(repo_root)
    if mem_root is None:
        return []
    return sorted(p for p in mem_root.rglob("*.md") if p.is_file())


def compute_bucket_shas(repo_root: Optional[Path] = None) -> dict[str, str]:
    """Per-bucket sha256 over (repo-relative-path, content), one digest per bucket.

    The union of bucket inputs equals ``_source_files`` (plus the out-of-tree
    memory files), so a change to ANY graph input bumps exactly one bucket's
    sub-sha — the lever the incremental rebuild pulls.
    """
    root = repo_root or REPO_ROOT
    buckets: dict[str, hashlib._Hash] = {b: hashlib.sha256() for b in _BUCKETS}

    # In-tree files.
    for p in sorted(_source_files(root), key=lambda p: p.as_posix()):
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        bucket = _bucket_of_path(rel)
        if bucket is None:
            continue
        h = buckets[bucket]
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")

    # Out-of-tree memory files (MEMORY.md lives under ~/.claude/...).
    mh = buckets["memory"]
    for p in _memory_files(root):
        mh.update(p.as_posix().encode("utf-8"))
        mh.update(b"\0")
        try:
            mh.update(p.read_bytes())
        except OSError:
            mh.update(b"<unreadable>")

    return {b: buckets[b].hexdigest()[:12] for b in _BUCKETS}


def get_cached_bucket_shas(repo_root: Optional[Path] = None) -> dict[str, str]:
    """Read the per-bucket sub-shas stamped by the last rebuild (empty if none)."""
    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return {}
    try:
        conn = _connect(cache_p)
    except sqlite3.OperationalError:
        return {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM cache_meta WHERE key LIKE 'bucket_sha:%'"
        ).fetchall()
        return {r["key"].split(":", 1)[1]: r["value"] for r in rows}
    finally:
        conn.close()


def get_cached_semantic_fingerprint(repo_root: Optional[Path] = None) -> str | None:
    """Read the SEMANTIC_NEIGHBOR input fingerprint stamped by the last rebuild.

    Pairs with ``noctus.graph.build.semantic_neighbor_fingerprint``: an
    unchanged fingerprint means the (embeddings, node-id-set) inputs to the
    O(N²) cosine are identical, so the persisted SEMANTIC_NEIGHBOR edges can be
    reused verbatim instead of recomputed. Returns ``None`` if absent.
    """
    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return None
    try:
        conn = _connect(cache_p)
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key = 'semantic_fingerprint'"
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def load_cached_semantic_edges(repo_root: Optional[Path] = None) -> list | None:
    """Load the persisted SEMANTIC_NEIGHBOR edges as schema ``Edge`` objects.

    Returns ``None`` if the cache is absent / unreadable, an empty list if the
    cache simply holds no semantic edges (a legitimate reuse target — e.g. a
    tree below the 2-vector threshold). The reused edges are re-added verbatim
    by ``_inject_r3_edges`` when the fingerprint is unchanged.
    """
    from noctusai_lib.graph.schema import Edge

    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return None
    try:
        conn = _connect(cache_p)
    except sqlite3.OperationalError:
        return None
    try:
        rows = conn.execute(
            "SELECT source, target, kind, confidence, weight, meta_json "
            "FROM noc_graph_edges WHERE kind = 'semantic_neighbor'"
        ).fetchall()
    finally:
        conn.close()
    edges: list = []
    for r in rows:
        meta = json.loads(r["meta_json"]) if r["meta_json"] else {}
        edges.append(Edge.from_dict({
            "source": r["source"], "target": r["target"], "kind": r["kind"],
            "confidence": r["confidence"], "weight": r["weight"], "meta": meta,
        }))
    return edges


def get_cached_source_sha(repo_root: Optional[Path] = None) -> str | None:
    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return None
    try:
        conn = _connect(cache_p)
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key = 'aggregate_source_sha'"
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


# ── Mirror — build graph + persist to SQLite ───────────────────────────────


# ``ai_*`` node-meta keys are written EXCLUSIVELY by the history extractor
# (extract_history decorates existing nodes). Reused code nodes must drop them
# so the always-re-run history pass re-derives them from scratch — otherwise a
# target that dropped out of the ndjson would keep a stale decoration. This is
# what makes "reuse cached code" byte-equivalent to "re-walk code".
_HISTORY_DECORATION_KEYS = ("ai_events", "ai_last_stage", "ai_last_ts", "ai_stages_seen")


def refresh(force: bool = False, repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Rebuild the graph + mirror it into the SQLite cache.

    Three paths:

    - **in-sync** — the aggregate source sha matches the cached value and
      ``force`` is False: no-op (the cheapest case).
    - **incremental** — the ``code`` bucket sub-sha is unchanged and a cache
      with code nodes exists: the persisted ``code:*`` nodes/edges are reused
      and the (expensive) AST walk is SKIPPED; the cheap knowledge tier
      (kb / harness / landscape / memory / cli) + the global finalization
      (history decoration, R3 mined edges, dedup, Louvain cluster) re-run.
    - **full** — ``force=True``, no usable cache, or the ``code`` bucket
      changed: re-run every extractor (the fallback / canonical path).

    Returns ``{ok, status, nodes, edges, rows_written, scope, build_seconds,
    source_sha}`` (status ∈ ``in-sync`` | ``refreshed`` | ``incremental``).
    """
    from noctusai_lib.graph import build_graph

    root = repo_root or REPO_ROOT
    cache_p = cache_path(root)
    live_sha = compute_source_sha(root)
    live_bucket_shas = compute_bucket_shas(root)

    if not force:
        cached_sha = get_cached_source_sha(root)
        if cached_sha == live_sha and cache_p.exists():
            return {
                "ok": True,
                "status": "in-sync",
                "source_sha": live_sha,
                "rows_written": 0,
                "scope": "repo",
            }

    # Decide full vs incremental. Incremental is viable iff the EXPENSIVE
    # ``code`` bucket is unchanged AND a cache with code nodes already exists.
    cached_bucket_shas = {} if force else get_cached_bucket_shas(root)
    code_unchanged = (
        not force
        and cached_bucket_shas
        and cached_bucket_shas.get("code") == live_bucket_shas.get("code")
    )

    graph = None
    status = "refreshed"
    if code_unchanged:
        graph = _assemble_incremental(root)
        if graph is not None:
            status = "incremental"
    if graph is None:
        # Full rebuild — canonical repo scope is the cache.
        graph = build_graph(root, scope="repo")
        status = "refreshed"

    # Cross-bucket SEMANTIC_NEIGHBOR reuse gate. The pair set is a pure
    # function of (embeddings, node-id-set); if that fingerprint is unchanged
    # from the persisted build we reuse the persisted semantic edges verbatim
    # and skip the ~60s O(N²) cosine. Computed AFTER assembly (the node-id set
    # is final; R3 adds edges only, never nodes) and BEFORE R3 injection.
    # ``force`` always recomputes (the canonical oracle path).
    sem_fp, reuse_semantic = _maybe_reuse_semantic(graph, root, force=force)
    _inject_r3_edges(graph, root, reuse_semantic=reuse_semantic)
    _persist_graph(cache_p, root, graph, live_sha, live_bucket_shas,
                   semantic_fingerprint=sem_fp)

    # Re-derive the portable artifacts (graph.json / graph.html / REPORT.md).
    from noctusai_lib.graph.serialize import (
        write_graph_html,
        write_graph_json,
        write_graph_report,
    )
    out_dir = root / ".noc-graph"
    write_graph_json(graph, out_dir)
    write_graph_html(graph, out_dir)
    write_graph_report(graph, out_dir)

    return {
        "ok": True,
        "status": status,
        "source_sha": live_sha,
        "rows_written": len(graph.nodes) + len(graph.edges),
        "scope": graph.meta.get("scope", "repo"),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "build_seconds": graph.meta.get("build_seconds"),
    }


def _load_cached_code_subgraph(repo_root: Path):
    """Load the persisted ``code`` bucket (nodes + their edges) from the cache.

    Returns ``(nodes, edges)`` of schema dataclasses with the history
    decoration (``ai_*`` meta) stripped from nodes, or ``None`` if the cache
    has no code nodes.

    The reused edges are exactly the set the code extractor emits:

      - every edge whose SOURCE is a ``code:`` node (IMPORTS / CALLS /
        INHERITS / consumes_component / EXPORTS / …), AND
      - the anchor→module ``CONTAINS`` edges (``product:<slug>`` /
        ``seed:noctusai_lib`` → ``code:…``) — these have a non-``code`` source
        but are emitted ONLY by the code walk, so they must travel with the
        reused code bucket or they orphan the modules under their anchor.

    Cross-bucket edges that merely TARGET code (kb DOCUMENTS source=``kb:``,
    history REFERENCED_BY_EVENT source=``ai:``) are owned by their source
    bucket and are re-emitted by the always-re-run knowledge / history passes —
    so they are NOT reused here (reusing them would risk a stale orphan when
    the owning doc stops referencing the code path).

    **R3-derived rows are NEVER reused.** ``_compute_guarded_by_edges``
    SYNTHESIZES ``code:…compliance.py::<keeper>`` KEEPER_RULE nodes (and their
    GUARDED_BY edges) into the graph; these get persisted with ``code:`` ids but
    are NOT code-bucket content — they are owned by the always-re-run R3 pass.
    Reloading them as "code" would (a) make the incremental node-set diverge
    from a full build pre-R3 (busting the semantic fingerprint) and (b) leak a
    stale keeper node if a keeper is later removed. So we exclude
    ``kind='keeper_rule'`` nodes and ``kind IN ('guarded_by','semantic_neighbor')``
    edges from the reused subgraph — R3 re-adds the live ones every rebuild.
    """
    from noctusai_lib.graph.schema import Edge, Node

    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return None
    conn = _connect(cache_p)
    try:
        node_rows = conn.execute(
            "SELECT id, label, kind, path, line, end_line, product, cluster, "
            "confidence, meta_json FROM noc_graph_nodes "
            "WHERE id LIKE 'code:%' AND kind != 'keeper_rule'"
        ).fetchall()
        if not node_rows:
            return None
        edge_rows = conn.execute(
            "SELECT source, target, kind, confidence, weight, meta_json "
            "FROM noc_graph_edges "
            "WHERE kind NOT IN ('guarded_by', 'semantic_neighbor') "
            "  AND (source LIKE 'code:%' "
            "       OR (kind = 'contains' AND target LIKE 'code:%' "
            "           AND (source LIKE 'product:%' OR source = 'seed:noctusai_lib')))"
        ).fetchall()
    finally:
        conn.close()

    nodes: list = []
    for r in node_rows:
        meta = json.loads(r["meta_json"]) if r["meta_json"] else {}
        for k in _HISTORY_DECORATION_KEYS:
            meta.pop(k, None)
        nodes.append(Node.from_dict({
            "id": r["id"], "label": r["label"], "kind": r["kind"],
            "path": r["path"], "line": r["line"], "end_line": r["end_line"],
            "product": r["product"],
            # cluster is recomputed in finalization — drop the stale value.
            "confidence": r["confidence"], "meta": meta,
        }))

    edges: list = []
    for r in edge_rows:
        meta = json.loads(r["meta_json"]) if r["meta_json"] else {}
        edges.append(Edge.from_dict({
            "source": r["source"], "target": r["target"], "kind": r["kind"],
            "confidence": r["confidence"], "weight": r["weight"], "meta": meta,
        }))
    return nodes, edges


def _assemble_incremental(repo_root: Path):
    """Assemble the graph reusing cached code nodes + re-running everything else.

    Mirrors the canonical ``build_graph(scope="repo")`` extractor ORDER, but
    seeds the code layer (L1) from the cache instead of walking the AST tree.
    The knowledge tier (L2) + finalization run identically to the full path, so
    the result is identical to a full rebuild for the same tree (proven by the
    parity test). Returns ``None`` (caller falls back to full) if the cached
    code subgraph is unavailable or the seed extractors can't be imported.
    """
    import time

    cached = _load_cached_code_subgraph(repo_root)
    if cached is None:
        return None
    code_nodes, code_edges = cached

    try:
        from noctusai_lib.graph.build import _cluster, _dedup, _discover_memory_root
        from noctusai_lib.graph.extract_cli import walk_cli
        from noctusai_lib.graph.extract_docs import walk_findings, walk_kb, walk_projects
        from noctusai_lib.graph.extract_harness import walk_harness
        from noctusai_lib.graph.extract_history import walk_auto_improvement
        from noctusai_lib.graph.extract_landscape import walk_kb_chapters, walk_landscape
        from noctusai_lib.graph.extract_memory import walk_memory
        from noctusai_lib.graph.extract_products import walk_products
        from noctusai_lib.graph.schema import Graph
    except ImportError as exc:
        logger.warning(
            "noc_graph_cache: incremental extractors unavailable (%s) — full rebuild",
            exc,
        )
        return None

    start = time.monotonic()
    graph = Graph(meta={"scope": "repo", "repo_root": str(repo_root)})

    # L0 anchors — products + seed (same as build_graph).
    landscape_candidates = [
        repo_root / "KNOWLEDGE-BASE" / "02-LANDSCAPE.md",
        repo_root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md",
    ]
    landscape = next((p for p in landscape_candidates if p.exists()), landscape_candidates[0])
    walk_products(graph, landscape)

    # L1 — code, reused from cache (THE skipped AST walk).
    for n in code_nodes:
        graph.add_node(n)
    for e in code_edges:
        graph.add_edge(e)

    # L2 — knowledge layers, re-run fresh against the reused code nodes (so the
    # presence-gated kb DOCUMENTS edges resolve against the identical node set).
    kb_root = repo_root / "KNOWLEDGE-BASE"
    walk_kb(graph, kb_root, repo_root=repo_root)
    walk_kb_chapters(graph, kb_root, repo_root=repo_root)
    walk_projects(graph, repo_root / "projects", repo_root=repo_root)
    for products_projects in (repo_root / "products").glob("*/projects"):
        walk_projects(graph, products_projects, repo_root=repo_root)
    walk_findings(graph, repo_root)
    memory_root = _discover_memory_root(repo_root)
    if memory_root is not None:
        walk_memory(graph, memory_root, repo_root=repo_root)
    walk_harness(graph, repo_root / ".claude", repo_root=repo_root)
    walk_landscape(graph, repo_root)
    cli_path = repo_root / "mcp" / "noctusai" / "cli.py"
    if cli_path.exists():
        walk_cli(graph, cli_path, repo_root=repo_root)
    ai_ndjson = repo_root / "project-history" / "auto-improvement.ndjson"
    if ai_ndjson.exists():
        walk_auto_improvement(graph, ai_ndjson)

    # Finalization — identical to build_graph's tail.
    _dedup(graph)
    _cluster(graph)
    graph.meta.update({
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "build_seconds": round(time.monotonic() - start, 3),
        "rebuild": "incremental",
    })
    logger.info(
        "noc_graph_cache: incremental rebuild — %d nodes, %d edges in %.2fs "
        "(code AST walk skipped)",
        len(graph.nodes), len(graph.edges), time.monotonic() - start,
    )
    return graph


def _maybe_reuse_semantic(graph, root: Path, force: bool) -> tuple[str | None, list | None]:
    """Decide whether the persisted SEMANTIC_NEIGHBOR edges can be reused.

    Returns ``(live_fingerprint, reuse_edges)``:

      - ``live_fingerprint`` — the freshly-computed fingerprint to stamp into
        meta on persist (``None`` if the fingerprint helper is unavailable, in
        which case we never reuse on the NEXT build either — safe).
      - ``reuse_edges`` — the persisted semantic ``Edge`` list to reuse, or
        ``None`` to force a full recompute.

    Reuse iff: not ``force`` AND the helper is importable AND the persisted
    fingerprint equals the live one AND persisted semantic edges are loadable.
    Any uncertainty falls back to recompute (correctness over speed).
    """
    if force:
        # Still compute the live fingerprint so the fresh recompute stamps it.
        try:
            from tools.noctus.graph.build import semantic_neighbor_fingerprint
            return semantic_neighbor_fingerprint(graph, root), None
        except Exception as exc:  # pragma: no cover - import/IO guard
            logger.debug("noc_graph_cache: semantic fingerprint unavailable (%s)", exc)
            return None, None
    try:
        from tools.noctus.graph.build import semantic_neighbor_fingerprint
        live_fp = semantic_neighbor_fingerprint(graph, root)
    except Exception as exc:  # pragma: no cover - import/IO guard
        logger.debug("noc_graph_cache: semantic fingerprint unavailable (%s)", exc)
        return None, None
    cached_fp = get_cached_semantic_fingerprint(root)
    if cached_fp is None or cached_fp != live_fp:
        return live_fp, None  # inputs changed → recompute.
    reuse = load_cached_semantic_edges(root)
    if reuse is None:
        return live_fp, None  # cache unreadable → recompute (safe).
    return live_fp, reuse


def _inject_r3_edges(graph, root: Path, reuse_semantic: list | None = None) -> None:
    """Inject the additive R3 edges (SEMANTIC_NEIGHBOR + GUARDED_BY).

    Identical for the full and incremental paths — a failure logs a warning
    and continues (purely additive). See the original inline note re: the
    seed-side-ingestor preferred path + the worktree-editable-install fallback.

    **Cross-bucket-edge reuse gate (the correctness-sensitive part).**
    SEMANTIC_NEIGHBOR pairs are a pure function of (embeddings, node-id-set) —
    see ``semantic_neighbor_fingerprint``. When ``reuse_semantic`` is provided
    (the caller verified the fingerprint is unchanged), the persisted semantic
    edges are re-added verbatim and the ~60s O(N²) cosine is SKIPPED. The pairs
    are identical by construction (same deterministic function, same inputs),
    so this satisfies the full-vs-incremental equivalence invariant. GUARDED_BY
    (sub-second) ALWAYS recomputes — never reused — because it resolves against
    the freshly-assembled keeper/graph state.

    ``reuse_semantic is None`` ⇒ recompute both (the canonical / safe fallback).
    """
    try:
        from tools.noctus.graph.build import (
            _compute_guarded_by_edges,
            _compute_semantic_neighbors,
        )
        if reuse_semantic is not None:
            # Fingerprint unchanged → reuse persisted semantic edges verbatim
            # (the O(N²) cosine is skipped). Filter to surviving node ids so a
            # reused edge can never dangle (defence-in-depth; the fingerprint
            # already pins the node-id set).
            node_ids = {n.id for n in graph.nodes}
            reused = 0
            for e in reuse_semantic:
                if e.source in node_ids and e.target in node_ids:
                    graph.add_edge(e)
                    reused += 1
            sem_pairs = []
            logger.info(
                "noc_graph_cache.refresh: SEMANTIC_NEIGHBOR reused %d cached edges "
                "(fingerprint unchanged — cosine skipped)", reused,
            )
        else:
            sem_pairs = _compute_semantic_neighbors(graph, root)
        gb_bindings = _compute_guarded_by_edges(graph, root)

        # Try seed-side ingestors first; fall back to inline edge injection.
        try:
            from noctusai_lib.graph.extract_mined import (
                ingest_guarded_by_edges,
                ingest_semantic_neighbors,
            )
            if sem_pairs:
                ingest_semantic_neighbors(graph, sem_pairs)
            if gb_bindings:
                ingest_guarded_by_edges(graph, gb_bindings)
        except ImportError:
            # Seed functions not yet visible (worktree isolation or pre-merge).
            from noctusai_lib.graph.schema import Edge, EdgeKind
            node_ids = {n.id for n in graph.nodes}
            sem_seen: set[tuple[str, str]] = set()
            for id_a, id_b, score in sem_pairs:
                if id_a > id_b:
                    id_a, id_b = id_b, id_a
                key = (id_a, id_b)
                if key in sem_seen:
                    continue
                sem_seen.add(key)
                if id_a in node_ids and id_b in node_ids:
                    for src, tgt in ((id_a, id_b), (id_b, id_a)):
                        graph.add_edge(Edge(
                            source=src, target=tgt,
                            kind=EdgeKind.SEMANTIC_NEIGHBOR,
                            confidence=min(score, 1.0),
                            weight=score,
                            meta=(("cosine", round(score, 4)),),
                        ))
            for guarded_id, keeper_id in gb_bindings:
                if guarded_id in node_ids and keeper_id in node_ids:
                    graph.add_edge(Edge(
                        source=guarded_id, target=keeper_id,
                        kind=EdgeKind.GUARDED_BY,
                        confidence=1.0, weight=1.0,
                        meta=(("source", "keeper-patterns-cache"),),
                    ))
        sem_count = sum(1 for e in graph.edges if e.kind.value == "semantic_neighbor")
        gb_count = sum(1 for e in graph.edges if e.kind.value == "guarded_by")
        logger.info(
            "noc_graph_cache.refresh: R3 edges — SEMANTIC_NEIGHBOR=%d, GUARDED_BY=%d",
            sem_count, gb_count,
        )
    except Exception as _r3_exc:
        logger.warning(
            "noc_graph_cache.refresh: R3 edge injection failed — %s", _r3_exc
        )


def _persist_graph(cache_p: Path, root: Path, graph, live_sha: str,
                   bucket_shas: dict[str, str],
                   semantic_fingerprint: str | None = None) -> None:
    """Mirror the assembled graph into SQLite (atomic full replace).

    Shared by the full + incremental paths — both write the SAME final graph,
    so persistence is a clean overwrite (no per-bucket DELETE/INSERT surgery in
    the table; the bucket-level skip happens upstream in assembly). This keeps
    the source-sha invariant + the 3-leg mirror contract intact.

    ``semantic_fingerprint`` is stamped into meta so the NEXT rebuild can decide
    whether the persisted SEMANTIC_NEIGHBOR edges are reusable (cosine skip).
    """
    conn = _connect(cache_p)
    try:
        conn.execute("DELETE FROM noc_graph_nodes")
        conn.execute("DELETE FROM noc_graph_edges")
        conn.execute("DELETE FROM noc_graph_files")

        node_rows = [_node_row(n) for n in graph.nodes]
        edge_rows = [_edge_row(e) for e in graph.edges]
        conn.executemany(
            "INSERT INTO noc_graph_nodes "
            "(id, label, kind, path, line, end_line, product, cluster, confidence, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            node_rows,
        )
        conn.executemany(
            "INSERT INTO noc_graph_edges "
            "(source, target, kind, confidence, weight, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            edge_rows,
        )

        # Per-file source_sha (legacy column; kept for portability).
        by_path: dict[str, list[str]] = {}
        for n in graph.nodes:
            if n.path:
                by_path.setdefault(n.path, []).append(n.id)
        file_rows = []
        ts = _now_iso()
        for rel, ids in by_path.items():
            abs_p = root / rel
            try:
                sha = hashlib.sha256(abs_p.read_bytes()).hexdigest()[:12]
            except OSError:
                continue
            file_rows.append((rel, sha, ts, json.dumps(ids)))
        if file_rows:
            conn.executemany(
                "INSERT INTO noc_graph_files (path, source_sha, cached_at, node_ids_json) "
                "VALUES (?, ?, ?, ?)",
                file_rows,
            )

        # Stamp meta — aggregate + per-bucket sub-shas (the incremental levers).
        meta_kv = {
            "aggregate_source_sha": live_sha,
            "last_refresh": ts,
            "node_count": str(len(graph.nodes)),
            "edge_count": str(len(graph.edges)),
            "scope": graph.meta.get("scope", "repo"),
            "build_seconds": str(graph.meta.get("build_seconds", "")),
            "clustering": str(graph.meta.get("clustering", "")),
            "rebuild": str(graph.meta.get("rebuild", "full")),
        }
        for bucket, sha in bucket_shas.items():
            meta_kv[f"bucket_sha:{bucket}"] = sha
        if semantic_fingerprint is not None:
            meta_kv["semantic_fingerprint"] = semantic_fingerprint
        conn.executemany(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
            meta_kv.items(),
        )
        conn.commit()
    finally:
        conn.close()


def _node_row(n) -> tuple:
    meta_json = json.dumps(dict(n.meta), sort_keys=True) if n.meta else None
    return (
        n.id, n.label, n.kind.value, n.path, n.line, n.end_line,
        n.product, n.cluster, n.confidence, meta_json,
    )


def _edge_row(e) -> tuple:
    meta_json = json.dumps(dict(e.meta), sort_keys=True) if e.meta else None
    return (e.source, e.target, e.kind.value, e.confidence, e.weight, meta_json)


# ── Lazy-on-read freshness gate ────────────────────────────────────────────

import threading

_rebuild_lock = threading.Lock()


def _ensure_fresh_on_read(repo_root: Optional[Path] = None) -> None:
    """Trigger a synchronous rebuild if the noc-graph cache is stale.

    Called at the entry of every graph READ path (noctus.graph.query,
    noctus.graph.neighbors, noctus.graph.explain, noctus.graph.path,
    noctus.graph.report, noctus.dev.noc_graph_status).

    Lazy-on-query semantics (KB § PATTERNS/common/cache-as-agent-tool.md +
    KB § PATTERNS/common/cache-auto-freshness.md): the cache is rebuilt ONLY
    when queried + stale, never eagerly on commit boundaries. This eliminates
    the ~5s pre-commit noc-graph pass that fired even when nobody was querying
    the graph — the staleness window is now closed at READ time, which is
    perfectly aligned with the cache-as-agent-tool consumption model.

    Concurrent-read safety: ``_rebuild_lock`` ensures only one thread
    triggers ``refresh()``; WAL mode lets the other readers continue against
    the stale data while the rebuild is in progress, then re-check after the
    lock is released.

    Fall-through on rebuild failure: if ``refresh()`` raises, a warning is
    logged and the stale cache is served rather than crashing the read path
    (the caller will surface what it has, which is better than an exception).
    """
    root = repo_root or REPO_ROOT
    live_sha = compute_source_sha(root)
    cached_sha = get_cached_source_sha(root)
    if cached_sha == live_sha and cache_path(root).exists():
        return  # Fresh — no-op.

    # Stale (or absent). Acquire the rebuild lock so that concurrent callers
    # don't all fan-out into a full graph rebuild simultaneously.
    with _rebuild_lock:
        # Re-check after acquiring the lock — another thread may have just
        # completed the rebuild while we were waiting.
        cached_sha = get_cached_source_sha(root)
        if cached_sha == live_sha and cache_path(root).exists():
            return
        try:
            logger.info("noc-graph cache stale, rebuilding...")
            refresh(force=True, repo_root=root)
        except Exception as exc:
            logger.warning(
                "noc-graph lazy rebuild failed — serving stale cache. Error: %s", exc
            )


# ── Read-side helpers (used by query / report tools) ───────────────────────


def load_summary(repo_root: Optional[Path] = None) -> dict[str, Any]:
    """One-shot summary the freshness keeper + /vector-status type display use."""
    _ensure_fresh_on_read(repo_root)
    cache_p = cache_path(repo_root)
    if not cache_p.exists():
        return {"present": False, "cache_path": str(cache_p)}
    conn = _connect(cache_p)
    try:
        nodes = conn.execute("SELECT COUNT(*) AS n FROM noc_graph_nodes").fetchone()["n"]
        edges = conn.execute("SELECT COUNT(*) AS n FROM noc_graph_edges").fetchone()["n"]
        meta_rows = conn.execute("SELECT key, value FROM cache_meta").fetchall()
        meta = {r["key"]: r["value"] for r in meta_rows}
        kind_rows = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM noc_graph_nodes GROUP BY kind ORDER BY n DESC"
        ).fetchall()
        edge_kind_rows = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM noc_graph_edges GROUP BY kind ORDER BY n DESC"
        ).fetchall()
        return {
            "present": True,
            "cache_path": str(cache_p),
            "nodes": nodes,
            "edges": edges,
            "meta": meta,
            "node_count_by_kind": {r["kind"]: r["n"] for r in kind_rows},
            "edge_count_by_kind": {r["kind"]: r["n"] for r in edge_kind_rows},
        }
    finally:
        conn.close()


# ── MCP registration ───────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.noc_graph_status",
        description=(
            "Show the noc-graph cache state — present? node/edge counts, "
            "kind breakdown, last refresh, aggregate source sha. Lightweight "
            "(SELECT COUNT only). Useful for /vector-status-style displays "
            "and for the freshness keeper. KB § PATTERNS/architect/noc-graph.md."
        ),
    )
    def _status() -> dict:
        return load_summary()


__all__ = [
    "cache_path",
    "compute_source_sha",
    "compute_bucket_shas",
    "get_cached_source_sha",
    "get_cached_bucket_shas",
    "get_cached_semantic_fingerprint",
    "load_cached_semantic_edges",
    "refresh",
    "load_summary",
    "register",
    "_ensure_fresh_on_read",
]

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
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

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
    return (repo_root or REPO_ROOT) / ".claude" / "cache" / "noc-graph.sqlite"


def _connect(cache_p: Path) -> sqlite3.Connection:
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_p))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
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


def refresh(force: bool = False, repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Rebuild the graph + mirror it into the SQLite cache.

    Per-source-file sha guards the FULL rebuild: when the aggregate sha
    matches the cached value AND `force=False`, the rebuild is skipped.

    Returns ``{ok, status, nodes, edges, rows_written, scope, build_seconds,
    source_sha}``.
    """
    from noctusai_lib.graph import build_graph
    from noctusai_lib.graph.serialize import write_graph_html, write_graph_json, write_graph_report

    root = repo_root or REPO_ROOT
    cache_p = cache_path(root)
    live_sha = compute_source_sha(root)

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

    # Rebuild — full repo scope is the canonical cache.
    graph = build_graph(root, scope="repo")

    # Persist to SQLite (atomic replace).
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

        # Per-file source_sha for incremental rebuilds.
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

        # Stamp meta.
        meta_kv = {
            "aggregate_source_sha": live_sha,
            "last_refresh": ts,
            "node_count": str(len(graph.nodes)),
            "edge_count": str(len(graph.edges)),
            "scope": graph.meta.get("scope", "repo"),
            "build_seconds": str(graph.meta.get("build_seconds", "")),
            "clustering": str(graph.meta.get("clustering", "")),
        }
        conn.executemany(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
            meta_kv.items(),
        )
        conn.commit()
    finally:
        conn.close()

    # Re-derive the portable artifacts (graph.json / graph.html / REPORT.md).
    out_dir = root / ".noc-graph"
    write_graph_json(graph, out_dir)
    write_graph_html(graph, out_dir)
    write_graph_report(graph, out_dir)

    return {
        "ok": True,
        "status": "refreshed",
        "source_sha": live_sha,
        "rows_written": len(graph.nodes) + len(graph.edges),
        "scope": graph.meta.get("scope", "repo"),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "build_seconds": graph.meta.get("build_seconds"),
    }


def _node_row(n) -> tuple:
    meta_json = json.dumps(dict(n.meta), sort_keys=True) if n.meta else None
    return (
        n.id, n.label, n.kind.value, n.path, n.line, n.end_line,
        n.product, n.cluster, n.confidence, meta_json,
    )


def _edge_row(e) -> tuple:
    meta_json = json.dumps(dict(e.meta), sort_keys=True) if e.meta else None
    return (e.source, e.target, e.kind.value, e.confidence, e.weight, meta_json)


# ── Read-side helpers (used by query / report tools) ───────────────────────


def load_summary(repo_root: Optional[Path] = None) -> dict[str, Any]:
    """One-shot summary the freshness keeper + /vector-status type display use."""
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
    "get_cached_source_sha",
    "refresh",
    "load_summary",
    "register",
]

"""Local SQLite cache of keeper validation patterns — the keeper-mirror.

Why this exists
    `mcp/noctusai/tools/noctus/dev/compliance.py` is ~8000 lines + ~60 `check_*`
    keepers + name-bound contracts (`_HARNESS_*_AGENTS` frozensets, etc.) + a
    matching ~95 test files whose fixtures carry the canonical patterns.
    A doc-authoring agent that doesn't *know* a keeper's contract authors a
    drift-prone doc → gets gated → reworks. The cure is a fast local cache
    the agent queries BEFORE authoring (the keeper-check-before-doc'ing
    discipline — `KB § PATTERNS/keeper-check-before-docing.md`).

Mirror contract (user mandate 2026-05-25)
    The cache IS a mirror of the live keepers. Modifying `compliance.py` MUST
    cause a refresh — enforced by `check_keeper_cache_freshness` (Stage-4
    keeper, severity high) + an eager refresh in `scripts/hooks/pre-commit`
    on `compliance.py` change + a lazy query-time `source_sha` mismatch
    rebuild (belt-and-suspenders). The cache file at
    `.claude/cache/keeper-patterns.sqlite` is gitignored (derived; mole
    tradition — fs-derived artifacts not tracked).

Schema (one SQLite file; permanent + session lanes via the `scope` column)
    keeper_patterns(keeper_name, pattern_kind, pattern_value, severity,
                    remediation, source_file, source_line, fixture_example,
                    scope, cached_at)
    cache_meta(key, value)                       # 'source_sha', 'populated_at'
    Indexes on keeper_name + scope.

Depth · `KB § PATTERNS/keeper-pattern-cache.md` (architecture + usage) ·
       `KB § PATTERNS/keeper-check-before-docing.md` (the discipline) ·
       `KB § PATTERNS/persistent-files-absorption.md` (sibling rule —
       persistent project/worktree files must be absorbed to KB/memory
       before teardown).
"""
from __future__ import annotations

import ast
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

# ── Paths ────────────────────────────────────────────────────────────────────
from .cache_backend import (
    apply_locking_pragmas,
    cache_dir as _cache_dir,
    cache_path as _cache_path,
)

CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("keeper-patterns")
COMPLIANCE_SRC = (
    REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
)
TESTS_DIR = REPO_ROOT / "mcp" / "noctusai" / "tests"
SESSION_TTL_HOURS = 24

# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compliance_src_for(worktree_path: str | None) -> Path:
    """Resolve the `compliance.py` SOURCE to hash/parse for this call. `None`
    (the default) preserves the pre-existing module-level `COMPLIANCE_SRC` —
    the primary tree, and what tests monkeypatch. An explicit `worktree_path`
    resolves the CALLER's own worktree copy instead — MCP stdio is a
    fixed-CWD process bound to the primary at startup, so omitting
    `worktree_path` from inside an engineer worktree silently mirrors the
    STALE primary `compliance.py`, never the worktree's own in-flight edits.
    Mirrors the `_ledger_path_for` convention in `auto_improvement.py`."""
    if worktree_path:
        return (
            resolve_caller_root(worktree_path)
            / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        )
    return COMPLIANCE_SRC


def _tests_dir_for(worktree_path: str | None) -> Path:
    """Sibling of `_compliance_src_for` for the colocated fixture tests dir."""
    if worktree_path:
        return resolve_caller_root(worktree_path) / "mcp" / "noctusai" / "tests"
    return TESTS_DIR


def _source_sha(worktree_path: str | None = None) -> str:
    """SHA-256 of `compliance.py` — the single source of truth for keeper patterns."""
    src = _compliance_src_for(worktree_path)
    if not src.exists():
        return ""
    return hashlib.sha256(src.read_bytes()).hexdigest()


def _cache_file(worktree_path: str | None) -> Path:
    """The cache slot mirroring `worktree_path`'s compliance.py (default: this
    process's tree). keeper-patterns is a per-tree cache
    (`cache_backend._PER_TREE_CACHES`) — one aggregate sha, so the slot must
    belong to the tree that was hashed."""
    if worktree_path:
        return _cache_path("keeper-patterns", resolve_caller_root(worktree_path))
    return CACHE_PATH


def _connect(worktree_path: str | None = None) -> sqlite3.Connection:
    path = _cache_file(worktree_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # WAL + busy_timeout — uniform locking discipline across keeper-mirror caches.
    apply_locking_pragmas(conn)
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS keeper_patterns (
  keeper_name      TEXT NOT NULL,
  pattern_kind     TEXT NOT NULL,
  pattern_value    TEXT NOT NULL,
  severity         TEXT,
  remediation      TEXT,
  source_file      TEXT NOT NULL,
  source_line      INTEGER,
  fixture_example  TEXT,
  scope            TEXT NOT NULL DEFAULT 'permanent',
  cached_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_keeper_name ON keeper_patterns(keeper_name);
CREATE INDEX IF NOT EXISTS idx_scope ON keeper_patterns(scope);
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


# ── Extractors (AST-first per CLAUDE.md §1 — Python source is parsed code) ───
# Three extractors, all `ast.walk`. Earlier regex versions were the AST-first
# slip the docs warn about — the fixture regex over-matched gaps BETWEEN string
# literals (proven by a build-time test failure 2026-05-26). Regex purged.


def _parse(path: Path) -> ast.Module | None:
    if not path.exists():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _extract_keepers_from_compliance(worktree_path: str | None = None) -> list[dict]:
    """AST-walk for `def check_*(...)` function defs + docstring 1st-line."""
    src = _compliance_src_for(worktree_path)
    tree = _parse(src)
    if tree is None:
        return []
    root = resolve_caller_root(worktree_path) if worktree_path else REPO_ROOT
    rel = str(src.relative_to(root))
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("check_"):
            continue
        doc = ast.get_docstring(node) or ""
        first = doc.strip().split("\n", 1)[0] if doc else ""
        out.append(
            {
                "keeper_name": node.name,
                "pattern_kind": "contract-clause",
                "pattern_value": (first[:300] or node.name),
                "severity": None,
                "remediation": None,
                "source_file": rel,
                "source_line": node.lineno,
                "fixture_example": None,
            }
        )
    return out


def _extract_set_membership(worktree_path: str | None = None) -> list[dict]:
    """AST-walk for `_HARNESS_*_AGENTS = frozenset({...})` assignments — pulls
    set members as `Constant(str)` elements."""
    src = _compliance_src_for(worktree_path)
    tree = _parse(src)
    if tree is None:
        return []
    root = resolve_caller_root(worktree_path) if worktree_path else REPO_ROOT
    rel = str(src.relative_to(root))
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        const_name = node.targets[0].id
        if not (
            const_name.startswith("_HARNESS_") and const_name.endswith("_AGENTS")
        ):
            continue
        v = node.value
        if not (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id == "frozenset"
            and len(v.args) == 1
            and isinstance(v.args[0], ast.Set)
        ):
            continue
        members = [
            elt.value
            for elt in v.args[0].elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
        out.append(
            {
                "keeper_name": (
                    f"check_agent_archetype_contract::{const_name}"
                ),
                "pattern_kind": "set-membership",
                "pattern_value": ",".join(members),
                "severity": "high",
                "remediation": (
                    f"Add the agent stem to {const_name} when porting a new "
                    f"agent of this archetype (see .claude/agents/ for current files)."
                ),
                "source_file": rel,
                "source_line": node.lineno,
                "fixture_example": None,
            }
        )
    return out


def _extract_fixtures_from_tests(worktree_path: str | None = None) -> list[dict]:
    """AST-walk each test file: find the `from tools.noctus.dev.compliance
    import check_X` statement (binds the test to its keeper), then find
    frontmatter-shaped `Constant(str)` literals."""
    out: list[dict] = []
    tests_dir = _tests_dir_for(worktree_path)
    root = resolve_caller_root(worktree_path) if worktree_path else REPO_ROOT
    if not tests_dir.exists():
        return out
    for tf in sorted(tests_dir.glob("test_*.py")):
        tree = _parse(tf)
        if tree is None:
            continue
        keeper: str | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "tools.noctus.dev.compliance"
            ):
                for alias in node.names:
                    if alias.name.startswith("check_"):
                        keeper = alias.name
                        break
                if keeper:
                    break
        if not keeper:
            continue
        rel = str(tf.relative_to(root))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Constant) and isinstance(node.value, str)
            ):
                continue
            literal = node.value
            if len(literal) < 10:
                continue
            if not (
                "---" in literal
                or "name:" in literal
                or "tools:" in literal
                or "description:" in literal
            ):
                continue
            out.append(
                {
                    "keeper_name": keeper,
                    "pattern_kind": "fixture-example",
                    "pattern_value": literal[:500],
                    "severity": None,
                    "remediation": None,
                    "source_file": rel,
                    "source_line": getattr(node, "lineno", 0),
                    "fixture_example": literal[:1200],
                }
            )
    return out


# ── Public API ───────────────────────────────────────────────────────────────
def refresh(force: bool = False, worktree_path: str | None = None) -> dict:
    """Re-populate permanent rows from `compliance.py` + tests. Idempotent.

    `worktree_path`: read the SOURCE `compliance.py` + tests from the
    CALLER's own worktree instead of the primary tree. MCP stdio is a
    fixed-CWD process bound to the primary at startup, so omitting
    `worktree_path` from inside an engineer worktree silently mirrors the
    STALE primary `compliance.py` rather than the worktree's own in-flight
    edits. The cache written is that SAME tree's per-tree slot
    (`<git-dir>/noctusai/cache/keeper-patterns.sqlite`), so hashing one tree
    never flips another tree's freshness.

    Returns a status dict: ``{ok, status('in-sync'|'rebuilt'), source_sha,
    rows_written, resolved_compliance_src}``. ``force=True`` bypasses the
    in-sync short-circuit.
    """
    sha_now = _source_sha(worktree_path)
    conn = _connect(worktree_path)
    _init_schema(conn)
    if not force:
        cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
        row = cur.fetchone()
        if row and row["value"] == sha_now:
            conn.close()
            return {
                "ok": True,
                "status": "in-sync",
                "source_sha": sha_now,
                "rows_written": 0,
                "resolved_compliance_src": str(_compliance_src_for(worktree_path)),
            }
    conn.execute("DELETE FROM keeper_patterns WHERE scope='permanent'")
    rows = (
        _extract_keepers_from_compliance(worktree_path)
        + _extract_set_membership(worktree_path)
        + _extract_fixtures_from_tests(worktree_path)
    )
    now = _now_iso()
    conn.executemany(
        "INSERT INTO keeper_patterns(keeper_name,pattern_kind,pattern_value,"
        "severity,remediation,source_file,source_line,fixture_example,scope,cached_at) "
        "VALUES (?,?,?,?,?,?,?,?,'permanent',?)",
        [
            (
                r["keeper_name"],
                r["pattern_kind"],
                r["pattern_value"],
                r["severity"],
                r["remediation"],
                r["source_file"],
                r["source_line"],
                r["fixture_example"],
                now,
            )
            for r in rows
        ],
    )
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("source_sha", sha_now),
    )
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", now),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "status": "rebuilt",
        "source_sha": sha_now,
        "rows_written": len(rows),
        "resolved_compliance_src": str(_compliance_src_for(worktree_path)),
    }


def _path_to_keeper_hint(file_path: str) -> list[str]:
    """File-path → likely-keeper-name fragments (extensible)."""
    p = file_path.lower()
    hints: list[str] = []
    if "claude.md" in p or "/claude/" in p:
        hints += ["claude_md_router", "doc_symbology"]
    if "memory.md" in p or "/memory/" in p:
        hints += ["memory_md_index"]
    if ".claude/agents/" in p or "/agents/" in p:
        hints += ["agent_format", "agent_archetype"]
    if ".claude/skills/" in p or "/skills/" in p:
        hints += ["skill_format"]
    if "knowledge-base/" in p or "/kb/" in p:
        hints += ["kb_sync", "doc_symbology", "methodology_reference"]
    return hints


def lookup(
    keeper_name: str | None = None, file_path: str | None = None
) -> list[dict]:
    """Query the cache. Filters optional; ``file_path`` heuristic-maps to keepers.

    Lazy freshness leg: if the cached ``source_sha`` differs from the live
    ``compliance.py`` hash, the cache is rebuilt before answering — so a
    stale cache self-heals on use (the keeper still fails loudly so the
    drift is visible, not papered over).
    """
    sha_now = _source_sha()
    if not CACHE_PATH.exists():
        refresh()
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
    row = cur.fetchone()
    if not row or row["value"] != sha_now:
        conn.close()
        refresh()
        conn = _connect()
        _init_schema(conn)
    sql = "SELECT * FROM keeper_patterns WHERE scope='permanent'"
    params: list = []
    clauses: list[str] = []
    if keeper_name:
        clauses.append("keeper_name LIKE ?")
        params.append(f"%{keeper_name}%")
    if file_path:
        hint = _path_to_keeper_hint(file_path)
        if hint:
            clauses.append(
                "(" + " OR ".join(["keeper_name LIKE ?"] * len(hint)) + ")"
            )
            params.extend([f"%{h}%" for h in hint])
    if clauses:
        sql += " AND " + " AND ".join(clauses)
    sql += " ORDER BY keeper_name, source_line"
    cur = conn.execute(sql, params)
    out = [dict(r) for r in cur.fetchall()]
    conn.close()
    return out


def list_keepers() -> list[str]:
    """Distinct keeper_names in the cache (permanent rows)."""
    if not CACHE_PATH.exists():
        refresh()
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute(
        "SELECT DISTINCT keeper_name FROM keeper_patterns "
        "WHERE scope='permanent' ORDER BY keeper_name"
    )
    out = [r["keeper_name"] for r in cur.fetchall()]
    conn.close()
    return out


# ── Session lane (temporary cache; for dev/research use) ─────────────────────
def session_set(scope_id: str, key: str, value: str) -> None:
    """Write a temporary row tagged ``scope='session-<scope_id>'``."""
    conn = _connect()
    _init_schema(conn)
    conn.execute(
        "INSERT INTO keeper_patterns(keeper_name,pattern_kind,pattern_value,"
        "source_file,scope,cached_at) VALUES (?,?,?,?,?,?)",
        (key, "session-data", value, "(session)", f"session-{scope_id}", _now_iso()),
    )
    conn.commit()
    conn.close()


def session_get(scope_id: str, key: str | None = None) -> list[dict]:
    """Read temporary rows for a session_id."""
    conn = _connect()
    _init_schema(conn)
    if key:
        cur = conn.execute(
            "SELECT * FROM keeper_patterns WHERE scope=? AND keeper_name=? "
            "ORDER BY cached_at DESC",
            (f"session-{scope_id}", key),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM keeper_patterns WHERE scope=? ORDER BY cached_at DESC",
            (f"session-{scope_id}",),
        )
    out = [dict(r) for r in cur.fetchall()]
    conn.close()
    return out


def sweep_session(ttl_hours: int = SESSION_TTL_HOURS) -> int:
    """Drop session rows older than ``ttl_hours``. Returns rows removed."""
    cutoff_ts = datetime.now(timezone.utc).timestamp() - ttl_hours * 3600
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute(
        "DELETE FROM keeper_patterns WHERE scope LIKE 'session-%' "
        "AND CAST(strftime('%s', cached_at) AS INTEGER) < ?",
        (int(cutoff_ts),),
    )
    removed = cur.rowcount
    conn.commit()
    conn.close()
    return removed

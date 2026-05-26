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
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "keeper-patterns.sqlite"
COMPLIANCE_SRC = (
    REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
)
TESTS_DIR = REPO_ROOT / "mcp" / "noctusai" / "tests"
SESSION_TTL_HOURS = 24

# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sha() -> str:
    """SHA-256 of `compliance.py` — the single source of truth for keeper patterns."""
    if not COMPLIANCE_SRC.exists():
        return ""
    return hashlib.sha256(COMPLIANCE_SRC.read_bytes()).hexdigest()


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
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


# ── Extractors (tests-first; AST cross-validates from compliance.py) ─────────
_CHECK_DEF_RE = re.compile(r"^def\s+(check_[a-z_]+)\s*\(", re.MULTILINE)
_FROZENSET_RE = re.compile(
    r"^(_HARNESS_[A-Z_]+)\s*=\s*frozenset\(\{([^}]+)\}\)", re.MULTILINE
)
_TEST_IMPORT_RE = re.compile(
    r"from tools\.noctus\.dev\.compliance import\s+(check_[a-z_]+)"
)


def _extract_keepers_from_compliance() -> list[dict]:
    """`def check_*(...)` symbols + their docstring first-line as contract-clause."""
    if not COMPLIANCE_SRC.exists():
        return []
    src = COMPLIANCE_SRC.read_text(encoding="utf-8")
    out: list[dict] = []
    rel = str(COMPLIANCE_SRC.relative_to(REPO_ROOT))
    for m in _CHECK_DEF_RE.finditer(src):
        name = m.group(1)
        line = src.count("\n", 0, m.start()) + 1
        body_window = src[m.end() : m.end() + 1500]
        doc_m = re.search(r'"""(.+?)"""', body_window, re.DOTALL)
        doc = doc_m.group(1).strip().split("\n")[0] if doc_m else ""
        out.append(
            {
                "keeper_name": name,
                "pattern_kind": "contract-clause",
                "pattern_value": (doc[:300] or name),
                "severity": None,
                "remediation": None,
                "source_file": rel,
                "source_line": line,
                "fixture_example": None,
            }
        )
    return out


def _extract_set_membership() -> list[dict]:
    """`_HARNESS_*_AGENTS = frozenset({...})` constants — set-membership contracts."""
    if not COMPLIANCE_SRC.exists():
        return []
    src = COMPLIANCE_SRC.read_text(encoding="utf-8")
    out: list[dict] = []
    rel = str(COMPLIANCE_SRC.relative_to(REPO_ROOT))
    for m in _FROZENSET_RE.finditer(src):
        const = m.group(1)
        members = re.findall(r'"([^"]+)"', m.group(2))
        line = src.count("\n", 0, m.start()) + 1
        out.append(
            {
                "keeper_name": f"check_agent_archetype_contract::{const}",
                "pattern_kind": "set-membership",
                "pattern_value": ",".join(members),
                "severity": "high",
                "remediation": (
                    f"Add the agent stem to {const} when porting a new agent of "
                    f"this archetype (see .claude/agents/ for current files)."
                ),
                "source_file": rel,
                "source_line": line,
                "fixture_example": None,
            }
        )
    return out


def _extract_fixtures_from_tests() -> list[dict]:
    """Test fixtures often carry the canonical *pattern* explicitly. Walk the AST
    (AST-first per CLAUDE.md §1) to find real `str` constants — a naive
    `"..."` regex matches gaps BETWEEN string literals (code text) too."""
    out: list[dict] = []
    if not TESTS_DIR.exists():
        return out
    for tf in sorted(TESTS_DIR.glob("test_*.py")):
        text = tf.read_text(encoding="utf-8")
        m = _TEST_IMPORT_RE.search(text)
        if not m:
            continue
        keeper = m.group(1)
        rel = str(tf.relative_to(REPO_ROOT))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
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
def refresh(force: bool = False) -> dict:
    """Re-populate permanent rows from `compliance.py` + tests. Idempotent.

    Returns a status dict: ``{ok, status('in-sync'|'rebuilt'), source_sha,
    rows_written}``. ``force=True`` bypasses the in-sync short-circuit.
    """
    sha_now = _source_sha()
    conn = _connect()
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
            }
    conn.execute("DELETE FROM keeper_patterns WHERE scope='permanent'")
    rows = (
        _extract_keepers_from_compliance()
        + _extract_set_membership()
        + _extract_fixtures_from_tests()
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

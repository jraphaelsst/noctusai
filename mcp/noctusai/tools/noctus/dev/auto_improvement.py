"""Local SQLite cache of scoped-auto-improvement findings — third-in-family
keeper-mirror (after keeper_pattern_cache + agent_context_cache).

Why this exists
    Every dispatch is a scoped auto-improvement pass — engineers surface
    slip/drift observations to the tech-lead, who codifies via the
    pipeline (memory → KB → keeper). Without a durable, queryable store
    the findings live only in chat text and get lost between sessions.
    Per the user mandate (2026-05-26 Phase B): *"the improvement should
    be made following the pattern of the wiring the agents pointer
    system has — a keeper drift detector pattern, and it should be
    cached for consultation in cached memory not the actual file for
    patterns before editing docs/agents."*

Source of truth (durable, committed)
    `project-history/auto-improvement.ndjson` — one JSON object per
    line. Schema:
      ts          ISO-8601 UTC timestamp
      agent       who surfaced (engineer name | 'tech-lead' | 'architect' …)
      scope       'scoped' (engineer-slice) | 'broad' (tech-lead cross-cutting)
      kind        'drift' | 'improvement'
      target      doc/file/agent path the surface is ABOUT (e.g.
                  '.claude/agents/backend-engineer.md', 'KB § PATTERNS/x.md',
                  'mcp/noctusai/...py'; '*' = cross-cutting / not file-specific)
      description verbatim engineer surface text
      status      's1-emergent' (just surfaced) | 's2-memory' (in memory)
                  | 's3-kb' (in KB) | 's4-keeper' (keeper exists) | 'closed'
      source_ref  commit SHA / session ID / project slug — optional provenance

Cache (gitignored, derived — `.claude/cache/auto-improvement.sqlite`)
    Mirror of the ndjson. Per-source-sha guard. The cache is what gets
    queried before editing a doc/agent (the **consult-before-editing**
    discipline — sibling of keeper-check-before-doc'ing).

Mirror contract (3 legs — same shape as the family)
    (a) Eager pre-commit refresh when the ndjson is staged.
    (b) Lazy query-time source_sha mismatch rebuild.
    (c) `check_auto_improvement_cache_freshness` keeper (severity high).

KB § PATTERNS/scoped-auto-improvement.md.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT


# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = REPO_ROOT / ".claude" / "cache"
CACHE_PATH = CACHE_DIR / "auto-improvement.sqlite"
LEDGER_PATH = REPO_ROOT / "project-history" / "auto-improvement.ndjson"

# Allowed enums (defensive; loud-fail on unknown values so typos don't grow stalely).
SCOPES = frozenset({"scoped", "broad"})
KINDS = frozenset({"drift", "improvement"})
STATUSES = frozenset({"s1-emergent", "s2-memory", "s3-kb", "s4-keeper", "closed"})


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sha() -> str:
    if not LEDGER_PATH.exists():
        return ""
    return hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS auto_improvement (
  rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  agent       TEXT,
  scope       TEXT NOT NULL,
  kind        TEXT NOT NULL,
  target      TEXT NOT NULL,
  description TEXT NOT NULL,
  status      TEXT NOT NULL,
  source_ref  TEXT,
  cached_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auto_target ON auto_improvement(target);
CREATE INDEX IF NOT EXISTS idx_auto_status ON auto_improvement(status);
CREATE INDEX IF NOT EXISTS idx_auto_kind ON auto_improvement(kind);
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def _validate(scope: str, kind: str, status: str) -> dict | None:
    if scope not in SCOPES:
        return {"ok": False, "error": f"scope must be one of {sorted(SCOPES)}; got {scope!r}"}
    if kind not in KINDS:
        return {"ok": False, "error": f"kind must be one of {sorted(KINDS)}; got {kind!r}"}
    if status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {sorted(STATUSES)}; got {status!r}"}
    return None


# ── Public API: log (append to ndjson + refresh cache for that entry) ────────
def log_entry(
    *,
    scope: str,
    kind: str,
    target: str,
    description: str,
    agent: str | None = None,
    status: str = "s1-emergent",
    source_ref: str | None = None,
) -> dict:
    """Append one entry to the ndjson + invalidate the cache.

    Returns `{ok, entry, ledger_path}` on success, `{ok: False, error}` on
    invalid enum value. The tech-lead's typical call after an engineer
    surface; can also be called directly when the tech-lead observes
    something themselves.
    """
    err = _validate(scope, kind, status)
    if err is not None:
        return err
    entry = {
        "ts": _now_iso(),
        "agent": agent,
        "scope": scope,
        "kind": kind,
        "target": target,
        "description": description,
        "status": status,
        "source_ref": source_ref,
    }
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # Lazy: next query() call will detect source_sha mismatch and rebuild.
    # `relative_to` may fail when tests monkeypatch LEDGER_PATH out of REPO_ROOT;
    # fall back to the absolute path so the return shape stays stable.
    try:
        ledger_path = str(LEDGER_PATH.relative_to(REPO_ROOT))
    except ValueError:
        ledger_path = str(LEDGER_PATH)
    return {"ok": True, "entry": entry, "ledger_path": ledger_path}


def refresh(force: bool = False) -> dict:
    """Re-populate the cache from the ndjson. Idempotent (source_sha guard)."""
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
    conn.execute("DELETE FROM auto_improvement")
    rows: list[tuple] = []
    if LEDGER_PATH.exists():
        now = _now_iso()
        for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip malformed lines; the keeper surfaces them separately
            rows.append((
                e.get("ts", ""),
                e.get("agent"),
                e.get("scope", ""),
                e.get("kind", ""),
                e.get("target", ""),
                e.get("description", ""),
                e.get("status", ""),
                e.get("source_ref"),
                now,
            ))
    if rows:
        conn.executemany(
            "INSERT INTO auto_improvement(ts,agent,scope,kind,target,description,status,source_ref,cached_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("source_sha", sha_now),
    )
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", _now_iso()),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "status": "rebuilt",
        "source_sha": sha_now,
        "rows_written": len(rows),
    }


def query(
    *,
    target: str | None = None,
    agent: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    open_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Consult the cache before editing a doc/agent.

    `target` accepts an exact path OR a substring (e.g.
    `.claude/agents/backend-engineer.md` for agent-specific surfaces,
    `KB § PATTERNS/` for all KB-pattern surfaces). `open_only=True`
    excludes `status='closed'`. Lazy rebuild on source_sha mismatch.
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
    sql = "SELECT * FROM auto_improvement WHERE 1=1"
    params: list = []
    if target:
        sql += " AND target LIKE ?"
        params.append(f"%{target}%")
    if agent:
        sql += " AND agent = ?"
        params.append(agent)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if open_only:
        sql += " AND status != 'closed'"
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(sql, params)
    out = [dict(r) for r in cur.fetchall()]
    conn.close()
    return out


def list_targets() -> list[str]:
    """Distinct targets seen in the cache (rebuilds if missing)."""
    if not CACHE_PATH.exists():
        refresh()
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute(
        "SELECT DISTINCT target FROM auto_improvement ORDER BY target"
    )
    out = [r["target"] for r in cur.fetchall()]
    conn.close()
    return out


# ── MCP registration (3 tools) ───────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.auto_improvement_log",
        description=(
            "Append a scoped-auto-improvement entry to the durable ledger "
            "(`project-history/auto-improvement.ndjson`). `scope` ∈ "
            "{'scoped','broad'} · `kind` ∈ {'drift','improvement'} · "
            "`status` ∈ {'s1-emergent','s2-memory','s3-kb','s4-keeper','closed'}. "
            "`target` is the doc/agent/file the surface is ABOUT (path or "
            "'*' for cross-cutting). The tech-lead's typical call after "
            "reading an engineer's `drift-found:` / `scoped-improvement:` "
            "footer; can also be called directly by the tech-lead. "
            "KB § PATTERNS/scoped-auto-improvement.md."
        ),
    )
    def _log(
        scope: str,
        kind: str,
        target: str,
        description: str,
        agent: str | None = None,
        status: str = "s1-emergent",
        source_ref: str | None = None,
    ) -> dict:
        return log_entry(
            scope=scope, kind=kind, target=target, description=description,
            agent=agent, status=status, source_ref=source_ref,
        )

    @server.tool(
        name="noctus.dev.auto_improvement_query",
        description=(
            "Consult the auto-improvement cache before editing a doc/agent. "
            "Filter by target (path substring), agent, kind, status, or "
            "open_only=True (excludes 'closed'). Returns most-recent-first. "
            "The **consult-before-editing** discipline — sibling of "
            "keeper-check-before-doc'ing. Lazy-rebuilds on source_sha "
            "mismatch (the cache self-heals on use)."
        ),
    )
    def _query(
        target: str | None = None,
        agent: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        return query(
            target=target, agent=agent, kind=kind, status=status,
            open_only=open_only, limit=limit,
        )

    @server.tool(
        name="noctus.dev.auto_improvement_refresh",
        description=(
            "Re-populate the auto-improvement cache from the ndjson. "
            "Idempotent — source_sha guard short-circuits when in-sync; "
            "force=True rebuilds anyway. Auto-run by pre-commit on "
            "`project-history/auto-improvement.ndjson` change."
        ),
    )
    def _refresh(force: bool = False) -> dict:
        return refresh(force=force)


__all__ = [
    "CACHE_PATH",
    "LEDGER_PATH",
    "SCOPES",
    "KINDS",
    "STATUSES",
    "log_entry",
    "refresh",
    "query",
    "list_targets",
    "register",
]

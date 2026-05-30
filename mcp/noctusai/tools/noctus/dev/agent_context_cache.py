"""Local SQLite cache of agent-context bundles — sibling of keeper_pattern_cache.

Why this exists
    Subagent dispatch is expensive — every Agent invocation re-loads the
    agent's `.md` body + (if it Reads them) every owned KB doc. The
    agent-context architecture (KB § PATTERNS/agent-context-architecture.md)
    declares a lean L1 INDEX (rule + → pointer) + KB depth at the pointers
    + this cache holding the COMPACT EXTRACT of agent body + owned KB. At
    dispatch, query `noctus.dev.agent_context(agent="backend-engineer")`
    and get a single round-trip bundle instead of N Read calls.

Mirror contract (Phase B 2026-05-26)
    The cache IS a mirror of:
      - each `.claude/agents/<name>.md` (frontmatter + body)
      - every path in that agent's `owns_kb:` declaration (compact extract)
    Per-agent `bundle_sha = sha256(agent.md ∪ each owned_kb)`. If ANY of
    those source files changes, the bundle_sha differs and the cache
    rebuilds for that agent. Enforced by three legs (mirroring the
    keeper-pattern-cache):
      (a) Eager pre-commit refresh when `.claude/agents/*.md` OR an
          owned-KB path is staged.
      (b) Lazy query-time bundle_sha mismatch rebuild (self-heals on use).
      (c) `check_agent_context_cache_freshness` keeper (severity high) —
          loud gate that surfaces stale caches at `validate`.

Schema (one SQLite file, gitignored at `.claude/cache/agent-context.sqlite`)
    agent_context(agent_name, section_kind, section_path, section_value,
                  source_sha, cached_at)
        section_kind ∈ {'frontmatter', 'body', 'owned-kb-extract'}
        section_path = the KB path for owned-kb-extract rows; NULL otherwise
    cache_meta(key, value)
        keys: 'bundle_sha:<agent_name>' + 'populated_at'
    Indexes on agent_name + section_kind.

Compact-extract heuristic (per owned KB doc, AST-friendly markdown walk):
    - First H1 (the title)
    - First non-empty paragraph after the title (the hook)
    - Each subsequent H2 + its first non-empty line (the section index)
    Typical output ~20-50 lines per doc — enough to know what the doc
    covers + decide if a full Read is warranted, never the full body.

Depth · KB § PATTERNS/agent-context-architecture.md · sibling
       KB § PATTERNS/keeper-pattern-cache.md.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

# ── Paths ────────────────────────────────────────────────────────────────────
from .cache_backend import (
    apply_locking_pragmas,
    cache_dir as _cache_dir,
    cache_path as _cache_path,
)

CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("agent-context")
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
KB_DIR = REPO_ROOT / "KNOWLEDGE-BASE"


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes()) if path.exists() else ""


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    # WAL + busy_timeout — uniform locking discipline across keeper-mirror caches.
    apply_locking_pragmas(conn)
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_context (
  agent_name      TEXT NOT NULL,
  section_kind    TEXT NOT NULL,
  section_path    TEXT,
  section_value   TEXT NOT NULL,
  source_sha      TEXT NOT NULL,
  cached_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_name ON agent_context(agent_name);
CREATE INDEX IF NOT EXISTS idx_section_kind ON agent_context(section_kind);
CREATE TABLE IF NOT EXISTS cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


# ── Frontmatter parsing (mirror of compliance._parse_frontmatter_owns_kb) ────
def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_yaml, body) — empty frontmatter if absent."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    fm_lines: list[str] = []
    for i, raw in enumerate(lines[1:], start=1):
        if raw.strip() == "---":
            return "".join(fm_lines), "".join(lines[i + 1:])
        fm_lines.append(raw)
    # never closed → treat as no frontmatter (defensive)
    return "", text


def _parse_owns_kb(frontmatter: str) -> list[str]:
    """Extract the `owns_kb:` list. Mirrors compliance._parse_frontmatter_owns_kb
    but returns [] (not None) for absent — the cache is permissive (the
    keeper enforces declaration; we just want to enumerate paths)."""
    if not frontmatter:
        return []
    lines = frontmatter.splitlines()
    in_block = False
    items: list[str] = []
    for raw in lines:
        if not in_block:
            stripped = raw.lstrip()
            if stripped.startswith("owns_kb:") and raw == stripped:
                rhs = raw.partition(":")[2].strip()
                if rhs == "[]":
                    return []
                if rhs:
                    if rhs.startswith("[") and rhs.endswith("]"):
                        inner = rhs[1:-1]
                        return [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
                    return []
                in_block = True
                continue
        else:
            if raw.startswith("  - ") or raw.startswith("- "):
                value = raw.lstrip()[2:].strip().strip('"').strip("'")
                if value:
                    items.append(value)
                continue
            if raw.strip() == "":
                continue
            if not raw.startswith(" "):
                in_block = False
                continue
    return items


# ── Compact-extract (markdown walk) ──────────────────────────────────────────
def _compact_extract(md: str, max_lines: int = 50) -> str:
    """Return a compact summary of a markdown doc: H1 + first paragraph +
    per-H2 first line. Capped at `max_lines` total. Pure line-walk; no
    regex needed (markdown structure is line-prefix-based)."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    # H1 title
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# ") and not ln.startswith("## "):
            out.append(ln)
            i += 1
            break
        i += 1
    # First non-empty paragraph after H1 (until blank or next heading)
    para: list[str] = []
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            if para:
                break
            i += 1
            continue
        if ln.startswith("#"):
            break
        para.append(ln)
        i += 1
        if len(para) >= 8:  # paragraph cap
            break
    if para:
        out.append("")
        out.extend(para)
    # Each subsequent H2 + first non-blank non-heading line
    while i < len(lines) and len(out) < max_lines:
        ln = lines[i]
        if ln.startswith("## ") and not ln.startswith("### "):
            out.append("")
            out.append(ln)
            # first non-blank line
            j = i + 1
            while j < len(lines):
                sub = lines[j]
                if sub.strip() and not sub.startswith("#"):
                    out.append(sub if len(sub) <= 200 else sub[:200] + "…")
                    break
                if sub.startswith("#"):
                    break
                j += 1
            i = j
        else:
            i += 1
    return "\n".join(out[:max_lines]).rstrip()


# ── Bundle-SHA per agent (all sources concatenated) ──────────────────────────
def _bundle_sources(agent_md: Path) -> tuple[str, list[Path]]:
    """Compute (bundle_sha, [sources]) for an agent.

    bundle_sha = sha256(agent.md.bytes ‖ each owned_kb.bytes), in path order.
    Missing owned-KB paths are still INCLUDED in the SHA stream (as empty
    bytes) so they re-trigger rebuild when they appear later.
    """
    if not agent_md.exists():
        return "", []
    fm, _body = _split_frontmatter(agent_md.read_text(encoding="utf-8"))
    paths_decl = _parse_owns_kb(fm)
    hasher = hashlib.sha256()
    hasher.update(agent_md.read_bytes())
    sources: list[Path] = [agent_md]
    for rel in paths_decl:
        kb = KB_DIR / rel
        sources.append(kb)
        hasher.update(b"\x00")  # boundary
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        if kb.exists():
            hasher.update(kb.read_bytes())
    return hasher.hexdigest(), sources


# ── Public API ───────────────────────────────────────────────────────────────
def refresh(force: bool = False, agent_name: str | None = None) -> dict:
    """Re-populate cache rows. Idempotent.

    Per-agent bundle_sha is compared vs cache_meta; matches short-circuit
    (unless `force=True`). `agent_name=...` limits scope to one agent.

    Returns:
      {ok, status('in-sync'|'rebuilt'), refreshed=[agent_names], rows_written}
    """
    if not AGENTS_DIR.is_dir():
        return {"ok": True, "status": "in-sync", "refreshed": [], "rows_written": 0}
    conn = _connect()
    _init_schema(conn)

    targets: list[Path] = sorted(AGENTS_DIR.glob("*.md"))
    if agent_name:
        targets = [p for p in targets if p.stem == agent_name]
    refreshed: list[str] = []
    skipped: list[str] = []
    total_rows = 0

    for agent_md in targets:
        stem = agent_md.stem
        bundle_sha, _sources = _bundle_sources(agent_md)
        cache_key = f"bundle_sha:{stem}"
        if not force:
            cur = conn.execute(
                "SELECT value FROM cache_meta WHERE key=?", (cache_key,)
            )
            row = cur.fetchone()
            if row and row["value"] == bundle_sha:
                skipped.append(stem)
                continue
        # Rebuild this agent's rows.
        conn.execute("DELETE FROM agent_context WHERE agent_name=?", (stem,))
        text = agent_md.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        now = _now_iso()
        rows: list[tuple] = []
        rows.append((stem, "frontmatter", None, fm, _sha_bytes(fm.encode("utf-8")), now))
        rows.append((stem, "body", None, body, _sha_bytes(body.encode("utf-8")), now))
        for rel in _parse_owns_kb(fm):
            kb = KB_DIR / rel
            if not kb.exists():
                continue  # keeper flags missing owns_kb; cache silently skips
            extract = _compact_extract(kb.read_text(encoding="utf-8"))
            rows.append((stem, "owned-kb-extract", rel, extract, _sha_file(kb), now))
        conn.executemany(
            "INSERT INTO agent_context(agent_name,section_kind,section_path,"
            "section_value,source_sha,cached_at) VALUES (?,?,?,?,?,?)",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
            (cache_key, bundle_sha),
        )
        refreshed.append(stem)
        total_rows += len(rows)

    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", _now_iso()),
    )
    conn.commit()
    conn.close()
    status = "in-sync" if not refreshed else "rebuilt"
    return {
        "ok": True,
        "status": status,
        "refreshed": refreshed,
        "skipped": skipped,
        "rows_written": total_rows,
    }


def lookup(agent_name: str) -> dict:
    """Return the compact bundle for one agent.

    Lazy freshness leg: compute live bundle_sha vs cached; mismatch ⇒
    rebuild this agent before answering. Returns:
      {ok, agent_name, frontmatter, body, owned_kb: [{path, extract}],
       bundle_sha, cached_at}
    """
    agent_md = AGENTS_DIR / f"{agent_name}.md"
    if not agent_md.exists():
        return {"ok": False, "error": f"agent {agent_name!r} not found"}
    live_sha, _ = _bundle_sources(agent_md)
    if not CACHE_PATH.exists():
        refresh(agent_name=agent_name)
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute(
        "SELECT value FROM cache_meta WHERE key=?",
        (f"bundle_sha:{agent_name}",),
    )
    row = cur.fetchone()
    if not row or row["value"] != live_sha:
        conn.close()
        refresh(agent_name=agent_name)
        conn = _connect()
        _init_schema(conn)
    cur = conn.execute(
        "SELECT section_kind, section_path, section_value, cached_at "
        "FROM agent_context WHERE agent_name=? ORDER BY section_kind, section_path",
        (agent_name,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    fm = next((r["section_value"] for r in rows if r["section_kind"] == "frontmatter"), "")
    body = next((r["section_value"] for r in rows if r["section_kind"] == "body"), "")
    owned = [
        {"path": r["section_path"], "extract": r["section_value"]}
        for r in rows if r["section_kind"] == "owned-kb-extract"
    ]
    cached_at = rows[0]["cached_at"] if rows else None
    return {
        "ok": True,
        "agent_name": agent_name,
        "frontmatter": fm,
        "body": body,
        "owned_kb": owned,
        "bundle_sha": live_sha,
        "cached_at": cached_at,
    }


def list_agents() -> list[str]:
    """Distinct agent_names in the cache (rebuild if empty)."""
    if not CACHE_PATH.exists():
        refresh()
    conn = _connect()
    _init_schema(conn)
    cur = conn.execute(
        "SELECT DISTINCT agent_name FROM agent_context ORDER BY agent_name"
    )
    out = [r["agent_name"] for r in cur.fetchall()]
    conn.close()
    return out


def get_bundle_sha(agent_name: str) -> tuple[str, str | None]:
    """Return (live_bundle_sha, cached_bundle_sha) — supports the
    freshness keeper. Cached value is None if cache missing/unread."""
    agent_md = AGENTS_DIR / f"{agent_name}.md"
    live, _ = _bundle_sources(agent_md)
    cached: str | None = None
    if CACHE_PATH.exists():
        try:
            conn = sqlite3.connect(str(CACHE_PATH))
            cur = conn.execute(
                "SELECT value FROM cache_meta WHERE key=?",
                (f"bundle_sha:{agent_name}",),
            )
            row = cur.fetchone()
            cached = row[0] if row else None
            conn.close()
        except sqlite3.Error:
            cached = None
    return live, cached


__all__ = [
    "CACHE_PATH",
    "refresh",
    "lookup",
    "list_agents",
    "get_bundle_sha",
]

"""Local SQLite cache of absorption tracking — 9th keeper-mirror cache.

Why this exists
    Product absorptions (importing a 3rd-party codebase into noctusai as a
    seed-native organ) are multi-session operations with lifecycle stages
    (cloned → diagnosed → uplifting → porting → teardown → done) and
    per-absorption capability extraction events (identified → building →
    pilot → fleet → native_doc → de_referenced). Without a durable,
    queryable store the state of an in-flight absorption is only recoverable
    by re-reading the KB and project-history text files, which is slow and
    error-prone across sessions.

    This is the 9th member of the keeper-mirror family. It follows the
    EXACT 3-leg mirror contract every existing keeper-mirror cache uses.

Source of truth (durable, committed)
    `project-history/absorptions.ndjson` — one JSON object per line.
    Two event kinds (unified schema, `kind` field):

    lifecycle:
      {
        "ts":          ISO-8601 UTC,
        "slug":        str,
        "kind":        "lifecycle",
        "source_repo": str|null,
        "source_head": str|null,
        "stage":       "cloned|diagnosed|uplifting|porting|teardown|done",
        "note":        str
      }

    capability:
      {
        "ts":            ISO-8601 UTC,
        "slug":          str,
        "kind":          "capability",
        "capability":    str,
        "target_organ":  str,
        "status":        "identified|building|pilot|fleet|native_doc|de_referenced",
        "pilot":         str|null,
        "note":          str
      }

Cache (gitignored, derived — `<git-common-dir>/noctusai/cache/absorptions.sqlite`)
    Mirror of the ndjson. Per-source-sha guard.

    Tables:
      absorptions(slug PK, stage, source_repo, source_head, updated_ts, note)
      capabilities(slug, capability, target_organ, status, pilot, updated_ts, note,
                   PRIMARY KEY(slug, capability))
      meta(key, value) — source_sha + populated_at

    Derivation = latest-event-wins per slug (lifecycle) and per (slug, capability).
    Rebuild is a pure function of the ndjson (idempotent).

Mirror contract (3 legs — same shape as the family)
    (a) Eager pre-commit refresh when the ndjson is staged.
    (b) Lazy query-time source_sha mismatch rebuild.
    (c) `check_absorptions_cache_freshness` keeper (severity warning).

KB § PATTERNS/common/absorption-tracking.md (tech-lead wires after integration).
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

from .cache_backend import (
    apply_locking_pragmas,
    cache_dir as _cache_dir,
    cache_path as _cache_path,
)

# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = _cache_dir()
CACHE_PATH = _cache_path("absorptions")
LEDGER_PATH = REPO_ROOT / "project-history" / "absorptions.ndjson"

# ── Allowed enums ─────────────────────────────────────────────────────────────
LIFECYCLE_STAGES = frozenset({"cloned", "diagnosed", "uplifting", "porting", "teardown", "done"})
CAPABILITY_STATUSES = frozenset({"identified", "building", "pilot", "fleet", "native_doc", "de_referenced"})
EVENT_KINDS = frozenset({"lifecycle", "capability"})

_log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sha(ledger: Path | None = None) -> str:
    p = ledger if ledger is not None else LEDGER_PATH
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _connect(cache: Path | None = None) -> sqlite3.Connection:
    p = cache if cache is not None else CACHE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    apply_locking_pragmas(conn)
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS absorptions (
  slug        TEXT PRIMARY KEY,
  stage       TEXT NOT NULL,
  source_repo TEXT,
  source_head TEXT,
  updated_ts  TEXT NOT NULL,
  note        TEXT
);
CREATE TABLE IF NOT EXISTS capabilities (
  slug         TEXT NOT NULL,
  capability   TEXT NOT NULL,
  target_organ TEXT NOT NULL,
  status       TEXT NOT NULL,
  pilot        TEXT,
  updated_ts   TEXT NOT NULL,
  note         TEXT,
  PRIMARY KEY (slug, capability)
);
CREATE INDEX IF NOT EXISTS idx_abs_stage  ON absorptions(stage);
CREATE INDEX IF NOT EXISTS idx_cap_status ON capabilities(status);
CREATE INDEX IF NOT EXISTS idx_cap_slug   ON capabilities(slug);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


# ── Validation ────────────────────────────────────────────────────────────────
def _validate_lifecycle(stage: str) -> dict | None:
    if stage not in LIFECYCLE_STAGES:
        return {"ok": False, "error": f"stage must be one of {sorted(LIFECYCLE_STAGES)}; got {stage!r}"}
    return None


def _validate_capability(status: str) -> dict | None:
    if status not in CAPABILITY_STATUSES:
        return {"ok": False, "error": f"status must be one of {sorted(CAPABILITY_STATUSES)}; got {status!r}"}
    return None


# ── Public API: log ───────────────────────────────────────────────────────────
def log_entry(
    *,
    slug: str,
    kind: str,
    # lifecycle fields
    stage: str | None = None,
    source_repo: str | None = None,
    source_head: str | None = None,
    # capability fields
    capability: str | None = None,
    target_organ: str | None = None,
    status: str | None = None,
    pilot: str | None = None,
    # shared
    note: str = "",
    ts: str | None = None,
) -> dict:
    """Append one lifecycle OR capability event to the ndjson + refresh the cache.

    For lifecycle events: `kind="lifecycle"`, `slug`, `stage` are required.
    For capability events: `kind="capability"`, `slug`, `capability`,
    `target_organ`, `status` are required.

    Returns `{ok, entry, ledger_path}` on success, `{ok: False, error}` on
    invalid enum value or missing required field. No silent errors.

    The 3-leg eager mirror refresh fires after the append so the cache stays
    COMPLIANT by construction (same pattern as auto_improvement.log_entry).
    Best-effort: a refresh failure is logged; the lazy rebuild + heal-on-contact
    still cover it.
    """
    if kind not in EVENT_KINDS:
        return {"ok": False, "error": f"kind must be one of {sorted(EVENT_KINDS)}; got {kind!r}"}
    entry: dict = {
        "ts": ts if ts is not None else _now_iso(),
        "slug": slug,
        "kind": kind,
        "note": note,
    }
    if kind == "lifecycle":
        if not stage:
            return {"ok": False, "error": "stage is required for lifecycle events"}
        err = _validate_lifecycle(stage)
        if err:
            return err
        entry["stage"] = stage
        if source_repo is not None:
            entry["source_repo"] = source_repo
        if source_head is not None:
            entry["source_head"] = source_head
    elif kind == "capability":
        if not capability:
            return {"ok": False, "error": "capability is required for capability events"}
        if not target_organ:
            return {"ok": False, "error": "target_organ is required for capability events"}
        if not status:
            return {"ok": False, "error": "status is required for capability events"}
        err = _validate_capability(status)
        if err:
            return err
        entry["capability"] = capability
        entry["target_organ"] = target_organ
        entry["status"] = status
        if pilot is not None:
            entry["pilot"] = pilot

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 3-leg keeper-mirror contract: EAGER mirror refresh at the mutation point.
    # Zero-OpenAI, source_sha-guarded. Best-effort (a failure is LOGGED; the
    # lazy rebuild + heal-on-contact remain the fallback).
    try:
        refresh()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "absorption_tracking.log_entry: eager mirror refresh skipped (%s); "
            "lazy rebuild + heal-on-contact remain the fallback",
            exc,
        )

    try:
        ledger_path = str(LEDGER_PATH.relative_to(REPO_ROOT))
    except ValueError:
        ledger_path = str(LEDGER_PATH)
    return {"ok": True, "entry": entry, "ledger_path": ledger_path}


# ── Public API: refresh ───────────────────────────────────────────────────────
def refresh(force: bool = False, ledger: Path | None = None, cache: Path | None = None) -> dict:
    """Re-populate the cache from the ndjson. Idempotent (source_sha guard).

    Derivation: latest-event-wins per slug (lifecycle) and per (slug, capability).
    """
    lp = ledger if ledger is not None else LEDGER_PATH
    sha_now = _source_sha(lp)
    conn = _connect(cache)
    _init_schema(conn)

    if not force:
        cur = conn.execute("SELECT value FROM meta WHERE key='source_sha'")
        row = cur.fetchone()
        if row and row["value"] == sha_now:
            conn.close()
            return {"ok": True, "status": "in-sync", "source_sha": sha_now, "rows_written": 0}

    # Full rebuild — latest-event-wins by iterating in ts order
    # (ndjson is append-only so the last event for a key wins).
    lifecycle_latest: dict[str, dict] = {}   # slug → latest lifecycle event
    capability_latest: dict[tuple, dict] = {}  # (slug, capability) → latest capability event

    if lp.exists():
        for line in lp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = e.get("kind")
            slug = e.get("slug", "")
            if not slug:
                continue
            if k == "lifecycle":
                # latest-event-wins: since ndjson is append-only the last
                # entry with the given slug is the "current" state.
                lifecycle_latest[slug] = e
            elif k == "capability":
                cap = e.get("capability", "")
                if cap:
                    capability_latest[(slug, cap)] = e

    now = _now_iso()
    conn.execute("DELETE FROM absorptions")
    conn.execute("DELETE FROM capabilities")

    abs_rows = [
        (
            slug,
            e.get("stage", ""),
            e.get("source_repo"),
            e.get("source_head"),
            e.get("ts", now),
            e.get("note", ""),
        )
        for slug, e in lifecycle_latest.items()
    ]
    if abs_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO absorptions(slug, stage, source_repo, source_head, updated_ts, note) "
            "VALUES (?,?,?,?,?,?)",
            abs_rows,
        )

    cap_rows = [
        (
            slug,
            cap,
            e.get("target_organ", ""),
            e.get("status", ""),
            e.get("pilot"),
            e.get("ts", now),
            e.get("note", ""),
        )
        for (slug, cap), e in capability_latest.items()
    ]
    if cap_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO capabilities(slug, capability, target_organ, status, pilot, updated_ts, note) "
            "VALUES (?,?,?,?,?,?,?)",
            cap_rows,
        )

    rows_written = len(abs_rows) + len(cap_rows)
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", ("source_sha", sha_now))
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", ("populated_at", now))
    conn.commit()
    conn.close()
    return {"ok": True, "status": "rebuilt", "source_sha": sha_now, "rows_written": rows_written}


# ── Public API: status ────────────────────────────────────────────────────────
def status(
    slug: str | None = None,
    stage: str | None = None,
    ledger: Path | None = None,
    cache: Path | None = None,
) -> dict:
    """Return derived absorption state from the sqlite cache.

    Lazy-rebuilds if the cache is stale (source_sha mismatch). Returns:
      {ok, absorptions: [{slug, stage, source_repo, source_head, updated_ts, note,
                          capabilities: [{capability, target_organ, status, pilot, updated_ts, note}]}]}

    Filters:
      slug — exact slug match
      stage — lifecycle stage filter
    """
    lp = ledger if ledger is not None else LEDGER_PATH
    cp = cache if cache is not None else CACHE_PATH

    sha_now = _source_sha(lp)
    if not cp.exists():
        refresh(ledger=lp, cache=cp)
    conn = _connect(cp)
    _init_schema(conn)
    cur = conn.execute("SELECT value FROM meta WHERE key='source_sha'")
    row = cur.fetchone()
    if not row or row["value"] != sha_now:
        conn.close()
        refresh(ledger=lp, cache=cp)
        conn = _connect(cp)
        _init_schema(conn)

    sql = "SELECT * FROM absorptions WHERE 1=1"
    params: list = []
    if slug:
        sql += " AND slug = ?"
        params.append(slug)
    if stage:
        sql += " AND stage = ?"
        params.append(stage)
    sql += " ORDER BY slug"
    abs_rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    result_abs = []
    for a in abs_rows:
        cap_rows = conn.execute(
            "SELECT * FROM capabilities WHERE slug = ? ORDER BY capability",
            (a["slug"],),
        ).fetchall()
        a["capabilities"] = [dict(c) for c in cap_rows]
        result_abs.append(a)

    conn.close()
    return {"ok": True, "absorptions": result_abs}


# ── Public API: query capabilities ───────────────────────────────────────────
def query_capabilities(
    slug: str | None = None,
    cap_status: str | None = None,
    target_organ: str | None = None,
    ledger: Path | None = None,
    cache: Path | None = None,
) -> list[dict]:
    """Filter capabilities by slug / status / target_organ. Lazy-rebuilds if stale."""
    lp = ledger if ledger is not None else LEDGER_PATH
    cp = cache if cache is not None else CACHE_PATH

    sha_now = _source_sha(lp)
    if not cp.exists():
        refresh(ledger=lp, cache=cp)
    conn = _connect(cp)
    _init_schema(conn)
    cur = conn.execute("SELECT value FROM meta WHERE key='source_sha'")
    row = cur.fetchone()
    if not row or row["value"] != sha_now:
        conn.close()
        refresh(ledger=lp, cache=cp)
        conn = _connect(cp)
        _init_schema(conn)

    sql = "SELECT * FROM capabilities WHERE 1=1"
    params: list = []
    if slug:
        sql += " AND slug = ?"
        params.append(slug)
    if cap_status:
        sql += " AND status = ?"
        params.append(cap_status)
    if target_organ:
        sql += " AND target_organ LIKE ?"
        params.append(f"%{target_organ}%")
    sql += " ORDER BY slug, capability"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.absorption_log",
        description=(
            "Append a lifecycle OR capability event to the absorption tracking "
            "ledger (`project-history/absorptions.ndjson`). "
            "For lifecycle events: `kind='lifecycle'`, `slug`, `stage` required. "
            "`stage` ∈ {'cloned','diagnosed','uplifting','porting','teardown','done'}. "
            "For capability events: `kind='capability'`, `slug`, `capability`, "
            "`target_organ`, `status` required. "
            "`status` ∈ {'identified','building','pilot','fleet','native_doc','de_referenced'}. "
            "Unknown enum values are refused (no silent errors). "
            "The sqlite cache is eagerly refreshed after each append."
        ),
    )
    def _log(
        slug: str,
        kind: str,
        stage: str | None = None,
        source_repo: str | None = None,
        source_head: str | None = None,
        capability: str | None = None,
        target_organ: str | None = None,
        status: str | None = None,
        pilot: str | None = None,
        note: str = "",
    ) -> dict:
        return log_entry(
            slug=slug, kind=kind, stage=stage,
            source_repo=source_repo, source_head=source_head,
            capability=capability, target_organ=target_organ,
            status=status, pilot=pilot, note=note,
        )

    @server.tool(
        name="noctus.dev.absorption_status",
        description=(
            "Return derived absorption state from the sqlite cache: list of "
            "absorptions with their lifecycle stage + per-absorption capabilities "
            "uplift statuses. Lazy-rebuilds the cache if the ndjson has changed "
            "(source_sha mismatch). Optional filters: `slug` (exact) and "
            "`stage` (lifecycle stage). "
            "Source: `project-history/absorptions.ndjson`."
        ),
    )
    def _status(slug: str | None = None, stage: str | None = None) -> dict:
        return status(slug=slug, stage=stage)

    @server.tool(
        name="noctus.dev.absorption_query",
        description=(
            "Filter absorption capabilities by slug / status / target_organ. "
            "Lazy-rebuilds the cache if stale. `cap_status` ∈ "
            "{'identified','building','pilot','fleet','native_doc','de_referenced'}. "
            "`target_organ` accepts a substring (e.g. 'noctusai_lib.domain.'). "
            "Returns a flat list of capability rows."
        ),
    )
    def _query(
        slug: str | None = None,
        cap_status: str | None = None,
        target_organ: str | None = None,
    ) -> list[dict]:
        return query_capabilities(slug=slug, cap_status=cap_status, target_organ=target_organ)

    @server.tool(
        name="noctus.dev.absorption_refresh",
        description=(
            "Re-populate the absorptions cache from the ndjson. "
            "Idempotent — source_sha guard short-circuits when in-sync; "
            "force=True rebuilds anyway. Auto-run by pre-commit on "
            "`project-history/absorptions.ndjson` change."
        ),
    )
    def _refresh(force: bool = False) -> dict:
        return refresh(force=force)


__all__ = [
    "CACHE_PATH",
    "LEDGER_PATH",
    "LIFECYCLE_STAGES",
    "CAPABILITY_STATUSES",
    "EVENT_KINDS",
    "log_entry",
    "refresh",
    "status",
    "query_capabilities",
    "register",
]

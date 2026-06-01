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
import logging
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
CACHE_PATH = _cache_path("auto-improvement")
LEDGER_PATH = REPO_ROOT / "project-history" / "auto-improvement.ndjson"

# Allowed enums (defensive; loud-fail on unknown values so typos don't grow stalely).
SCOPES = frozenset({"scoped", "broad"})
KINDS = frozenset({"drift", "improvement"})
# `s3-codified` is the canonical s3 name (matches `check_codification_pipeline_health` +
# CLAUDE.md §1 + user-facing terminology). `s3-kb` is the LEGACY alias from the
# first implementation (one historical entry uses it; new writes should prefer
# `s3-codified`). The codify_log helper standardizes on `s3-codified`.
STATUSES = frozenset({"s1-emergent", "s2-memory", "s3-kb", "s3-codified", "s4-keeper", "closed"})


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
    # WAL + busy_timeout — readers don't block writers AND a contending writer
    # waits instead of erroring (uniform locking discipline across keeper-mirror
    # caches).
    apply_locking_pragmas(conn)
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
    resolve_when: str | list[str] | None = None,
    resolve_to: str | None = None,
) -> dict:
    """Append one entry to the ndjson + invalidate the cache.

    Returns `{ok, entry, ledger_path}` on success, `{ok: False, error}` on
    invalid enum value. The tech-lead's typical call after an engineer
    surface; can also be called directly when the tech-lead observes
    something themselves.

    `resolve_when` is the **resolution handle** — a declarative predicate (or
    list, AND-combined) describing the real-world condition that means this
    drift is RESOLVED. `auto_improvement_reconcile` evaluates it against the
    live tree and auto-advances `status` to `resolve_to` (default `closed`)
    when satisfied — so a landed fix stops re-surfacing as "hot drift" next
    session WITHOUT anyone remembering to flip the status by hand. Predicate
    grammar lives in `_eval_predicate`. Optional but STRONGLY recommended for
    every `s2-memory`+ entry (enforced advisory by
    `check_s2_drift_has_resolution_handle`).
    """
    err = _validate(scope, kind, status)
    if err is not None:
        return err
    if resolve_to is not None and resolve_to not in STATUSES:
        return {"ok": False, "error": f"resolve_to must be one of {sorted(STATUSES)}; got {resolve_to!r}"}
    entry: dict = {
        "ts": _now_iso(),
        "agent": agent,
        "scope": scope,
        "kind": kind,
        "target": target,
        "description": description,
        "status": status,
        "source_ref": source_ref,
    }
    if resolve_when is not None:
        entry["resolve_when"] = resolve_when
    if resolve_to is not None:
        entry["resolve_to"] = resolve_to
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # 3-leg keeper-mirror contract: EAGER-refresh the mirror cache at the
    # mutation point (zero-OpenAI, source_sha-guarded) so the cache stays
    # COMPLIANT by construction — the freshness check is then a true no-op,
    # instead of the cache sitting stale until a query()/8-way-check heals it
    # on contact (the 2026-06-01 trap: a codify_log append left the
    # auto-improvement cache stale → blocked an UNRELATED commit [high]). This
    # is the proactive mechanism the other mirrors already use (refresh-on-source-
    # mutate); heal-on-contact (settle_structural_caches) stays ONLY as the
    # FF-merge / cross-tree fallback. Best-effort: a refresh failure is LOGGED,
    # the lazy rebuild + heal-on-contact still cover it (no silent error).
    try:
        refresh()
    except Exception as exc:  # noqa: BLE001 — eager refresh is best-effort
        logging.getLogger(__name__).warning(
            "auto_improvement.log_entry: eager mirror refresh skipped (%s); "
            "lazy rebuild + heal-on-contact remain the fallback",
            exc,
        )
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
    skip_reconcile: bool = False,
) -> list[dict]:
    """Consult the cache before editing a doc/agent.

    `target` accepts an exact path OR a substring (e.g.
    `.claude/agents/backend-engineer.md` for agent-specific surfaces,
    `KB § PATTERNS/` for all KB-pattern surfaces). `open_only=True`
    returns only entries that STILL NEED WORK — excludes the terminal
    statuses (`closed` ∪ `s4-keeper`; a keeper-guarded drift is done).
    Lazy rebuild on source_sha mismatch.

    **Auto-reconcile-filter (heal-on-contact at the READ path).** When
    `open_only=True`, the result EXCLUDES any entry whose `resolve_when`
    predicate already passes against the live tree — i.e. landed-but-not-yet-
    closed drift is never surfaced as open. This is the structural guarantee
    that a fresh environment cannot re-detect already-done work: it does not
    depend on anyone REMEMBERING to run `reconcile` first (the ledger row may
    still read `s2-memory` in git until an explicit `reconcile(dry_run=False)`
    + commit, but the surface is correct on every read). Set
    `skip_reconcile=True` to get the raw not-closed set (the ledger's literal
    state — used by the reconcile apply path + tests). Graceful: a reconcile
    failure logs a warning and falls back to the unfiltered set."""
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
        # "open" = still needs work = NOT terminal. Terminal = `closed` ∪
        # `s4-keeper` (a keeper now permanently guards the drift — the strongest
        # codification, no further work). Mirrors reconcile's TERMINAL_STATUSES so
        # the read surface and the reconciler agree on what "done" means; aligns
        # the impl with the long-documented intent (kb_recurrence_radar:
        # "open_only: read only s1/s2/s3 entries; s4-keeper + closed excluded").
        _terminal = sorted(TERMINAL_STATUSES)
        sql += f" AND status NOT IN ({','.join('?' for _ in _terminal)})"
        params.extend(_terminal)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(sql, params)
    out = [dict(r) for r in cur.fetchall()]
    conn.close()
    if open_only and not skip_reconcile and out:
        # Heal-on-contact: drop entries whose resolve_when already passes, so a
        # landed fix is never re-surfaced as open even before the ledger row is
        # closed. Best-effort — reconcile reads the tree only (no mutation here).
        try:
            rec = reconcile(dry_run=True)
            resolved = {(r["ts"], r["target"]) for r in rec.get("reconciled", [])}
            if resolved:
                out = [r for r in out if (r.get("ts"), r.get("target")) not in resolved]
        except Exception as e:  # noqa: BLE001 — never let the filter break the query
            logging.getLogger(__name__).warning(
                "auto_improvement.query open_only reconcile-filter skipped: %s", e
            )
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


# ── Reconciliation: self-close landed drift (heal-on-contact) ────────────────
# The problem this solves. The ledger is APPEND-ONLY. When a drift's fix lands,
# the resolving session typically APPENDS a fresh `closed`/`s4-keeper` row
# (a new ts+target+description) instead of promoting the ORIGINAL — so the
# original `s2-memory` row never dies and re-surfaces as "hot drift" every
# session (observed 2026-06-01: 4 entries resolved at 00:39 via appended rows,
# still surfaced by the 00:53 cache). `promote()` keys on the exact triple, which
# the resolving agent rarely has handy. Reconcile fixes this STRUCTURALLY: each
# entry carries a declarative `resolve_when` predicate; reconcile evaluates it
# against the live tree and auto-advances the ORIGINAL row's status. Run it
# heal-on-contact at every hot-drift surface (the /contextualize protocol).

# Statuses that are terminal — reconcile never re-touches them, and they never
# count as "open drift" for the resolution-handle discipline.
TERMINAL_STATUSES = frozenset({"s4-keeper", "closed"})

# Text-file suffixes reconcile's grep predicates scan (skips binaries).
_GREP_SUFFIXES = frozenset({".md", ".py", ".txt", ".json", ".yml", ".yaml", ".ndjson", ".toml", ".cfg", ".sh", ".ts", ".tsx"})
# Directories never walked (vendored / derived — false-positive sources).
_GREP_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "__pycache__", ".claude", "dist", "build", ".mypy_cache", ".pytest_cache"})


def _entry_key(e: dict) -> tuple[str, str, str]:
    """Composite identity used everywhere the ndjson is rewritten by-entry."""
    return (e.get("ts", ""), e.get("target", ""), e.get("description", ""))


def _load_entries() -> list[dict]:
    """Parse the ndjson into valid entry dicts (malformed lines skipped)."""
    out: list[dict] = []
    if not LEDGER_PATH.exists():
        return out
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _rewrite_ledger(mutate) -> int:
    """Atomic by-entry rewrite of the ndjson (tmp + rename). `mutate(entry)`
    returns the (possibly modified) entry dict; an entry is counted changed when
    its dict differs. Malformed lines are preserved verbatim — never lost.

    Single source of truth for every status-mutating rewrite (reconcile +
    `codification_radar.promote` both route through this — DRY on the
    atomic-rewrite + malformed-preservation invariants).
    """
    if not LEDGER_PATH.exists():
        return 0
    new_lines: list[str] = []
    changed = 0
    for raw in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            new_lines.append(raw)
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(raw)  # preserve malformed verbatim
            continue
        before = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        updated = mutate(dict(entry))
        after = json.dumps(updated, ensure_ascii=False, sort_keys=True)
        if after != before:
            changed += 1
            new_lines.append(json.dumps(updated, ensure_ascii=False))
        else:
            new_lines.append(raw)  # unchanged → preserve verbatim (no cosmetic churn)
    tmp = LEDGER_PATH.with_suffix(".ndjson.tmp")
    tmp.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    tmp.replace(LEDGER_PATH)
    return changed


def _grep_file_count(term: str, root: Path) -> int:
    """Number of distinct files under `root` containing `term`. `root` may be a
    file (checks that one) or a directory (rglob over text suffixes, skipping
    vendored/derived dirs)."""
    if not term:
        return 0
    if root.is_file():
        try:
            return 1 if term in root.read_text(encoding="utf-8", errors="ignore") else 0
        except OSError:
            return 0
    if not root.is_dir():
        return 0
    count = 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in _GREP_SUFFIXES:
            continue
        if any(part in _GREP_SKIP_DIRS for part in p.parts):
            continue
        try:
            if term in p.read_text(encoding="utf-8", errors="ignore"):
                count += 1
        except OSError:
            continue
    return count


def _eval_predicate(pred: str, all_entries: list[dict], this_entry: dict, repo_root: Path) -> tuple[bool, str]:
    """Evaluate ONE resolution predicate against the live tree.

    Grammar (a satisfied predicate ⇒ this drift is resolved):
      · `keeper:<name>`                  keeper `def <name>(` exists in compliance.py
      · `path_exists:<relpath>`          file/dir exists under repo root
      · `grep_present:<term>@<path>`     ≥1 file under <path> contains <term>
      · `grep_max:<n>:<term>@<path>`     ≤ n files under <path> contain <term>
      · `superseded_by:<target_substr>`  a LATER entry (ts >) at a terminal status
                                          (s4-keeper|closed) has target ⊇ substr

    Returns `(satisfied, human_detail)`. Unknown grammar ⇒ `(False, "unknown ...")`
    (loud, never silently True). KB § PATTERNS/common/scoped-auto-improvement.md.
    """
    pred = pred.strip()
    if pred.startswith("keeper:"):
        name = pred[len("keeper:"):].strip()
        comp = repo_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        ok = comp.is_file() and f"def {name}(" in comp.read_text(encoding="utf-8", errors="ignore")
        return ok, f"keeper {name} {'exists' if ok else 'absent'}"
    if pred.startswith("path_exists:"):
        rel = pred[len("path_exists:"):].strip()
        ok = (repo_root / rel).exists()
        return ok, f"path {rel} {'exists' if ok else 'missing'}"
    if pred.startswith("grep_present:"):
        body = pred[len("grep_present:"):]
        term, _, path = body.partition("@")
        n = _grep_file_count(term.strip(), repo_root / path.strip()) if path else 0
        return n >= 1, f"grep_present '{term.strip()}' in {path.strip()}: {n} file(s)"
    if pred.startswith("grep_max:"):
        body = pred[len("grep_max:"):]
        n_str, _, rest = body.partition(":")
        term, _, path = rest.partition("@")
        try:
            cap = int(n_str.strip())
        except ValueError:
            return False, f"grep_max: bad threshold {n_str!r}"
        n = _grep_file_count(term.strip(), repo_root / path.strip()) if path else 0
        return n <= cap, f"grep_max '{term.strip()}' in {path.strip()}: {n} ≤ {cap}? "
    if pred.startswith("superseded_by:"):
        substr = pred[len("superseded_by:"):].strip()
        my_ts = this_entry.get("ts", "")
        for e in all_entries:
            if (e.get("status") in TERMINAL_STATUSES
                    and e.get("ts", "") > my_ts
                    and substr in e.get("target", "")):
                return True, f"superseded by terminal entry target⊇'{substr}'"
        return False, f"no terminal superseding entry for '{substr}'"
    return False, f"unknown predicate grammar: {pred!r}"


def reconcile(dry_run: bool = True, repo_root: Path | None = None) -> dict:
    """Heal-on-contact: auto-advance every OPEN entry whose `resolve_when`
    predicate(s) are now satisfied by the live tree.

    An entry resolves when ALL its `resolve_when` predicates pass (AND); status
    advances to `resolve_to` (default `closed`) and the entry is stamped with
    `resolved_ts` + `resolved_by` (the satisfied predicates) for audit. Entries
    already terminal (s4-keeper|closed) are skipped.

    Returns `{ok, dry_run, reconciled:[{ts,target,from,to,by}], still_open:[...],
    unhandled:[{ts,target,status}], counts}`. `unhandled` = open entries WITH NO
    `resolve_when` (they cannot self-close — the resolution-handle keeper flags
    the s2-memory ones). Idempotent: a second run reconciles nothing new.
    """
    root = repo_root or REPO_ROOT
    entries = _load_entries()
    resolutions: dict[tuple, tuple[str, list[str]]] = {}
    reconciled: list[dict] = []
    still_open: list[dict] = []
    unhandled: list[dict] = []
    now = _now_iso()

    for e in entries:
        if e.get("status") in TERMINAL_STATUSES:
            continue
        rw = e.get("resolve_when")
        if not rw:
            unhandled.append({"ts": e.get("ts"), "target": e.get("target"), "status": e.get("status")})
            continue
        preds = [rw] if isinstance(rw, str) else list(rw)
        verdicts = [(p, *_eval_predicate(p, entries, e, root)) for p in preds]
        if all(v[1] for v in verdicts):
            new_status = e.get("resolve_to") or "closed"
            # Idempotency guard: if the entry is ALREADY at its resolve_to, there
            # is nothing to advance — skip (else a non-terminal resolve_to like
            # `s3-codified` would re-stamp resolved_ts on every run → ndjson churn).
            if e.get("status") == new_status:
                continue
            satisfied = [v[0] for v in verdicts]
            resolutions[_entry_key(e)] = (new_status, satisfied)
            reconciled.append({
                "ts": e.get("ts"), "target": e.get("target"),
                "from": e.get("status"), "to": new_status, "by": satisfied,
            })
        else:
            still_open.append({
                "ts": e.get("ts"), "target": e.get("target"), "status": e.get("status"),
                "unmet": [v[2] for v in verdicts if not v[1]],
            })

    if not dry_run and resolutions:
        def _mutate(entry: dict) -> dict:
            res = resolutions.get(_entry_key(entry))
            if res is not None and entry.get("status") not in TERMINAL_STATUSES:
                new_status, satisfied = res
                entry["status"] = new_status
                entry["resolved_ts"] = now
                entry["resolved_by"] = satisfied
            return entry
        _rewrite_ledger(_mutate)
        refresh(force=True)  # keep the cache in lockstep with the ledger

    return {
        "ok": True,
        "dry_run": dry_run,
        "reconciled": reconciled,
        "still_open": still_open,
        "unhandled": unhandled,
        "counts": {
            "reconciled": len(reconciled),
            "still_open": len(still_open),
            "unhandled": len(unhandled),
        },
    }


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
        resolve_when: str | list[str] | None = None,
        resolve_to: str | None = None,
    ) -> dict:
        return log_entry(
            scope=scope, kind=kind, target=target, description=description,
            agent=agent, status=status, source_ref=source_ref,
            resolve_when=resolve_when, resolve_to=resolve_to,
        )

    @server.tool(
        name="noctus.dev.auto_improvement_query",
        description=(
            "Consult the auto-improvement cache before editing a doc/agent. "
            "Filter by target (path substring), agent, kind, status, or "
            "open_only=True (returns only still-needs-work entries — excludes "
            "the terminal statuses 'closed' + 's4-keeper'). Most-recent-first. "
            "The **consult-before-editing** discipline — sibling of "
            "keeper-check-before-doc'ing. Lazy-rebuilds on source_sha "
            "mismatch (the cache self-heals on use). With open_only=True the "
            "result AUTO-EXCLUDES entries whose `resolve_when` already passes "
            "(heal-on-contact — landed-but-unclosed drift never surfaces); pass "
            "skip_reconcile=True for the raw not-closed set."
        ),
    )
    def _query(
        target: str | None = None,
        agent: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        open_only: bool = False,
        limit: int = 200,
        skip_reconcile: bool = False,
    ) -> list[dict]:
        return query(
            target=target, agent=agent, kind=kind, status=status,
            open_only=open_only, limit=limit, skip_reconcile=skip_reconcile,
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

    @server.tool(
        name="noctus.dev.auto_improvement_reconcile",
        description=(
            "Heal-on-contact: auto-advance every OPEN auto-improvement entry "
            "whose `resolve_when` predicate(s) are now satisfied by the live "
            "tree — so a landed fix stops re-surfacing as 'hot drift'. "
            "dry_run=True (default) previews; pass dry_run=False to rewrite the "
            "ndjson (atomic) + refresh the cache. Predicate grammar: "
            "`keeper:<name>` · `path_exists:<relpath>` · "
            "`grep_present:<term>@<path>` · `grep_max:<n>:<term>@<path>` · "
            "`superseded_by:<target_substr>`. Returns reconciled / still_open / "
            "unhandled (open entries with NO resolve_when — they cannot self-"
            "close). Run it at every hot-drift surface (the /contextualize "
            "protocol). KB § PATTERNS/common/scoped-auto-improvement.md."
        ),
    )
    def _reconcile(dry_run: bool = True) -> dict:
        return reconcile(dry_run=dry_run)


__all__ = [
    "CACHE_PATH",
    "LEDGER_PATH",
    "SCOPES",
    "KINDS",
    "STATUSES",
    "TERMINAL_STATUSES",
    "log_entry",
    "refresh",
    "query",
    "list_targets",
    "reconcile",
    "register",
]

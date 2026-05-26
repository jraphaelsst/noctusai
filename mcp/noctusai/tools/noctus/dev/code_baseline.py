"""code_baseline — ratified-canonical layer over code recurrence findings.

Sister of `kb_baseline` (W2-E6). Same shape, applied to a different
corpus: instead of `kb_validate_owns_kb` findings, this ratifies output
of `code_recurrence_promote.scan()`.

Why it exists
    Without ratification, every session re-surfaces the same pairs:
    "yes these N similar helpers ARE the duplication; not absorbed yet,
    planned for Q3" → 5 known-noise pairs drown out 1 real new
    recurrence. Same signal-vs-noise problem `kb_baseline` solves for
    owns_kb validation; we just hadn't applied the pattern here yet.

Workflow
    1. `code_recurrence_promote.scan(threshold)` → N pairs.
    2. Architect reviews: 3 will-be-absorbed-Q3, 2 are intentional
       duplication (e.g. seed + per-product wrapper).
    3. `code_ratify("Q3 absorption plan; 2 are intentional seed↔wrapper")`.
    4. Next session: `code_baseline_diff()` shows only NEW pairs since
       ratification — sharp signal.

Storage
    `project-history/code-baselines/<YYYY-MM-DD>-<short_corpus_sha>.json`.
    Corpus_sha here = sha256 of the active code-embeddings cache rows
    (path+symbol+sha tuples) — identifies "which code state was ratified".
    Append-only ledger of decisions (same as kb-baselines).

Keeper
    `check_code_recurrence_drift` (severity `warning`) — fires when:
      - No baseline exists AND current scan has pairs ≥ STRONG band → suggests ratification.
      - Diff vs latest baseline shows new_pairs > _DRIFT_THRESHOLD (default 3).
      - Code corpus shifted significantly since baseline.

KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import REPO_ROOT


# ── Paths ────────────────────────────────────────────────────────────────────
BASELINE_DIR = REPO_ROOT / "project-history" / "code-baselines"

# How many NEW pairs (vs. latest baseline) constitute drift worth flagging.
# Smaller than kb_baseline's 5 because code-corpus signal is sparser —
# a single new recurrence is meaningful when most are stable.
_DRIFT_THRESHOLD = 3


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_dir() -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)


def _code_corpus_sha(repo_root: Path | None = None) -> str:
    """Hash of the active code-embeddings cache rows.

    Identifies "which code state was ratified". Uses the cache directly
    (not the source tree) because the cache IS what `scan()` reads —
    re-ratification only matters when the cache shifts. Deterministic
    via sorted (path, symbol_name, source_sha) tuples.

    Returns empty string when the cache is absent (fresh clone / unreachable).
    """
    root = repo_root or REPO_ROOT
    cache = root / ".claude" / "cache" / "code-embeddings.sqlite"
    if not cache.exists():
        return ""
    h = hashlib.sha256()
    try:
        conn = sqlite3.connect(str(cache))
        cur = conn.execute(
            "SELECT path, symbol_name, source_sha FROM code_chunks "
            "ORDER BY path, symbol_name"
        )
        for path, symbol_name, source_sha in cur:
            h.update(f"{path}\x00{symbol_name}\x00{source_sha}".encode())
            h.update(b"\x00\x00")
        conn.close()
    except sqlite3.Error:
        return ""
    return h.hexdigest()


def _pair_key(match: dict) -> str:
    """Stable identity for a recurrence pair — what makes two matches 'the same'.

    Uses canonical-ordered (path::symbol) pair. Excludes score (which
    fluctuates per refresh) so a pair stays "the same case" across runs.
    """
    a, b = match.get("a") or {}, match.get("b") or {}
    left = (a.get("path", ""), a.get("symbol_name", ""))
    right = (b.get("path", ""), b.get("symbol_name", ""))
    if left <= right:
        return f"{left[0]}::{left[1]}|{right[0]}::{right[1]}"
    return f"{right[0]}::{right[1]}|{left[0]}::{left[1]}"


def _load_baselines() -> list[dict]:
    """All ratified baselines, oldest → newest. Empty list if dir absent."""
    if not BASELINE_DIR.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(BASELINE_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload["_baseline_id"] = f.stem
        payload["_path"] = str(f.relative_to(REPO_ROOT))
        out.append(payload)
    out.sort(key=lambda p: p.get("ratified_at", ""))
    return out


def _current_matches(threshold: float = 0.7) -> list[dict]:
    """Live code_recurrence_promote.scan() output. Lazy import to avoid cycles."""
    try:
        from . import code_recurrence_promote as crp
        result = crp.scan(threshold=threshold)
        return result.get("clusters", []) if result.get("ok") else []
    except Exception:  # noqa: BLE001 — advisory layer, never crash
        return []


# ── Public API ───────────────────────────────────────────────────────────────
def ratify(
    reason: str,
    matches: list[dict] | None = None,
    threshold: float = 0.7,
    repo_root: Path | None = None,
) -> dict:
    """Snapshot current code recurrence matches as approved-canonical.

    `reason` is REQUIRED — explains why this baseline was ratified.

    `matches` optional — defaults to a live scan at `threshold`. Pass a
    curated subset to ratify some pairs (the others stay "open").

    Returns: `{ok, baseline_id, ratified_at, pair_count, code_corpus_sha, path}`.
    """
    if not reason or not reason.strip():
        return {"ok": False, "error": "ratify requires a non-empty `reason`."}
    _ensure_dir()
    if matches is None:
        matches = _current_matches(threshold=threshold)
    corpus_sha = _code_corpus_sha(repo_root=repo_root)
    short_sha = corpus_sha[:8] if corpus_sha else "nocache"
    ratified_at = _now_iso()
    baseline_id = f"{_today()}-{short_sha}"
    payload: dict[str, Any] = {
        "ratified_at": ratified_at,
        "reason": reason.strip(),
        "code_corpus_sha": corpus_sha,
        "threshold": threshold,
        "pair_count": len(matches),
        "matches": matches,
    }
    target = BASELINE_DIR / f"{baseline_id}.json"
    if target.exists():
        suffix = 2
        while True:
            cand = BASELINE_DIR / f"{baseline_id}-{suffix}.json"
            if not cand.exists():
                target = cand
                baseline_id = cand.stem
                break
            suffix += 1
    target.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return {
        "ok": True,
        "baseline_id": baseline_id,
        "ratified_at": ratified_at,
        "pair_count": len(matches),
        "code_corpus_sha": corpus_sha,
        "path": str(target.relative_to(REPO_ROOT)),
    }


def latest() -> dict | None:
    baselines = _load_baselines()
    return baselines[-1] if baselines else None


def list_baselines() -> list[dict]:
    return [
        {
            "baseline_id": b["_baseline_id"],
            "ratified_at": b.get("ratified_at"),
            "reason": b.get("reason"),
            "pair_count": b.get("pair_count"),
            "threshold": b.get("threshold"),
            "code_corpus_sha": (b.get("code_corpus_sha") or "")[:12],
            "path": b.get("_path"),
        }
        for b in _load_baselines()
    ]


def diff(against: str | None = None, threshold: float = 0.7) -> dict:
    """Compare current code recurrence matches against a baseline.

    `against` ∈ {None | "latest" | <baseline_id>}. Default: latest.
    `threshold` is the scan threshold for the current live state.

    Returns: `{ok, baseline_id?, code_corpus_drifted?, base_count,
              current_count, new_matches, resolved_matches, unchanged_count}`.

    `new_matches`: present in current, absent from baseline (NEW
    recurrence to review). `resolved_matches`: in baseline, gone from
    current — fixed OR corpus shifted (kb_corpus_drifted flags artifacts).
    """
    baselines = _load_baselines()
    if not baselines:
        current = _current_matches(threshold=threshold)
        return {
            "ok": True,
            "baseline_id": None,
            "base_count": 0,
            "current_count": len(current),
            "new_matches": current,
            "resolved_matches": [],
            "unchanged_count": 0,
            "message": "no baseline ratified — call code_ratify() to establish.",
        }
    if against in (None, "latest"):
        baseline = baselines[-1]
    else:
        baseline = next((b for b in baselines if b["_baseline_id"] == against), None)
        if baseline is None:
            return {
                "ok": False,
                "error": f"no baseline with id '{against}' — see list_baselines().",
            }
    base_matches = baseline.get("matches", [])
    current = _current_matches(threshold=threshold)
    base_keys = {_pair_key(m) for m in base_matches}
    cur_keys = {_pair_key(m) for m in current}
    new_matches = [m for m in current if _pair_key(m) not in base_keys]
    resolved = [m for m in base_matches if _pair_key(m) not in cur_keys]
    unchanged = len(cur_keys & base_keys)
    live_corpus = _code_corpus_sha()
    corpus_drifted = bool(
        live_corpus
        and baseline.get("code_corpus_sha")
        and live_corpus != baseline.get("code_corpus_sha")
    )
    return {
        "ok": True,
        "baseline_id": baseline["_baseline_id"],
        "ratified_at": baseline.get("ratified_at"),
        "code_corpus_drifted": corpus_drifted,
        "base_count": len(base_matches),
        "current_count": len(current),
        "new_matches": new_matches,
        "resolved_matches": resolved,
        "unchanged_count": unchanged,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.code_ratify",
        description=(
            "Snapshot current code recurrence matches as approved-canonical "
            "baseline. REQUIRED `reason`. Optional `matches` to ratify a "
            "curated subset. Persists durably to project-history/code-baselines/. "
            "Sister of noctus.dev.kb_ratify — same reasoning-driven "
            "ratification pattern applied to cross-product code recurrence "
            "findings. "
            "KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md."
        ),
    )
    def _ratify(reason: str, matches: list[dict] | None = None,
                threshold: float = 0.7) -> dict:
        return ratify(reason, matches=matches, threshold=threshold)

    @server.tool(
        name="noctus.dev.code_baseline_diff",
        description=(
            "Compare current code recurrence matches against a ratified "
            "baseline. Returns new_matches (NEW recurrence to review), "
            "resolved_matches (gone now), unchanged_count, and "
            "code_corpus_drifted (True if the code corpus shifted since "
            "ratification → resolved may be artifacts). Use INSTEAD OF raw "
            "code_recurrence_scan when a baseline exists — filters out "
            "previously-reviewed pairs so the signal stays sharp."
        ),
    )
    def _diff(against: str | None = None, threshold: float = 0.7) -> dict:
        return diff(against=against, threshold=threshold)

    @server.tool(
        name="noctus.dev.code_baseline_list",
        description=(
            "Chronological summary of every ratified code-recurrence "
            "baseline — baseline_id, ratified_at, reason, pair_count, "
            "threshold, code_corpus_sha."
        ),
    )
    def _list() -> list[dict]:
        return list_baselines()


__all__ = [
    "BASELINE_DIR",
    "ratify",
    "latest",
    "list_baselines",
    "diff",
    "register",
]

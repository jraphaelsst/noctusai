"""KB baseline — ratified-canonical layer over the owns_kb validation signal.

Why this exists
    The vector signal (`kb_validate_owns_kb` from kb-vector-search) flags
    docs whose semantic centroid is closer to another agent than to their
    declared owner. Each run produces a list of "potentially mis-owned"
    findings. Some are real (fix the ownership), some are noise (KB
    structure is fine, vector just happens to score that way).

    Without a ratification mechanism, every run re-surfaces the SAME
    false positives forever, drowning the signal. The user mandate
    (2026-05-26 W2-E7): *"evaluate canonical truth and evaluate if the
    signal makes sense or not"*. That's done case-by-case at review
    time → THIS module snapshots the result as a durable baseline. Next
    run, `kb_baseline_diff` shows only NEW drift, not previously-reviewed
    drift.

What it is, in one sentence
    A signal-vs-noise differentiator: ratify the current owns_kb
    validation findings as approved-canonical; subsequent runs report
    deltas against that baseline rather than the full raw output.

How it composes with `vector_calibration`
    `vector_calibration` reasons about THRESHOLDS (numbers that need
    tuning). `kb_baseline` reasons about RATIFIED FINDINGS (specific
    cases reviewed). Both are reasoning-driven, not auto-tuning.

Storage
    Baselines live as JSON files under `project-history/kb-baselines/`
    — durable, committed, append-only. Each file is a snapshot:
    `{ratified_at, reason, kb_corpus_sha, finding_count, findings: [...]}`.
    Filename: `YYYY-MM-DD-<short_corpus_sha>.json` (corpus-sha is the
    primary key — different corpus state ⇒ different baseline).

Keeper
    `check_kb_semantic_drift` — severity `warning`. Fires when:
      - Current validation has findings AND no baseline exists (suggest
        ratification).
      - Current validation diverges from latest baseline by more than
        `_DRIFT_THRESHOLD` NEW findings.

KB § CONTEXT/PATTERNS/common/vector-baseline.md.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import REPO_ROOT


# ── Paths ────────────────────────────────────────────────────────────────────
BASELINE_DIR = REPO_ROOT / "project-history" / "kb-baselines"

# How many NEW findings (vs. latest baseline) constitute "drift worth flagging".
_DRIFT_THRESHOLD = 5


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_dir() -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)


def _kb_corpus_sha(repo_root: Path | None = None) -> str:
    """Hash of every KB markdown file's content. Identifies "the corpus
    state at ratification time" — different corpus ⇒ different baseline.

    Deterministic by sorted-relative-path; content-hash, not mtime."""
    root = repo_root or REPO_ROOT
    kb_dir = root / "KNOWLEDGE-BASE"
    if not kb_dir.is_dir():
        return ""
    h = hashlib.sha256()
    for md in sorted(kb_dir.rglob("*.md")):
        if not md.is_file():
            continue
        h.update(str(md.relative_to(kb_dir)).encode())
        h.update(b"\x00")
        try:
            h.update(md.read_bytes())
        except OSError:
            continue
        h.update(b"\x00\x00")
    return h.hexdigest()


def _finding_key(finding: dict) -> str:
    """Stable identity for a finding — what makes two findings 'the same'.

    Path + current_owner + suggested_owner. We deliberately EXCLUDE the
    raw scores (they fluctuate per refresh) so a finding stays 'the same
    case' even when its drift score shifts slightly."""
    return f"{finding.get('path', '')}|{finding.get('current_owner', '')}|{finding.get('suggested_owner', '')}"


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


def _current_findings() -> list[dict]:
    """Live owns_kb validation findings. Lazy import to avoid cycles."""
    try:
        from . import kb_embeddings as kbe
        return kbe.kb_validate_owns_kb()
    except Exception:  # noqa: BLE001 — advisory layer, never crash
        return []


# ── Public API ───────────────────────────────────────────────────────────────
def ratify(
    reason: str,
    findings: list[dict] | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Snapshot the current owns_kb validation findings as approved canonical.

    `reason` is REQUIRED — the human-readable note explaining why this
    baseline was ratified. Future-us reads it to understand the decision.

    `findings` optional — if omitted, runs the live validation. Passing
    in a curated subset is supported (architect ratifies SOME findings,
    not all).

    Returns: `{ok, baseline_id, ratified_at, finding_count, kb_corpus_sha, path}`.
    """
    if not reason or not reason.strip():
        return {"ok": False, "error": "ratify requires a non-empty `reason`."}
    _ensure_dir()
    if findings is None:
        findings = _current_findings()
    corpus_sha = _kb_corpus_sha(repo_root=repo_root)
    short_sha = corpus_sha[:8] if corpus_sha else "nocorpus"
    ratified_at = _now_iso()
    baseline_id = f"{_today()}-{short_sha}"
    payload: dict[str, Any] = {
        "ratified_at": ratified_at,
        "reason": reason.strip(),
        "kb_corpus_sha": corpus_sha,
        "finding_count": len(findings),
        "findings": findings,
    }
    target = BASELINE_DIR / f"{baseline_id}.json"
    # If a baseline with the SAME corpus_sha exists, append a suffix so we
    # don't silently overwrite a prior ratification (history preserved).
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
        "finding_count": len(findings),
        "kb_corpus_sha": corpus_sha,
        "path": str(target.relative_to(REPO_ROOT)),
    }


def latest() -> dict | None:
    """Most-recent baseline (by ratified_at) or None if no baselines exist."""
    baselines = _load_baselines()
    return baselines[-1] if baselines else None


def list_baselines() -> list[dict]:
    """Chronological summary of every ratified baseline."""
    return [
        {
            "baseline_id": b["_baseline_id"],
            "ratified_at": b.get("ratified_at"),
            "reason": b.get("reason"),
            "finding_count": b.get("finding_count"),
            "kb_corpus_sha": (b.get("kb_corpus_sha") or "")[:12],
            "path": b.get("_path"),
        }
        for b in _load_baselines()
    ]


def diff(against: str | None = None) -> dict:
    """Compare current owns_kb validation against a baseline.

    `against` ∈ {None | "latest" | <baseline_id>}. Default: latest.

    Returns:
      `{ok, baseline_id?, kb_corpus_drifted?, base_count, current_count,
        new_findings: [...], resolved_findings: [...], unchanged_count}`.

    - `new_findings`: present in current, absent from baseline (NEW drift
      since ratification — these are what humans should review next).
    - `resolved_findings`: present in baseline, absent from current —
      either the issue was fixed OR the vector signal moved.
    - `kb_corpus_drifted`: True if the live kb_corpus_sha differs from
      the baseline's. When True, "resolved" findings might be artifacts
      of changed corpus, not real fixes.
    """
    baselines = _load_baselines()
    if not baselines:
        current = _current_findings()
        return {
            "ok": True,
            "baseline_id": None,
            "base_count": 0,
            "current_count": len(current),
            "new_findings": current,
            "resolved_findings": [],
            "unchanged_count": 0,
            "message": "no baseline ratified — current findings are all 'new' by definition. Call kb_ratify() to establish.",
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
    base_findings = baseline.get("findings", [])
    current = _current_findings()
    base_keys = {_finding_key(f) for f in base_findings}
    cur_keys = {_finding_key(f) for f in current}
    new_findings = [f for f in current if _finding_key(f) not in base_keys]
    resolved = [f for f in base_findings if _finding_key(f) not in cur_keys]
    unchanged = len(cur_keys & base_keys)
    live_corpus = _kb_corpus_sha()
    corpus_drifted = bool(
        live_corpus and baseline.get("kb_corpus_sha") and live_corpus != baseline.get("kb_corpus_sha")
    )
    return {
        "ok": True,
        "baseline_id": baseline["_baseline_id"],
        "ratified_at": baseline.get("ratified_at"),
        "kb_corpus_drifted": corpus_drifted,
        "base_count": len(base_findings),
        "current_count": len(current),
        "new_findings": new_findings,
        "resolved_findings": resolved,
        "unchanged_count": unchanged,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.kb_ratify",
        description=(
            "Snapshot the current owns_kb validation findings as approved "
            "canonical baseline. REQUIRED `reason` argument explains why "
            "this ratification is being made (future-us reads it to "
            "understand the decision). Optional `findings` argument lets "
            "you ratify a curated subset; default runs the live validation. "
            "Persists durably to project-history/kb-baselines/. Sibling of "
            "noctus.dev.vector_calibration_decide — both are reasoning-driven "
            "ratification tools, not auto-tuners. "
            "KB § CONTEXT/PATTERNS/common/vector-baseline.md."
        ),
    )
    def _ratify(reason: str, findings: list[dict] | None = None) -> dict:
        return ratify(reason, findings=findings)

    @server.tool(
        name="noctus.dev.kb_baseline_diff",
        description=(
            "Compare current owns_kb validation against a ratified baseline. "
            "Returns new_findings (NEW drift to review), resolved_findings "
            "(present in baseline, absent now), unchanged_count, and "
            "kb_corpus_drifted (True if the KB itself shifted since "
            "ratification → resolved findings may be artifacts). Use this "
            "INSTEAD OF raw kb_validate_owns_kb when a baseline exists — "
            "filters out previously-reviewed drift so the signal stays sharp."
        ),
    )
    def _diff(against: str | None = None) -> dict:
        return diff(against=against)

    @server.tool(
        name="noctus.dev.kb_baseline_list",
        description=(
            "Chronological summary of every ratified baseline — baseline_id, "
            "ratified_at, reason, finding_count, kb_corpus_sha. Read-only."
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

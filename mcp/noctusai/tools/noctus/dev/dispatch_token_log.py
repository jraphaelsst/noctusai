"""dispatch_token_log — manual per-dispatch token-budget logging.

Why this exists
    The original diagnostic wanted automatic per-dispatch token tracking:
    "per-dispatch tokens consumed, time-to-completion, did it land?"

    Claude Code's harness does NOT expose dispatch lifecycle hooks we
    can attach to. Automatic logging requires harness-side support we
    don't control.

    This module ships the MANUAL log path: the architect (after each
    dispatch) logs the slug + duration + estimated tokens + outcome.
    Trend analysis is the architect's responsibility for now; when the
    harness exposes hooks, swap the manual call for an automatic one.

What it logs
    Each entry: ts, slug, agent, duration_minutes, estimated_tokens,
    outcome (landed | drift-found | failed | escalated), notes.

Where it lives
    `project-history/dispatch-budget.ndjson` (committed; trend history
    is shared methodology signal).

Status
    Manual-instrument path. The automatic path is a future enhancement
    deferred until harness exposes session lifecycle hooks.

KB § CONTEXT/PATTERNS/common/dispatch-token-log.md.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


VALID_OUTCOMES = frozenset({"landed", "drift-found", "failed", "escalated"})

# Slice-scoring rubric (versioned: a weight change ships as RUBRIC_V2, never an
# in-place edit — old rows keep their `rubric_version` and stay comparable).
# Each criterion is scored 0-4; q_weighted = sum(weight * q) (a 0-4 scale).
RUBRIC_V1: dict[str, Any] = {
    "version": "v1",
    "scale": (0, 4),
    "weights": {
        "Q1": 0.25,  # correctness
        "Q2": 0.20,  # design
        "Q3": 0.15,  # tests
        "Q4": 0.15,  # maintainability
        "Q5": 0.10,  # security
        "Q6": 0.05,  # methodology
        "Q7": 0.10,  # integration-rework
    },
    "names": {
        "Q1": "correctness", "Q2": "design", "Q3": "tests",
        "Q4": "maintainability", "Q5": "security", "Q6": "methodology",
        "Q7": "integration-rework",
    },
}
RUBRICS: dict[str, dict[str, Any]] = {"v1": RUBRIC_V1}
SLICE_SCORES_LEDGER = "slice-scores.ndjson"
REWORK_SEVERITIES = ("blocker", "major", "minor")


def _ledger_path() -> Path:
    # LEDGER_ROOT (never REPO_ROOT): repo-global append-only ledger — must
    # land in the PRIMARY checkout even when the MCP server booted with
    # cwd inside a worktree. See workspace.get_ledger_root() docstring.
    from settings import LEDGER_ROOT
    return LEDGER_ROOT / "project-history" / "dispatch-budget.ndjson"


def _slice_scores_path() -> Path:
    from settings import LEDGER_ROOT
    return LEDGER_ROOT / "project-history" / SLICE_SCORES_LEDGER


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_completion(
    slug: str,
    agent: str,
    duration_minutes: float,
    estimated_tokens: int | None = None,
    outcome: str = "landed",
    notes: str | None = None,
    score: dict[str, Any] | None = None,
    engineer_return: str | None = None,
    ai_logger: Callable[..., dict] | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Log a completed dispatch.

    Args:
      slug: worktree slug / branch name.
      agent: specialist name.
      duration_minutes: wall-clock duration in minutes (architect-observed).
      estimated_tokens: optional token estimate (sum of brief + return + any
        intermediate work; architect's best guess).
      outcome: 'landed' | 'drift-found' | 'failed' | 'escalated'.
      notes: optional free-form notes.
      score: optional slice-score payload (see `build_score_row`); also
        appends a row to `slice-scores.ndjson` (result key `score_row`).
      ai_logger: injectable auto-improvement logger (default
        `auto_improvement.log_entry`) used for footer lines.
      publish: False spools the slice-score row locally (no push to
        origin/ledgers) until `ledger_store action='flush'`.
      engineer_return: optional raw engineer return text. Linted for the
        two-leg footer (missing footer -> refusal result, nothing written);
        each `drift-found:` / `scoped-improvement:` line is logged to the
        auto-improvement ledger and its ts stored in the score row's
        `drifts[]` / `improvements[]` `ai_ts`.

    Returns: `{ok, entry, ledger_path}` (+ `score_row`, `score_store`).
    """
    if outcome not in VALID_OUTCOMES:
        return {
            "ok": False,
            "error": f"outcome must be one of {sorted(VALID_OUTCOMES)}; got {outcome!r}",
        }
    if not slug or not slug.strip():
        return {"ok": False, "error": "slug is required"}
    if duration_minutes < 0:
        return {"ok": False, "error": "duration_minutes must be >= 0"}
    score_row: dict[str, Any] | None = None
    if score is not None or engineer_return is not None:
        if score is None:
            return {"ok": False, "error": "engineer_return requires score= (the row it enriches)"}
        built = build_score_row(slug.strip(), agent, score, engineer_return=engineer_return,
                                ai_logger=ai_logger)
        if not built.get("ok"):
            return built
        score_row = built["row"]
    entry = {
        "ts": _now_iso(),
        "slug": slug.strip(),
        "agent": agent,
        "duration_minutes": float(duration_minutes),
        "estimated_tokens": int(estimated_tokens) if estimated_tokens is not None else None,
        "outcome": outcome,
        "notes": notes,
    }
    # Since 2026-09-24 the ledger lives on the orphan origin/ledgers branch
    # (`_ledger_store`, KB § PATTERNS/common/ledger-store.md); reads are the
    # S2 dual-read (origin/ledgers ∪ the legacy dev copy).
    path = _ledger_path()
    from ._ledger_store import append_rows  # noqa: PLC0415 — keep import-time light
    try:
        store = append_rows(path.name, path, [entry], message=f"dispatch-completion: {agent} on {slug}")
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"write failed: {str(e)[:200]}"}
    try:
        from settings import LEDGER_ROOT
        rel = str(path.relative_to(LEDGER_ROOT))
    except (ImportError, ValueError):
        rel = str(path)
    # `store.status == 'pending'` ⇒ the row is durably spooled, not yet on
    # origin/ledgers — surfaced, never hidden.
    result = {"ok": True, "entry": entry, "ledger_path": rel, "store": store}
    if score_row is not None:
        try:
            sp = _slice_scores_path()
            result["score_store"] = append_rows(
                sp.name, sp, [score_row], message=f"slice-score: {agent} on {slug}", publish=publish)
            result["score_row"] = score_row
        except (OSError, ValueError) as e:
            return {**result, "ok": False, "error": f"score write failed: {str(e)[:200]}"}
    return result


# ── slice scores ─────────────────────────────────────────────────────────────
def compute_q_weighted(q: dict[str, Any], rubric_version: str = "v1") -> float | None:
    """Weighted score on the 0-4 scale; None if any criterion is missing."""
    weights = RUBRICS[rubric_version]["weights"]
    if any(q.get(k) is None for k in weights):
        return None
    return round(sum(w * float(q[k]) for k, w in weights.items()), 4)


_PATH_RE = re.compile(r"[\w./-]+/[\w.-]+\.[A-Za-z]{1,5}")
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*\S)\s*$")


def parse_footer(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract bullet lines of the two footer sections as {text, target}."""
    from .engineer_output_linter import _extract_section  # noqa: PLC0415
    out: dict[str, list[dict[str, Any]]] = {"drifts": [], "improvements": []}
    for header, key in (("drift-found", "drifts"), ("scoped-improvement", "improvements")):
        body = _extract_section(text, header)
        if not body:
            continue
        for ln in body.splitlines():
            m = _BULLET_RE.match(ln)
            if not m:
                continue
            t = m.group(1).strip()
            pm = _PATH_RE.search(t)
            out[key].append({"text": t, "target": pm.group(0) if pm else None})
    return out


def _validate_score(slug: str, agent: str, sc: dict[str, Any]) -> str | None:
    if not agent or not str(agent).strip():
        return "agent is required"
    for f in ("model",):
        if not sc.get(f) or not str(sc[f]).strip():
            return f"score.{f} is required"
    ver = sc.get("rubric_version", "v1")
    if ver not in RUBRICS:
        return f"unknown rubric_version {ver!r}; known: {sorted(RUBRICS)}"
    q = sc.get("q")
    if not isinstance(q, dict):
        return "score.q must be a dict Q1..Q7 -> number|null"
    weights = RUBRICS[ver]["weights"]
    for k, v in q.items():
        if k not in weights:
            return f"score.q has unknown criterion {k!r}"
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 4):
            return f"score.q[{k}] must be within 0-4 or null; got {v!r}"
    sev = sc.get("rework_severity") or {}
    if not isinstance(sev, dict) or any(k not in REWORK_SEVERITIES for k in sev):
        return f"score.rework_severity keys must be within {REWORK_SEVERITIES}"
    for f in ("tokens", "tool_uses", "rework_commits", "scope_changes"):
        v = sc.get(f)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            return f"score.{f} must be a non-negative int or null"
    for f in ("wall_s_measured", "wall_s_self_reported"):
        v = sc.get(f)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            return f"score.{f} must be a non-negative number or null"
    return None


def build_score_row(
    slug: str, agent: str, sc: dict[str, Any], *, engineer_return: str | None = None,
    ai_logger: Callable[..., dict] | None = None,
) -> dict[str, Any]:
    """Validate + assemble one `slice-scores.ndjson` row (no write).

    Returns `{ok, row}` or `{ok: False, error | refused}`. With
    `engineer_return`, the footer is linted (refusal if absent) and each
    drift/improvement line is logged to auto-improvement (side effect).
    """
    err = _validate_score(slug, agent, sc)
    if err:
        return {"ok": False, "error": err}
    ver = sc.get("rubric_version", "v1")
    weights = RUBRICS[ver]["weights"]
    q = {k: (None if sc["q"].get(k) is None else float(sc["q"][k])) for k in weights}
    drifts = [dict(d) for d in sc.get("drifts") or []]
    improvements = [dict(d) for d in sc.get("improvements") or []]
    if engineer_return is not None:
        from .engineer_output_linter import lint_return  # noqa: PLC0415
        lint = lint_return(engineer_return)
        if lint["missing"]:
            return {"ok": False, "refused": "missing-footer", "lint": lint,
                    "error": f"engineer return lacks footer section(s): {lint['missing']}"}
        parsed = parse_footer(engineer_return)
        if ai_logger is None:
            from .auto_improvement import log_entry as ai_logger  # noqa: PLC0415
        for key, kind in (("drifts", "drift"), ("improvements", "improvement")):
            for item in parsed[key]:
                r = ai_logger(
                    scope="scoped", kind=kind, target=item["target"] or "*",
                    description=item["text"], agent=agent,
                    source_ref=f"slice:{slug}",
                    resolve_when="manual:engineer-footer triage")
                item["ai_ts"] = (r.get("entry") or {}).get("ts") if r.get("ok") else None
                (drifts if key == "drifts" else improvements).append(item)
    row = {
        "ts": _now_iso(),
        "slug": slug,
        "branch": sc.get("branch"),
        "sha": sc.get("sha"),
        "agent": str(agent).strip(),
        "model": str(sc["model"]).strip(),
        "planner_model": sc.get("planner_model"),
        "rubric_version": ver,
        "q": q,
        "q_weighted": compute_q_weighted(q, ver),
        "tokens": sc.get("tokens"),
        "tool_uses": sc.get("tool_uses"),
        "wall_s_measured": sc.get("wall_s_measured"),
        "wall_s_self_reported": sc.get("wall_s_self_reported"),
        "first_pass": bool(sc.get("first_pass", False)),
        "rework_commits": int(sc.get("rework_commits") or 0),
        "rework_severity": {k: int((sc.get("rework_severity") or {}).get(k, 0)) for k in REWORK_SEVERITIES},
        "scope_changes": int(sc.get("scope_changes") or 0),
        "drifts": [{"text": d.get("text"), "target": d.get("target"), "ai_ts": d.get("ai_ts")} for d in drifts],
        "improvements": [{"text": d.get("text"), "target": d.get("target"), "ai_ts": d.get("ai_ts")} for d in improvements],
        "notes": sc.get("notes"),
    }
    return {"ok": True, "row": row}


def summary(
    agent: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Aggregate dispatch budget rows.

    Args:
      agent: filter to one specialist.
      since: ISO date prefix; rows with ts < since excluded.

    Returns:
      {
        ok: True,
        total_dispatches: int,
        by_outcome: {outcome: count},
        by_agent: {agent: {dispatches, avg_minutes, avg_tokens}},
        total_estimated_tokens: int,
        landed_rate: float,        # landed / total
      }
    """
    path = _ledger_path()
    from ._ledger_store import read_ledger_text  # noqa: PLC0415
    text, _store_err = read_ledger_text(path.name, path)
    if not text.strip():
        return {
            "ok": True, "total_dispatches": 0,
            "by_outcome": {}, "by_agent": {},
            "total_estimated_tokens": 0, "landed_rate": 0.0,
            "message": "no dispatches logged yet",
        }
    by_outcome: dict[str, int] = {}
    by_agent_raw: dict[str, list[dict]] = {}
    total_tokens = 0
    total = 0
    landed = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("ts", "")
        if since and ts < since:
            continue
        a = entry.get("agent", "?")
        if agent and a != agent:
            continue
        oc = entry.get("outcome", "?")
        total += 1
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        if oc == "landed":
            landed += 1
        tokens = entry.get("estimated_tokens") or 0
        total_tokens += tokens
        by_agent_raw.setdefault(a, []).append(entry)
    by_agent: dict[str, dict[str, Any]] = {}
    for a, entries in by_agent_raw.items():
        n = len(entries)
        durs = [e["duration_minutes"] for e in entries if e.get("duration_minutes") is not None]
        toks = [e["estimated_tokens"] for e in entries if e.get("estimated_tokens") is not None]
        by_agent[a] = {
            "dispatches": n,
            "avg_minutes": round(sum(durs) / len(durs), 2) if durs else None,
            "avg_tokens": int(sum(toks) / len(toks)) if toks else None,
        }
    return {
        "ok": True,
        "total_dispatches": total,
        "by_outcome": by_outcome,
        "by_agent": by_agent,
        "total_estimated_tokens": total_tokens,
        "landed_rate": round(landed / total, 3) if total else 0.0,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_log_completion",
        description=(
            "Manually log a completed dispatch: slug + agent + duration "
            "+ estimated tokens + outcome (landed|drift-found|failed|"
            "escalated) + optional notes; optional score={model, q{Q1..Q7 0-4}, "
            "tokens, wall_s_measured, ...} appends a slice-scores.ndjson row "
            "and optional engineer_return=<raw text> lints the footer + logs "
            "its drift/improvement lines to auto-improvement. Appends to "
            "project-history/dispatch-budget.ndjson. Manual instrumentation "
            "path; automatic harness-hook variant deferred until Claude "
            "Code exposes dispatch lifecycle. "
            "KB § CONTEXT/PATTERNS/common/dispatch-token-log.md."
        ),
    )
    def _log(slug: str, agent: str, duration_minutes: float,
             estimated_tokens: int | None = None,
             outcome: str = "landed",
             notes: str | None = None,
             score: dict | None = None,
             engineer_return: str | None = None,
             publish: bool = True) -> dict:
        return log_completion(slug, agent, duration_minutes,
                              estimated_tokens=estimated_tokens,
                              outcome=outcome, notes=notes,
                              score=score, engineer_return=engineer_return,
                              publish=publish)

    # NOTE (2026-08-31, tool-name-uniqueness triage): this module and
    # `dispatch_budget.py` BOTH declared `name="noctus.dev.dispatch_budget_summary"`.
    # `dispatch_budget.register` runs before `dispatch_token_log.register`
    # in `register_all` (`tools/noctus/dev/__init__.py`), so
    # `dispatch_budget.py`'s (agent, model, window_days) token-sum
    # aggregation — over the {agent, slug, input_tokens, output_tokens,
    # model, source_ref} entry shape written by `dispatch_budget_log` —
    # was the live tool; THIS (agent, since) outcome/duration aggregation
    # — over the DIFFERENT {slug, agent, duration_minutes,
    # estimated_tokens, outcome, notes} entry shape written by
    # `log_completion` above — was silently dead code registered a
    # second time under the same name. Both modules read/write the SAME
    # ledger file (`project-history/dispatch-budget.ndjson`) with two
    # DIFFERENT row schemas — a real, separate drift worth flagging (see
    # the delivery-note drift-found). Not behaviourally equivalent, so
    # renamed rather than deleted per the no-silent-behavior-change rule:
    # the winning name's semantics are untouched; this one keeps its
    # capability under an honest, non-colliding name that pairs with the
    # already-unique `noctus.dev.dispatch_log_completion` tool above.
    @server.tool(
        name="noctus.dev.dispatch_completion_summary",
        description=(
            "Aggregate dispatch-COMPLETION rows logged via "
            "`noctus.dev.dispatch_log_completion` (the {duration_minutes, "
            "estimated_tokens, outcome} manual-log shape — a DIFFERENT "
            "entry schema than `noctus.dev.dispatch_budget_summary`, "
            "though both read the same "
            "`project-history/dispatch-budget.ndjson` file). Returns "
            "total_dispatches, by_outcome counts, by_agent {dispatches, "
            "avg_minutes, avg_tokens}, total_estimated_tokens, "
            "landed_rate. Optional `agent=<name>` + `since=<ISO date>` "
            "filters."
        ),
    )
    def _sum(agent: str | None = None, since: str | None = None) -> dict:
        return summary(agent=agent, since=since)


__all__ = ["log_completion", "summary", "register", "RUBRIC_V1", "compute_q_weighted", "build_score_row", "parse_footer"]

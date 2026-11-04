"""``noctus.team.agent_metrics`` — per-(agent, model) slice-score trend.

Reads ``slice-scores.ndjson`` (written by
``noctus.dev.dispatch_log_completion score=``) and groups by (agent, model),
optionally bucketed by ISO week. KB § CONTEXT/PATTERNS/common/dispatch-token-log.md.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# $ per million tokens (in, out). Keyed by model-id substring, first match wins.
PRICES: dict[str, tuple[float, float]] = {
    "opus": (4.0, 20.0),
    "sonnet": (2.0, 10.0),
}
# The ledger stores a single `tokens` total, not an in/out split.
IN_SHARE = 0.9
SEVERITY_WEIGHT = {"blocker": 3, "major": 2, "minor": 1}
COST_NOTE = (
    "cost_usd_est assumes a 90/10 input/output split of total tokens "
    "(the ledger does not record the split); PRICES: Opus 5.5 $4/$20, "
    "Sonnet 5.5 $2/$10 per MTok."
)


def estimate_cost_usd(model: str, tokens: int | None) -> float | None:
    if not tokens:
        return None
    for key, (p_in, p_out) in PRICES.items():
        if key in (model or "").lower():
            return (tokens * IN_SHARE * p_in + tokens * (1 - IN_SHARE) * p_out) / 1_000_000
    return None


def _week(ts: str) -> str:
    try:
        y, w, _ = datetime.fromisoformat(ts).isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, TypeError):
        return "unknown"


def load_rows() -> list[dict[str, Any]]:
    from settings import LEDGER_ROOT
    from tools.noctus.dev._ledger_store import read_ledger_text
    name = "slice-scores.ndjson"
    text, _err = read_ledger_text(name, LEDGER_ROOT / "project-history" / name)
    rows = []
    for ln in text.splitlines():
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def _group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    qw = [r["q_weighted"] for r in rows if r.get("q_weighted") is not None]
    sev = sum(SEVERITY_WEIGHT[k] * int((r.get("rework_severity") or {}).get(k, 0))
              for r in rows for k in SEVERITY_WEIGHT)
    tokens = [r["tokens"] for r in rows if r.get("tokens")]
    costs = [c for r in rows if (c := estimate_cost_usd(r.get("model", ""), r.get("tokens"))) is not None]
    ratios = [r["wall_s_self_reported"] / r["wall_s_measured"] for r in rows
              if r.get("wall_s_self_reported") and r.get("wall_s_measured")]
    drifts = Counter(d["text"] for r in rows for d in r.get("drifts") or [] if d.get("text"))
    return {
        "n": n,
        "mean_q_weighted": _mean(qw),
        "first_pass_yield": round(sum(1 for r in rows if r.get("first_pass")) / n, 3),
        "rework_rate": round(sev / n, 3),
        "tokens_per_accepted_slice": int(sum(tokens) / len(tokens)) if tokens else None,
        "cost_usd_est": round(sum(costs), 4) if costs else None,
        "self_estimate_error_ratio": _mean(ratios),
        "top_drifts": [{"text": t, "count": c} for t, c in drifts.most_common(3)],
    }


def rollup(rows: list[dict[str, Any]], *, agent: str | None = None,
           by_week: bool = False) -> dict[str, Any]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        if agent and r.get("agent") != agent:
            continue
        key = (r.get("agent"), r.get("model")) + ((_week(r.get("ts", "")),) if by_week else ())
        groups.setdefault(key, []).append(r)
    out = []
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        entry = {"agent": key[0], "model": key[1]}
        if by_week:
            entry["week"] = key[2]
        entry.update(_group_stats(groups[key]))
        out.append(entry)
    return {"groups": out, "total_rows": sum(len(v) for v in groups.values()),
            "cost_note": COST_NOTE}


class AgentMetricsInput(BaseModel):
    name: str = Field(
        description=(
            "Agent name to filter slice-scores by (e.g. 'backend-engineer'); "
            "'*' or empty = every agent."
        )
    )
    scope: str | None = Field(
        default=None,
        description="Optional ISO date prefix; rows with ts before it are excluded.",
    )
    by_week: bool = Field(default=False, description="Bucket each (agent, model) group by ISO week.")


class AgentMetricsOutput(BaseModel):
    metrics: dict[str, Any] = Field(
        description=(
            "Per (agent, model[, week]) group: n, mean_q_weighted, first_pass_yield, "
            "rework_rate (severity-weighted 3/2/1 per slice), tokens_per_accepted_slice, "
            "cost_usd_est (90/10 in/out estimate), self_estimate_error_ratio, top_drifts."
        )
    )


def agent_metrics(name: str = "*", scope: str | None = None, by_week: bool = False) -> dict[str, Any]:
    rows = load_rows()
    if scope:
        rows = [r for r in rows if r.get("ts", "") >= scope]
    return rollup(rows, agent=None if name in ("", "*") else name, by_week=by_week)


def register(server) -> None:
    @server.tool(
        name="noctus.team.agent_metrics",
        description=(
            "Per-agent/per-model slice-score trend from slice-scores.ndjson: "
            "n, mean weighted quality (0-4), first-pass yield, rework rate, "
            "tokens per accepted slice, estimated cost USD (90/10 in/out "
            "split assumed), self-estimate error ratio, top recurring drifts. "
            "Optional by_week bucket. Read-only."
        ),
    )
    def _handler(payload: AgentMetricsInput) -> AgentMetricsOutput:
        return AgentMetricsOutput(
            metrics=agent_metrics(payload.name, payload.scope, payload.by_week))

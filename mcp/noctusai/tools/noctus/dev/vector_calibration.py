"""Vector calibration — reasoning-driven, NOT threshold-blind.

Codified 2026-05-26 (W2-E7) per user mandate:
  *"you are to evaluate when we have signals from the numbers. Evaluate
   canonical truth and evaluate if the signal makes sense or not. You
   are to do the reasoning, not only accept blindly what numbers tells
   us, we gotta understand why, where it came from. so then we will
   calibrate the params as we must to reach the level of confidence and
   reliability and efficiency we deserve."*

Philosophy
----------
This module is NOT an auto-tuner. It is an OBSERVATORY + REASONER:

  · Observatory: logs vector-system signals (search queries, cluster
    surfaces, neighbor lookups, validation flags) to a durable ledger
    so trends across sessions become visible.
  · Reasoner: cross-references signals against CANONICAL TRUTH (the
    manual owns_kb declarations, the auto-improvement.ndjson status
    progression, the human codification decisions) to evaluate
    *whether the signal makes sense* + surface reasoned recommendations.
  · Decision ledger: when the architect makes a calibration call
    (raise/lower threshold, switch chunking, etc.), it's recorded with
    *rationale*. Future sessions see WHY past calls were made.

The architect REVIEWS recommendations + makes the call. Numbers don't
auto-apply. The tool's job is to surface reasoning candidates the
human evaluates against context the tool can't fully see.

Surfaces (ndjson ledgers — sibling of auto-improvement.ndjson)
--------------------------------------------------------------
  project-history/vector-signals.ndjson      ← signal observation log
  project-history/vector-calibration.ndjson  ← calibration decision log

Both committed (durable audit trail). Schema in the respective KB doc.

KB § PATTERNS/common/vector-calibration.md.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import REPO_ROOT


# ── Paths ────────────────────────────────────────────────────────────────────
SIGNALS_PATH = REPO_ROOT / "project-history" / "vector-signals.ndjson"
DECISIONS_PATH = REPO_ROOT / "project-history" / "vector-calibration.ndjson"

# Allowed signal types — tracked for typo defense + future analyzer routing.
SIGNAL_TYPES = frozenset({
    "kb_search",              # query → top-K hits + scores
    "kb_neighbors",           # path → neighbor list + scores
    "kb_similar",             # text → similar chunks + scores
    "kb_validate_owns_kb",    # ownership flags surfaced
    "codification_radar",     # clusters surfaced + suggested promotions
    "code_search",            # (future, when code-embeddings ships)
    "code_recurrence",        # (future)
})

# Calibration parameters that have human-meaningful semantics.
KNOWN_PARAMS = frozenset({
    "similarity_threshold",
    "top_k",
    "min_score",
    "min_cluster_size",
    "max_chunk_chars",
    "chunking_strategy",
    "embedding_model",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Observatory: log signals + decisions ─────────────────────────────────────
def log_signal(
    signal_type: str,
    params: dict,
    result: dict,
    context: dict | None = None,
) -> dict:
    """Append a signal observation to vector-signals.ndjson.

    `params`: the tunable parameters used (e.g., `{"threshold": 0.75, "top_k": 5}`).
    `result`: the tool's output (or a summary — scores, sizes, counts).
    `context`: optional metadata (query text, agent, session, what the
    user did with the result if known).

    Returns `{ok, entry, ledger_path}`. Idempotent at the ndjson layer
    (just appends — no dedup; signals are meant to accumulate).
    """
    if signal_type not in SIGNAL_TYPES:
        return {
            "ok": False,
            "error": f"signal_type must be one of {sorted(SIGNAL_TYPES)}; got {signal_type!r}",
        }
    entry = {
        "ts": _now_iso(),
        "signal_type": signal_type,
        "params": params,
        "result": result,
        "context": context or {},
    }
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SIGNALS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        rel = str(SIGNALS_PATH.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(SIGNALS_PATH)
    return {"ok": True, "entry": entry, "ledger_path": rel}


def log_decision(
    signal_type: str,
    parameter: str,
    old_value: Any,
    new_value: Any,
    reasoning: str,
    evidence: dict | None = None,
) -> dict:
    """Append a calibration decision to vector-calibration.ndjson.

    `reasoning` is REQUIRED — the human's explanation of WHY this
    calibration call was made. Future sessions read this to understand
    decision provenance (the codebase-is-source-of-truth principle
    applied to tuning).

    `evidence`: optional structured pointers to signals / analyses that
    informed the decision.

    Returns `{ok, entry, ledger_path}`.
    """
    if signal_type not in SIGNAL_TYPES:
        return {"ok": False, "error": f"unknown signal_type {signal_type!r}"}
    if parameter not in KNOWN_PARAMS:
        return {"ok": False, "error": f"unknown parameter {parameter!r} (extend KNOWN_PARAMS first)"}
    if not reasoning or not reasoning.strip():
        return {"ok": False, "error": "reasoning is required — describe WHY this calibration call was made"}
    entry = {
        "ts": _now_iso(),
        "signal_type": signal_type,
        "parameter": parameter,
        "old_value": old_value,
        "new_value": new_value,
        "reasoning": reasoning,
        "evidence": evidence or {},
    }
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DECISIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        rel = str(DECISIONS_PATH.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(DECISIONS_PATH)
    return {"ok": True, "entry": entry, "ledger_path": rel}


def decisions_log(signal_type: str | None = None) -> list[dict]:
    """Read the calibration-decisions log. `signal_type` filter optional."""
    if not DECISIONS_PATH.exists():
        return []
    out: list[dict] = []
    for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if signal_type and entry.get("signal_type") != signal_type:
            continue
        out.append(entry)
    return out


# ── Reasoner: cross-reference signals vs canonical truth ─────────────────────
def _load_signals(signal_type: str | None = None, since: str | None = None) -> list[dict]:
    """Load + filter signals from the ndjson."""
    if not SIGNALS_PATH.exists():
        return []
    out: list[dict] = []
    for line in SIGNALS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if signal_type and entry.get("signal_type") != signal_type:
            continue
        if since and entry.get("ts", "") < since:
            continue
        out.append(entry)
    return out


def _score_distribution(scores: list[float]) -> dict:
    """Basic histogram + summary statistics for a list of similarity scores.

    Returns a structured summary the analyzer can REASON about:
      - count, mean, median, stdev
      - quantiles (q25, q75, q90)
      - histogram (5 bins from 0.0 to 1.0)
    """
    if not scores:
        return {"count": 0}
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    def quantile(p: float) -> float:
        if n == 1:
            return sorted_scores[0]
        idx = int(p * (n - 1))
        return sorted_scores[idx]
    histogram = [0] * 5
    for s in scores:
        bucket = min(int(s * 5), 4)
        histogram[bucket] += 1
    return {
        "count": n,
        "mean": round(statistics.mean(scores), 4),
        "median": round(statistics.median(scores), 4),
        "stdev": round(statistics.stdev(scores), 4) if n > 1 else 0.0,
        "q25": round(quantile(0.25), 4),
        "q75": round(quantile(0.75), 4),
        "q90": round(quantile(0.90), 4),
        "histogram_0_to_1_in_5_bins": histogram,
    }


def _reason_about_threshold(
    signal_type: str,
    current_threshold: float | None,
    score_dist: dict,
    canonical_alignment: dict,
) -> list[str]:
    """Generate REASONING (not numeric recommendations) about whether the
    current threshold makes sense given the observed distribution + the
    canonical-truth alignment.

    Each line in the returned list is a discrete reasoning point — the
    architect reads + judges. The tool surfaces hypotheses; the human
    evaluates.
    """
    reasoning: list[str] = []
    n = score_dist.get("count", 0)
    if n == 0:
        return ["No observations logged yet for this signal type. Run the tool a few times, then re-analyze."]
    if n < 10:
        reasoning.append(
            f"Only {n} observations — too few for statistical reasoning. "
            "Observe more (≥30 recommended) before calibrating; current "
            "distribution stats are advisory not authoritative."
        )

    if current_threshold is not None:
        mean = score_dist["mean"]
        q25 = score_dist["q25"]
        q75 = score_dist["q75"]
        # Hypothesis 1: threshold sits inside the high-density region → likely too inclusive
        if current_threshold < q25:
            reasoning.append(
                f"Threshold ({current_threshold}) is BELOW the 25th percentile ({q25}) of observed "
                f"scores. ⇒ Most observations PASS the threshold — likely yielding many low-precision "
                f"hits. Reasoning candidate: try raising toward {q75} (75th percentile) and observe "
                f"whether high-value hits survive. WHY: a threshold that doesn't discriminate isn't a "
                f"threshold; it's the floor."
            )
        elif current_threshold > q75:
            reasoning.append(
                f"Threshold ({current_threshold}) is ABOVE the 75th percentile ({q75}) of observed "
                f"scores. ⇒ Most observations FAIL the threshold — likely missing useful hits. "
                f"Reasoning candidate: try lowering toward the median ({score_dist['median']}) and "
                f"observe whether useful results emerge. WHY: a threshold the data rarely crosses is "
                f"likely tuned for a different distribution than what you actually have."
            )
        else:
            reasoning.append(
                f"Threshold ({current_threshold}) sits between Q25 ({q25}) and Q75 ({q75}) of the "
                f"observed distribution. ⇒ Threshold is in the discriminating range. Validate via "
                f"canonical-truth alignment (see below) before adjusting."
            )

    # Histogram shape reasoning.
    hist = score_dist.get("histogram_0_to_1_in_5_bins", [])
    if hist:
        top_bin = max(range(5), key=lambda i: hist[i])
        if hist[0] > sum(hist) * 0.6:
            reasoning.append(
                "60%+ of scores cluster in the 0.0-0.2 band ⇒ likely most queries are returning "
                "weakly-related results. Hypothesis: the corpus content doesn't match query intent "
                "(consider re-chunking strategy OR the corpus is the wrong domain for these queries)."
            )
        if hist[4] > sum(hist) * 0.5:
            reasoning.append(
                "50%+ of scores in the 0.8-1.0 band ⇒ matches are extremely confident. Hypothesis: "
                "either you're routinely querying for exact known content (low signal value — grep "
                "would work) OR the corpus has near-duplicate chunks. Investigate before lowering "
                "threshold to filter."
            )

    # Canonical-truth alignment.
    aligned = canonical_alignment.get("aligned_count", 0)
    diverged = canonical_alignment.get("diverged_count", 0)
    if aligned + diverged > 0:
        rate = aligned / (aligned + diverged)
        reasoning.append(
            f"Canonical-truth alignment: {aligned}/{aligned + diverged} signals matched canonical "
            f"({rate:.0%}). {'GOOD — the vector signal is tracking truth.' if rate > 0.7 else 'WEAK — vector signals frequently diverge from canonical decisions; threshold/chunking likely off.'}"
        )

    if not reasoning:
        reasoning.append("Distribution looks reasonable; no strong calibration signal. Continue observing.")
    return reasoning


def analyze(
    signal_type: str | None = None,
    since: str | None = None,
) -> dict:
    """Produce a structured analysis with REASONING about whether current
    vector calibration is appropriate. The architect reviews + makes
    calibration calls via `log_decision`.

    `signal_type=None` analyzes ALL signal types separately. `since` is
    an ISO date prefix — entries with `ts < since` are excluded.

    Returns a structured report:
      {ok, analyses: [{signal_type, observation_count, score_distribution,
                       canonical_alignment, reasoning: [str],
                       recommended_next_step}],
       generated_at, decisions_history_count}
    """
    signals = _load_signals(signal_type=signal_type, since=since)
    types_observed = sorted({s["signal_type"] for s in signals}) if signals else (
        [signal_type] if signal_type else []
    )

    analyses: list[dict] = []
    for stype in types_observed:
        type_signals = [s for s in signals if s["signal_type"] == stype]
        # Extract scores from the results — every vector tool returns
        # similarity scores, but the result shape varies. Best-effort.
        scores: list[float] = []
        thresholds_used: list[float] = []
        for sig in type_signals:
            result = sig.get("result", {})
            params = sig.get("params", {})
            # Score collection paths (varies by signal_type).
            if isinstance(result, dict):
                # kb_search: result has "hits" or top-level "score"
                hits = result.get("hits") or result.get("clusters") or []
                if isinstance(hits, list):
                    for h in hits:
                        if isinstance(h, dict) and "score" in h:
                            try:
                                scores.append(float(h["score"]))
                            except (TypeError, ValueError):
                                pass
                if "score" in result:
                    try:
                        scores.append(float(result["score"]))
                    except (TypeError, ValueError):
                        pass
            # Threshold from params.
            for k in ("threshold", "similarity_threshold", "min_score"):
                if k in params:
                    try:
                        thresholds_used.append(float(params[k]))
                    except (TypeError, ValueError):
                        pass

        # Canonical-truth alignment placeholder — real logic depends on
        # signal type; for v1 we surface the structure + a TODO note.
        # Future: cross-reference against owns_kb / auto-improvement
        # status progressions / human codification decisions.
        canonical_alignment = {
            "aligned_count": 0,
            "diverged_count": 0,
            "note": (
                "v1 — canonical-truth cross-reference not yet implemented per "
                "signal type. The framework is here; specific analyzers per "
                "signal_type land as follow-ups. For now, the architect "
                "reasons about scores + thresholds + the qualitative "
                "checks below."
            ),
        }
        score_dist = _score_distribution(scores)
        current_threshold = thresholds_used[-1] if thresholds_used else None

        reasoning = _reason_about_threshold(
            stype, current_threshold, score_dist, canonical_alignment
        )

        recommended_next_step = (
            "ADVISORY — review the reasoning lines, optionally validate "
            "by sampling specific signals (read source ndjson lines), "
            "make the call via `noctus.dev.vector_calibration_decide` "
            "with a `reasoning` argument."
        )

        analyses.append({
            "signal_type": stype,
            "observation_count": len(type_signals),
            "score_distribution": score_dist,
            "current_threshold_observed": current_threshold,
            "canonical_alignment": canonical_alignment,
            "reasoning": reasoning,
            "recommended_next_step": recommended_next_step,
        })

    return {
        "ok": True,
        "generated_at": _now_iso(),
        "analyses": analyses,
        "decisions_history_count": len(decisions_log(signal_type)),
        "since_filter": since,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.vector_signal_log",
        description=(
            "Observatory leg of vector calibration: log a signal "
            "observation (kb_search / codification_radar / kb_neighbors / "
            "etc.) to `project-history/vector-signals.ndjson`. Future "
            "calls to `vector_calibration_analyze` reason about the "
            "accumulated history. Reasoning-driven, NOT auto-tuning: "
            "humans make calibration calls."
        ),
    )
    def _log_signal(
        signal_type: str,
        params: dict,
        result: dict,
        context: dict | None = None,
    ) -> dict:
        return log_signal(signal_type, params, result, context=context)

    @server.tool(
        name="noctus.dev.vector_calibration_analyze",
        description=(
            "Reasoner leg of vector calibration: read accumulated "
            "vector-signals.ndjson, cross-reference against canonical "
            "truth, produce structured reasoning about whether current "
            "calibration is appropriate. Output includes score "
            "distribution, canonical-truth alignment, hypotheses about "
            "the data, and a recommended_next_step. The architect "
            "reviews + makes the call via `vector_calibration_decide`. "
            "Numbers don't auto-apply. KB § PATTERNS/common/vector-calibration.md."
        ),
    )
    def _analyze(signal_type: str | None = None, since: str | None = None) -> dict:
        return analyze(signal_type=signal_type, since=since)

    @server.tool(
        name="noctus.dev.vector_calibration_decide",
        description=(
            "Record a calibration decision with REQUIRED reasoning. "
            "Appends to `project-history/vector-calibration.ndjson`. "
            "`reasoning` describes WHY this calibration call was made — "
            "future sessions read this for decision provenance. "
            "`evidence` is optional structured pointers (specific signal "
            "rows, analysis outputs)."
        ),
    )
    def _decide(
        signal_type: str,
        parameter: str,
        old_value: Any,
        new_value: Any,
        reasoning: str,
        evidence: dict | None = None,
    ) -> dict:
        return log_decision(
            signal_type, parameter, old_value, new_value, reasoning, evidence=evidence
        )

    @server.tool(
        name="noctus.dev.vector_calibration_history",
        description=(
            "Read the calibration-decisions log. Optional "
            "`signal_type` filter. Returns the structured history of "
            "past tuning calls with rationale — useful when revisiting "
            "a parameter to remember why it was set to the current value."
        ),
    )
    def _history(signal_type: str | None = None) -> list[dict]:
        return decisions_log(signal_type=signal_type)


__all__ = [
    "SIGNAL_TYPES",
    "KNOWN_PARAMS",
    "SIGNALS_PATH",
    "DECISIONS_PATH",
    "log_signal",
    "log_decision",
    "decisions_log",
    "analyze",
    "register",
]

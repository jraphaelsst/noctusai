"""Baselines from the profile's OWN history + alerts relative to them.

SIMEC rule: "baselines come from the profile's own history, never universal
rules". A baseline is computed per window × comparable group (``group_by`` —
today: format) × indicator over ``ok`` readings, and only COUNTS once it has
the configured minimum sample. Alerts compare a reading against its own
group's baseline with a configured method + threshold; a group whose
baseline is insufficient produces no alert and is reported as such (never a
silent pass).

Percentiles use linear interpolation between closest ranks (Excel
``PERCENTILE.INC`` / numpy's default), so they match a spreadsheet check.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from noctusai_lib.domain.content_performance.calculator import ReadingResult, ReadingStatus
from noctusai_lib.domain.content_performance.config import AlertRuleSpec, PerformanceConfig

#: Group label for a reading without the grouping attribute.
NO_GROUP_VALUE = "(sem formato)"


def percentile_inc(sorted_values: Sequence[float], q: float) -> float:
    """Excel ``PERCENTILE.INC`` over an already-sorted, non-empty sequence."""
    if not sorted_values:
        raise ValueError("percentile of an empty sample")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def group_of(result: ReadingResult, config: PerformanceConfig) -> tuple[tuple[str, str], ...]:
    out = []
    for g in config.baseline.group_by:
        raw = getattr(result.reading, g, None)
        out.append((g, str(raw) if raw not in (None, "") else NO_GROUP_VALUE))
    return tuple(out)


@dataclass(frozen=True)
class BaselineStat:
    window: str
    group: tuple[tuple[str, str], ...]
    indicator: str
    n: int
    mean: Optional[float]
    median: Optional[float]
    p25: Optional[float]
    p75: Optional[float]
    sufficient: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window, "group": dict(self.group), "indicator": self.indicator,
            "n": self.n, "mean": self.mean, "median": self.median, "p25": self.p25,
            "p75": self.p75, "sufficient": self.sufficient,
        }


def compute_baselines(
    history: Sequence[ReadingResult], config: PerformanceConfig
) -> list[BaselineStat]:
    """One ``BaselineStat`` per (window, group, indicator) present in the
    ``ok`` history. Indicators the source cannot provide are skipped."""
    unavailable = config.unavailable_keys()
    buckets: dict[tuple[str, tuple, str], list[float]] = {}
    for r in history:
        if r.status is not ReadingStatus.OK:
            continue
        grp = group_of(r, config)
        for ind in config.baseline.indicators:
            if ind in unavailable:
                continue
            v = r.value(ind)
            key = (str(r.reading.window), grp, ind)
            buckets.setdefault(key, [])
            if v is not None:
                buckets[key].append(v)
    stats = []
    for (window, grp, ind), vals in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        vals = sorted(vals)
        n = len(vals)
        stats.append(BaselineStat(
            window=window, group=grp, indicator=ind, n=n,
            mean=(sum(vals) / n) if n else None,
            median=percentile_inc(vals, 0.5) if n else None,
            p25=percentile_inc(vals, 0.25) if n else None,
            p75=percentile_inc(vals, 0.75) if n else None,
            sufficient=n >= config.baseline.min_posts,
        ))
    return stats


@dataclass(frozen=True)
class Alert:
    rule: str
    indicator: str
    method: str
    threshold: float
    content_id: Optional[str]
    window: str
    group: tuple[tuple[str, str], ...]
    value: float
    direction: str  # "below" | "above"
    deviation: float  # relative (pct_from_median) or IQR units (outside_iqr)
    baseline_n: int
    baseline_median: Optional[float]
    baseline_p25: Optional[float]
    baseline_p75: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule, "indicator": self.indicator, "method": self.method,
            "threshold": self.threshold, "content_id": self.content_id, "window": self.window,
            "group": dict(self.group), "value": self.value, "direction": self.direction,
            "deviation": self.deviation, "baseline": {
                "n": self.baseline_n, "median": self.baseline_median,
                "p25": self.baseline_p25, "p75": self.baseline_p75,
            },
        }


@dataclass(frozen=True)
class NotEvaluated:
    rule: str
    window: str
    group: tuple[tuple[str, str], ...]
    reason: str  # "baseline_insuficiente" | "sem_baseline" | "mediana_zero" | "iqr_zero"
    baseline_n: int

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "window": self.window, "group": dict(self.group),
                "reason": self.reason, "baseline_n": self.baseline_n}


@dataclass(frozen=True)
class AlertEvaluation:
    fired: tuple[Alert, ...]
    not_evaluated: tuple[NotEvaluated, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"fired": [a.to_dict() for a in self.fired],
                "not_evaluated": [n.to_dict() for n in self.not_evaluated]}


def _check(rule: AlertRuleSpec, value: float, b: BaselineStat) -> tuple[Optional[str], float, Optional[str]]:
    """``(direction_fired | None, deviation, not_evaluable_reason | None)``."""
    assert b.median is not None and b.p25 is not None and b.p75 is not None
    if rule.method == "pct_from_median":
        if b.median == 0:
            return None, 0.0, "mediana_zero"
        dev = (value - b.median) / abs(b.median)
        hit_below = dev <= -rule.threshold
        hit_above = dev >= rule.threshold
    elif rule.method == "outside_iqr":
        iqr = b.p75 - b.p25
        if iqr == 0:
            return None, 0.0, "iqr_zero"
        if value < b.p25:
            dev = (value - b.p25) / iqr
        elif value > b.p75:
            dev = (value - b.p75) / iqr
        else:
            dev = 0.0
        hit_below = dev <= -rule.threshold
        hit_above = dev >= rule.threshold
    else:  # pragma: no cover — config validation forbids it
        raise ValueError(f"unknown alert method {rule.method!r}")
    if hit_below and rule.direction in ("below", "both"):
        return "below", dev, None
    if hit_above and rule.direction in ("above", "both"):
        return "above", dev, None
    return None, dev, None


def evaluate_alerts(
    period: Sequence[ReadingResult],
    baselines: Sequence[BaselineStat],
    config: PerformanceConfig,
) -> AlertEvaluation:
    index = {(b.window, b.group, b.indicator): b for b in baselines}
    fired: list[Alert] = []
    skipped: dict[tuple, NotEvaluated] = {}
    for r in period:
        if r.status is not ReadingStatus.OK:
            continue
        window = str(r.reading.window)
        grp = group_of(r, config)
        for rule in config.active_alerts:
            if rule.windows and window not in rule.windows:
                continue
            value = r.value(rule.indicator)
            if value is None:
                continue
            b = index.get((window, grp, rule.indicator))
            reason = None
            if b is None or b.n == 0:
                reason = "sem_baseline"
            elif not b.sufficient:
                reason = "baseline_insuficiente"
            if reason is None:
                assert b is not None
                direction, dev, reason = _check(rule, value, b)
                if direction is not None:
                    fired.append(Alert(
                        rule=rule.key, indicator=rule.indicator, method=rule.method,
                        threshold=rule.threshold, content_id=r.reading.content_id,
                        window=window, group=grp, value=value, direction=direction,
                        deviation=dev, baseline_n=b.n, baseline_median=b.median,
                        baseline_p25=b.p25, baseline_p75=b.p75,
                    ))
            if reason is not None:
                skipped.setdefault((rule.key, window, grp), NotEvaluated(
                    rule=rule.key, window=window, group=grp, reason=reason,
                    baseline_n=b.n if b is not None else 0,
                ))
    return AlertEvaluation(fired=tuple(fired), not_evaluated=tuple(skipped.values()))


__all__ = [
    "Alert",
    "AlertEvaluation",
    "BaselineStat",
    "NO_GROUP_VALUE",
    "NotEvaluated",
    "compute_baselines",
    "evaluate_alerts",
    "group_of",
    "percentile_inc",
]

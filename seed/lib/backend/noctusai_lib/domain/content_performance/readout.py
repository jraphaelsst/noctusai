"""One readout = panel for a period + baselines from the prior history +
alerts, stamped with the config that produced it.

The caller supplies ALL readings it has (period + history) and the period
bounds; the split is by publication date: the period is
``[period_start, period_end]``; the history is the ``lookback_days`` before
``period_start`` (exclusive), so new content is compared against the
profile's earlier content, never against itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from noctusai_lib.domain.content_performance.baseline import (
    AlertEvaluation,
    BaselineStat,
    compute_baselines,
    evaluate_alerts,
)
from noctusai_lib.domain.content_performance.calculator import (
    PanelCell,
    Reading,
    ReadingResult,
    ReadingStatus,
    compute_panel,
    evaluate_readings,
    status_counts,
)
from noctusai_lib.domain.content_performance.config import PerformanceConfig


def _published_on(r: Reading) -> date | None:
    p = r.published_at
    if p is None:
        return None
    return p.date() if isinstance(p, datetime) else p


def split_by_period(
    results: Sequence[ReadingResult],
    period_start: date,
    period_end: date,
    lookback_days: int,
) -> tuple[list[ReadingResult], list[ReadingResult]]:
    """``(period, history)`` by publication date. Readings with no
    publication date go to neither (they are ``incompleto`` anyway)."""
    if period_start > period_end:
        raise ValueError(f"period_start {period_start} > period_end {period_end}")
    history_start = period_start - timedelta(days=lookback_days)
    period, history = [], []
    for r in results:
        d = _published_on(r.reading)
        if d is None:
            continue
        if period_start <= d <= period_end:
            period.append(r)
        elif history_start <= d < period_start:
            history.append(r)
    return period, history


@dataclass(frozen=True)
class Readout:
    platform: str
    config_version: str
    config_fingerprint: str
    period_start: date
    period_end: date
    history_start: date
    readings: tuple[ReadingResult, ...]
    panel: dict[str, dict[str, PanelCell]]
    status_counts: dict[str, int]
    baselines: tuple[BaselineStat, ...]
    alerts: AlertEvaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "config_version": self.config_version,
            "config_fingerprint": self.config_fingerprint,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "history_start": self.history_start.isoformat(),
            "status_counts": dict(self.status_counts),
            "panel": {w: {k: c.to_dict() for k, c in col.items()} for w, col in self.panel.items()},
            "baselines": [b.to_dict() for b in self.baselines],
            "alerts": self.alerts.to_dict(),
            "readings": [r.to_dict() for r in self.readings],
        }


def compute_readout(
    readings: Sequence[Reading],
    config: PerformanceConfig,
    *,
    period_start: date,
    period_end: date,
) -> Readout:
    results = evaluate_readings(readings, config)
    period, history = split_by_period(
        results, period_start, period_end, config.baseline.lookback_days)
    baselines = compute_baselines(history, config)
    return Readout(
        platform=config.platform,
        config_version=config.version,
        config_fingerprint=config.fingerprint,
        period_start=period_start,
        period_end=period_end,
        history_start=period_start - timedelta(days=config.baseline.lookback_days),
        readings=tuple(r for r in period if r.status is not ReadingStatus.VAZIO),
        panel=compute_panel(period, config),
        status_counts=status_counts(period),
        baselines=tuple(baselines),
        alerts=evaluate_alerts(period, baselines, config),
    )


__all__ = ["Readout", "compute_readout", "split_by_period"]

"""Content performance — pure-domain calculator for social-content metrics
(the SIMEC method). Seed piece B3 of
``products/social-wiring/projects/marketing-intelligence/specs/phase0-audit.md``.

PURE: no database, no network, no clock. Products load readings from their
own collection, pick a config (defaults ⊕ org ⊕ profile overrides) and call
the functions here. The workbooks of the SIMEC 1.0 kit are the golden
reference (``tests/domain/content_performance/golden/``).

NOTHING HARDCODED (owner rule 2026-10-19): windows + tolerances, indicators,
panel lines, baseline look-back + minimum sample, alert thresholds (relative
to the profile's own baseline), which metrics the source provides, review
cadence and decision-validation period are all ``PerformanceConfig`` data.
Defaults ship as ``defaults/<platform>.json``. Every result carries the
config ``version`` + ``fingerprint``.

Platforms stay separate: each config is per platform (Instagram divides by
reach, TikTok by views); nothing compares across platforms.

Public surface:

Config:
    ``PerformanceConfig``, ``ConfigError``, ``config_from_dict``,
    ``default_config_dict``, ``load_default_config``, ``merge_overrides``
    (+ the ``*Spec`` value objects)

Calculator:
    ``Reading``, ``ReadingResult``, ``ReadingStatus``, ``Cell``,
    ``CellStatus``, ``PanelCell``, ``evaluate_readings``, ``compute_panel``,
    ``select_window_observation``, ``age_in_days``, ``status_counts``

Baselines + alerts:
    ``BaselineStat``, ``Alert``, ``NotEvaluated``, ``AlertEvaluation``,
    ``compute_baselines``, ``evaluate_alerts``, ``percentile_inc``

Readout:
    ``Readout``, ``compute_readout``, ``split_by_period``
"""
from __future__ import annotations

from noctusai_lib.domain.content_performance.baseline import (
    NO_GROUP_VALUE,
    Alert,
    AlertEvaluation,
    BaselineStat,
    NotEvaluated,
    compute_baselines,
    evaluate_alerts,
    group_of,
    percentile_inc,
)
from noctusai_lib.domain.content_performance.calculator import (
    Cell,
    CellStatus,
    PanelCell,
    Reading,
    ReadingResult,
    ReadingStatus,
    age_in_days,
    compute_panel,
    evaluate_readings,
    select_window_observation,
    status_counts,
)
from noctusai_lib.domain.content_performance.config import (
    ALERT_DIRECTIONS,
    ALERT_METHODS,
    INDICATOR_OPS,
    PANEL_AGGREGATES,
    AlertRuleSpec,
    BaselineSpec,
    CadenceSpec,
    ConfigError,
    IndicatorSpec,
    MetricSpec,
    PanelLineSpec,
    PerformanceConfig,
    ReviewCadenceSpec,
    WindowSpec,
    config_from_dict,
    default_config_dict,
    load_default_config,
    merge_overrides,
)
from noctusai_lib.domain.content_performance.readout import (
    Readout,
    compute_readout,
    split_by_period,
)

__all__ = [
    "ALERT_DIRECTIONS",
    "ALERT_METHODS",
    "INDICATOR_OPS",
    "NO_GROUP_VALUE",
    "PANEL_AGGREGATES",
    "Alert",
    "AlertEvaluation",
    "AlertRuleSpec",
    "BaselineSpec",
    "BaselineStat",
    "CadenceSpec",
    "Cell",
    "CellStatus",
    "ConfigError",
    "IndicatorSpec",
    "MetricSpec",
    "NotEvaluated",
    "PanelCell",
    "PanelLineSpec",
    "PerformanceConfig",
    "Reading",
    "ReadingResult",
    "ReadingStatus",
    "Readout",
    "ReviewCadenceSpec",
    "WindowSpec",
    "age_in_days",
    "compute_baselines",
    "compute_panel",
    "compute_readout",
    "config_from_dict",
    "default_config_dict",
    "evaluate_alerts",
    "evaluate_readings",
    "group_of",
    "load_default_config",
    "merge_overrides",
    "percentile_inc",
    "select_window_observation",
    "split_by_period",
    "status_counts",
]

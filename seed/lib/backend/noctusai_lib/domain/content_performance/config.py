"""Content-performance configuration — every number is DATA, never code.

Owner rule (2026-10-19, `products/social-wiring/projects/marketing-intelligence/
DECISIONS.md` § "Decided by the owner — 2026-10-19"): the calculator holds only
OPERATIONS (a ratio, a sum, a window check, a dedup, a comparison against the
profile's own baseline). Every value those operations use — reading windows and
their tolerance, which indicators exist, the baseline look-back and minimum
sample, alert thresholds, which metrics the source actually provides, the review
cadence and the decision-validation period — lives in a ``PerformanceConfig``.

Recommended defaults ship as JSON files next to this module
(``defaults/<platform>.json``); an org and a profile layer partial overrides on
top (``merge_overrides``). Every computed result carries the config ``version``
label AND its ``fingerprint`` (sha256 of the canonical resolved config), so a
number can always be traced back to the exact settings that produced it
(SIMEC reliability rule 1).

The config is validated strictly on construction: an unknown field, an unknown
operation, a reference to a metric/indicator that does not exist, or an
inverted window raises ``ConfigError`` — never a silent default.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib import resources
from typing import Any, Mapping, Optional

#: Operations an indicator may use. Adding an operation is a code change; adding
#: an indicator that uses one is a config change.
INDICATOR_OPS = ("sum_all", "ratio")
#: Panel aggregations (the workbook PAINEL's row kinds).
PANEL_AGGREGATES = ("count", "sum", "mean", "sample")
#: Baseline-relative alert methods.
ALERT_METHODS = ("pct_from_median", "outside_iqr")
ALERT_DIRECTIONS = ("below", "above", "both")
#: Fields every reading carries structurally (not metrics).
STRUCTURAL_FIELDS = ("published_at", "collected_at", "content_id", "window")


class ConfigError(ValueError):
    """The configuration is malformed or internally inconsistent."""


# ─── specs ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MetricSpec:
    """A raw metric the platform may report. ``available=False`` means the
    source does not provide it: every value is reported as "não disponível",
    never estimated and never 0."""

    key: str
    label: str
    available: bool = True
    unit: str = "count"
    note: Optional[str] = None


@dataclass(frozen=True)
class WindowSpec:
    """A reading window: a reading is accepted when the content's age at
    collection (days, ``collected_at - published_at``) lies in
    ``[min_days, max_days]``. ``None`` on a bound = unbounded (the workbook's
    ``Atual`` window has no tolerance at all)."""

    key: str
    label: str
    min_days: Optional[float] = None
    max_days: Optional[float] = None
    enabled: bool = True

    def accepts(self, age_days: float) -> bool:
        if self.min_days is not None and age_days < self.min_days:
            return False
        if self.max_days is not None and age_days > self.max_days:
            return False
        return True


@dataclass(frozen=True)
class IndicatorSpec:
    """A computed value. ``op='sum_all'`` = sum of ``inputs`` only when EVERY
    input is present (the workbook's ``COUNT(J:M)<4 → blank``);
    ``op='ratio'`` = ``inputs[0] / inputs[1]``, blank when either is missing
    or the denominator is ``<= 0``. Inputs may name metrics or indicators
    declared EARLIER in the list."""

    key: str
    label: str
    op: str
    inputs: tuple[str, ...]
    unit: str = "ratio"
    enabled: bool = True


@dataclass(frozen=True)
class PanelLineSpec:
    """One PAINEL row, computed per window over readings with status OK.
    ``count`` = valid readings; ``sum`` = sum of ``source`` (blank when there
    are no valid readings); ``mean`` = simple mean of ``source`` over the
    readings that have it (mean of rates, not a weighted rate); ``sample`` =
    how many readings have ``source``."""

    key: str
    label: str
    aggregate: str
    source: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class BaselineSpec:
    """The profile's own history: readings published within ``lookback_days``
    before the period, grouped by ``group_by`` (comparable posts), per window
    and indicator. A group's baseline only counts once it has ``min_posts``."""

    lookback_days: int
    min_posts: int
    group_by: tuple[str, ...] = ("format",)
    indicators: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlertRuleSpec:
    """An alert relative to the profile's own baseline — never a universal
    cut-off. ``pct_from_median``: fires when ``|value - median| / median >=
    threshold`` in ``direction``; ``outside_iqr``: fires when the value is
    below ``p25 - threshold*IQR`` or above ``p75 + threshold*IQR``."""

    key: str
    indicator: str
    method: str
    threshold: float
    direction: str = "both"
    windows: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class ReviewCadenceSpec:
    key: str
    label: str
    every_days: int
    enabled: bool = True


@dataclass(frozen=True)
class CadenceSpec:
    reviews: tuple[ReviewCadenceSpec, ...]
    decision_validation_days: int


@dataclass(frozen=True)
class PerformanceConfig:
    platform: str
    version: str
    required_metrics: tuple[str, ...]
    metrics: tuple[MetricSpec, ...]
    windows: tuple[WindowSpec, ...]
    indicators: tuple[IndicatorSpec, ...]
    panel: tuple[PanelLineSpec, ...]
    baseline: BaselineSpec
    alerts: tuple[AlertRuleSpec, ...]
    cadence: CadenceSpec
    description: str = ""
    _raw: dict = field(default_factory=dict, compare=False, repr=False)

    # lookups ---------------------------------------------------------------
    def metric(self, key: str) -> Optional[MetricSpec]:
        return next((m for m in self.metrics if m.key == key), None)

    def window(self, key: str) -> Optional[WindowSpec]:
        return next((w for w in self.windows if w.key == key and w.enabled), None)

    @property
    def active_windows(self) -> tuple[WindowSpec, ...]:
        return tuple(w for w in self.windows if w.enabled)

    @property
    def active_indicators(self) -> tuple[IndicatorSpec, ...]:
        return tuple(i for i in self.indicators if i.enabled)

    @property
    def active_panel(self) -> tuple[PanelLineSpec, ...]:
        return tuple(p for p in self.panel if p.enabled)

    @property
    def active_alerts(self) -> tuple[AlertRuleSpec, ...]:
        return tuple(a for a in self.alerts if a.enabled)

    def unavailable_keys(self) -> frozenset[str]:
        """Metrics the source does not provide PLUS every indicator that
        (transitively) depends on one — all reported as "não disponível"."""
        out = {m.key for m in self.metrics if not m.available}
        for ind in self.active_indicators:
            if any(i in out for i in ind.inputs):
                out.add(ind.key)
        return frozenset(out)

    # identity --------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._raw)

    @property
    def fingerprint(self) -> str:
        """sha256 of the canonical resolved config — the unforgeable identity
        stamped on every result (the ``version`` label is for humans)."""
        canonical = json.dumps(self._raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # cadence ops -----------------------------------------------------------
    def review_period(self, cadence_key: str, as_of: date) -> tuple[date, date]:
        """Inclusive ``(start, end)`` of the review period ending ``as_of``."""
        spec = next((r for r in self.cadence.reviews if r.key == cadence_key and r.enabled), None)
        if spec is None:
            raise ConfigError(f"unknown or disabled review cadence {cadence_key!r}")
        return as_of - timedelta(days=spec.every_days - 1), as_of

    def decision_review_date(self, decided_on: date) -> date:
        """When a decision's effect must be checked (results control)."""
        return decided_on + timedelta(days=self.cadence.decision_validation_days)


# ─── parsing + validation ────────────────────────────────────────────────
_TOP_KEYS = {
    "platform", "version", "description", "required_metrics", "metrics", "windows",
    "indicators", "panel", "baseline", "alerts", "cadence",
}


def _check_keys(obj: Mapping[str, Any], allowed: set[str], where: str) -> None:
    if not isinstance(obj, Mapping):
        raise ConfigError(f"{where}: expected an object, got {type(obj).__name__}")
    unknown = set(obj) - allowed
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {sorted(unknown)}")


def _req(obj: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise ConfigError(f"{where}: missing required field {key!r}")
    return obj[key]


def _num(value: Any, where: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: expected a number, got {value!r}")
    return value


def _int(value: Any, where: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{where}: expected an integer >= {minimum}, got {value!r}")
    return value


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _keyed_items(raw: Any, where: str) -> dict[str, dict[str, Any]]:
    """Keyed collections are stored as ``{key: {...fields}}`` — the shape that
    makes per-key overrides a plain deep-merge."""
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{where}: expected an object keyed by item key")
    for k, v in raw.items():
        _str(k, f"{where} key")
        if not isinstance(v, Mapping):
            raise ConfigError(f"{where}.{k}: expected an object")
    return dict(raw)


def config_from_dict(raw: Mapping[str, Any]) -> PerformanceConfig:
    """Build + validate a config from its dict form (JSON shape)."""
    _check_keys(raw, _TOP_KEYS, "config")
    platform = _str(_req(raw, "platform", "config"), "config.platform")
    version = _str(_req(raw, "version", "config"), "config.version")

    metrics: list[MetricSpec] = []
    for k, m in _keyed_items(_req(raw, "metrics", "config"), "metrics").items():
        w = f"metrics.{k}"
        _check_keys(m, {"label", "available", "unit", "note"}, w)
        avail = m.get("available", True)
        if not isinstance(avail, bool):
            raise ConfigError(f"{w}.available: expected a boolean")
        metrics.append(MetricSpec(
            key=k, label=_str(_req(m, "label", w), f"{w}.label"), available=avail,
            unit=m.get("unit", "count"), note=m.get("note"),
        ))
    metric_keys = {m.key for m in metrics}
    if set(STRUCTURAL_FIELDS) & metric_keys:
        raise ConfigError(f"metrics: {sorted(set(STRUCTURAL_FIELDS) & metric_keys)} are structural fields")

    required = tuple(raw.get("required_metrics", ()))
    for r in required:
        if r not in metric_keys:
            raise ConfigError(f"required_metrics: {r!r} is not a declared metric")
        if not next(m for m in metrics if m.key == r).available:
            raise ConfigError(f"required_metrics: {r!r} is marked unavailable — no reading could ever be valid")

    windows: list[WindowSpec] = []
    for k, w_raw in _keyed_items(_req(raw, "windows", "config"), "windows").items():
        w = f"windows.{k}"
        _check_keys(w_raw, {"label", "min_days", "max_days", "enabled"}, w)
        lo = _num(w_raw.get("min_days"), f"{w}.min_days", allow_none=True)
        hi = _num(w_raw.get("max_days"), f"{w}.max_days", allow_none=True)
        if lo is not None and lo < 0:
            raise ConfigError(f"{w}.min_days: must be >= 0")
        if lo is not None and hi is not None and lo > hi:
            raise ConfigError(f"{w}: min_days {lo} > max_days {hi}")
        windows.append(WindowSpec(
            key=k, label=_str(_req(w_raw, "label", w), f"{w}.label"),
            min_days=lo, max_days=hi, enabled=bool(w_raw.get("enabled", True)),
        ))
    if not any(w.enabled for w in windows):
        raise ConfigError("windows: at least one window must be enabled")

    indicators: list[IndicatorSpec] = []
    known = set(metric_keys)
    for k, i_raw in _keyed_items(_req(raw, "indicators", "config"), "indicators").items():
        w = f"indicators.{k}"
        _check_keys(i_raw, {"label", "op", "inputs", "unit", "enabled"}, w)
        if k in metric_keys:
            raise ConfigError(f"{w}: key collides with a metric")
        op = _req(i_raw, "op", w)
        if op not in INDICATOR_OPS:
            raise ConfigError(f"{w}.op: {op!r} not in {INDICATOR_OPS}")
        inputs = tuple(_req(i_raw, "inputs", w))
        if op == "ratio" and len(inputs) != 2:
            raise ConfigError(f"{w}: ratio takes exactly 2 inputs (numerator, denominator)")
        if op == "sum_all" and len(inputs) < 1:
            raise ConfigError(f"{w}: sum_all needs at least 1 input")
        enabled = bool(i_raw.get("enabled", True))
        if enabled:
            for inp in inputs:
                if inp not in known:
                    raise ConfigError(
                        f"{w}: input {inp!r} is not a metric or an earlier enabled indicator")
            known.add(k)
        indicators.append(IndicatorSpec(
            key=k, label=_str(_req(i_raw, "label", w), f"{w}.label"), op=op,
            inputs=inputs, unit=i_raw.get("unit", "ratio"), enabled=enabled,
        ))

    panel: list[PanelLineSpec] = []
    for k, p_raw in _keyed_items(_req(raw, "panel", "config"), "panel").items():
        w = f"panel.{k}"
        _check_keys(p_raw, {"label", "aggregate", "source", "enabled"}, w)
        agg = _req(p_raw, "aggregate", w)
        if agg not in PANEL_AGGREGATES:
            raise ConfigError(f"{w}.aggregate: {agg!r} not in {PANEL_AGGREGATES}")
        src = p_raw.get("source")
        enabled = bool(p_raw.get("enabled", True))
        if agg == "count":
            if src is not None:
                raise ConfigError(f"{w}: 'count' takes no source")
        elif enabled and src not in known:
            raise ConfigError(f"{w}.source: {src!r} is not a metric or enabled indicator")
        panel.append(PanelLineSpec(
            key=k, label=_str(_req(p_raw, "label", w), f"{w}.label"),
            aggregate=agg, source=src, enabled=enabled,
        ))

    b_raw = _req(raw, "baseline", "config")
    _check_keys(b_raw, {"lookback_days", "min_posts", "group_by", "indicators"}, "baseline")
    b_inds = tuple(b_raw.get("indicators", ()))
    for i in b_inds:
        if i not in known:
            raise ConfigError(f"baseline.indicators: {i!r} is not a metric or enabled indicator")
    group_by = tuple(b_raw.get("group_by", ("format",)))
    for g in group_by:
        if g != "format":
            raise ConfigError(f"baseline.group_by: only 'format' is supported, got {g!r}")
    baseline = BaselineSpec(
        lookback_days=_int(_req(b_raw, "lookback_days", "baseline"), "baseline.lookback_days", minimum=1),
        min_posts=_int(_req(b_raw, "min_posts", "baseline"), "baseline.min_posts", minimum=1),
        group_by=group_by, indicators=b_inds,
    )

    alerts: list[AlertRuleSpec] = []
    win_keys = {wn.key for wn in windows}
    for k, a_raw in _keyed_items(raw.get("alerts", {}), "alerts").items():
        w = f"alerts.{k}"
        _check_keys(a_raw, {"indicator", "method", "threshold", "direction", "windows", "enabled"}, w)
        enabled = bool(a_raw.get("enabled", True))
        ind = _req(a_raw, "indicator", w)
        if enabled and ind not in b_inds:
            raise ConfigError(f"{w}.indicator: {ind!r} has no baseline (add it to baseline.indicators)")
        method = _req(a_raw, "method", w)
        if method not in ALERT_METHODS:
            raise ConfigError(f"{w}.method: {method!r} not in {ALERT_METHODS}")
        direction = a_raw.get("direction", "both")
        if direction not in ALERT_DIRECTIONS:
            raise ConfigError(f"{w}.direction: {direction!r} not in {ALERT_DIRECTIONS}")
        thr = _num(_req(a_raw, "threshold", w), f"{w}.threshold")
        if thr is None or thr <= 0:
            raise ConfigError(f"{w}.threshold: must be > 0")
        a_wins = tuple(a_raw.get("windows", ()))
        for wk in a_wins:
            if wk not in win_keys:
                raise ConfigError(f"{w}.windows: unknown window {wk!r}")
        alerts.append(AlertRuleSpec(
            key=k, indicator=ind, method=method, threshold=thr,
            direction=direction, windows=a_wins, enabled=enabled,
        ))

    c_raw = _req(raw, "cadence", "config")
    _check_keys(c_raw, {"reviews", "decision_validation_days"}, "cadence")
    reviews = []
    for k, r_raw in _keyed_items(_req(c_raw, "reviews", "cadence"), "cadence.reviews").items():
        w = f"cadence.reviews.{k}"
        _check_keys(r_raw, {"label", "every_days", "enabled"}, w)
        reviews.append(ReviewCadenceSpec(
            key=k, label=_str(_req(r_raw, "label", w), f"{w}.label"),
            every_days=_int(_req(r_raw, "every_days", w), f"{w}.every_days", minimum=1),
            enabled=bool(r_raw.get("enabled", True)),
        ))
    cadence = CadenceSpec(
        reviews=tuple(reviews),
        decision_validation_days=_int(
            _req(c_raw, "decision_validation_days", "cadence"),
            "cadence.decision_validation_days", minimum=1),
    )

    return PerformanceConfig(
        platform=platform, version=version, description=raw.get("description", ""),
        required_metrics=required, metrics=tuple(metrics), windows=tuple(windows),
        indicators=tuple(indicators), panel=tuple(panel), baseline=baseline,
        alerts=tuple(alerts), cadence=cadence, _raw=copy.deepcopy(dict(raw)),
    )


# ─── defaults + layering ─────────────────────────────────────────────────
def default_config_dict(platform: str) -> dict[str, Any]:
    """The methodology's recommended defaults for ``platform`` (JSON data
    shipped with the package)."""
    try:
        text = resources.files(__package__).joinpath("defaults", f"{platform}.json").read_text("utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"no default content-performance config for platform {platform!r}") from exc
    return json.loads(text)


def load_default_config(platform: str) -> PerformanceConfig:
    return config_from_dict(default_config_dict(platform))


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(override)


#: Fields an override layer may never touch (identity of the base).
_LOCKED = {"platform", "version"}


def merge_overrides(
    base: PerformanceConfig, overrides: Optional[Mapping[str, Any]], layer_label: str
) -> PerformanceConfig:
    """Layer a partial override (same shape as the config, any subset) on top
    of ``base``. Keyed collections merge per key (``{"windows": {"7d":
    {"max_days": 12}}}`` changes one bound; a new key adds an item;
    ``{"enabled": false}`` switches one off). Lists (``inputs``,
    ``required_metrics``, ``group_by``) replace whole. The result's
    ``version`` records the layer: ``"<base>+<layer_label>"``. An empty or
    ``None`` override returns ``base`` unchanged."""
    if not overrides:
        return base
    if not isinstance(overrides, Mapping):
        raise ConfigError("overrides: expected an object")
    locked = _LOCKED & set(overrides)
    if locked:
        raise ConfigError(f"overrides: {sorted(locked)} cannot be overridden")
    merged = _deep_merge(base.to_dict(), overrides)
    merged["version"] = f"{base.version}+{_str(layer_label, 'layer_label')}"
    return config_from_dict(merged)


__all__ = [
    "ALERT_DIRECTIONS",
    "ALERT_METHODS",
    "INDICATOR_OPS",
    "PANEL_AGGREGATES",
    "STRUCTURAL_FIELDS",
    "AlertRuleSpec",
    "BaselineSpec",
    "CadenceSpec",
    "ConfigError",
    "IndicatorSpec",
    "MetricSpec",
    "PanelLineSpec",
    "PerformanceConfig",
    "ReviewCadenceSpec",
    "WindowSpec",
    "config_from_dict",
    "default_config_dict",
    "load_default_config",
    "merge_overrides",
]

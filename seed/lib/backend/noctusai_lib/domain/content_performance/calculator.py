"""Content-performance calculator — per-reading validation + indicators and
the per-window panel. Pure: no IO, no clock, no config values in code.

Reproduces the SIMEC 1.0 workbooks' DADOS (columns S–Z) and PAINEL
semantics exactly — golden tests evaluate the real workbook formulas
(`tests/domain/content_performance/golden/`):

* A blank is never 0. A metric the source did not report is ``None``
  (status ``ausente``); a metric the platform does not provide at all
  (``MetricSpec.available=False``) is ``None`` with status
  ``nao_disponivel`` — never estimated.
* ``sum_all`` is blank unless EVERY input is present (zeros count as present).
* ``ratio`` is blank when either side is missing or the denominator is <= 0.
* Validation precedence (first match wins): ``incompleto`` (a structural
  field or a required metric missing) → ``data_invalida`` (collected before
  published) → ``fora_da_janela`` (age outside the window's tolerance) →
  ``duplicado`` (same content + window appears more than once — EVERY copy
  is flagged, as the workbook's COUNTIFS does) → ``ok``.
* The panel uses only ``ok`` readings, per window; ``mean`` is the simple
  mean of per-content values over the readings that HAVE the value (mean of
  rates, not a weighted rate), always reported with its sample size.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from noctusai_lib.domain.content_performance.config import PerformanceConfig

Temporal = Union[date, datetime]


class ReadingStatus(str, Enum):
    OK = "ok"
    INCOMPLETO = "incompleto"
    DATA_INVALIDA = "data_invalida"
    FORA_DA_JANELA = "fora_da_janela"
    DUPLICADO = "duplicado"
    JANELA_DESCONHECIDA = "janela_desconhecida"
    VAZIO = "vazio"


class CellStatus(str, Enum):
    OK = "ok"
    AUSENTE = "ausente"  # the source can provide it, but this reading lacks it
    NAO_DISPONIVEL = "nao_disponivel"  # the platform/source does not provide it
    SEM_DADOS = "sem_dados"  # panel: no reading in the window has it


@dataclass(frozen=True)
class Reading:
    """One observation of one piece of content in one window (a DADOS row).

    ``values`` maps metric keys (see the config's ``metrics``) to numbers or
    ``None``. ``source``/``source_ref`` carry traceability (where the number
    came from: e.g. ``{"snapshot_date": "2026-10-09"}``)."""

    content_id: Optional[str]
    published_at: Optional[Temporal]
    collected_at: Optional[Temporal]
    window: Optional[str]
    values: Mapping[str, Any] = field(default_factory=dict)
    format: Optional[str] = None
    topic: Optional[str] = None
    source: Optional[str] = None
    source_ref: Optional[Mapping[str, Any]] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class Cell:
    value: Optional[float]
    status: CellStatus

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "status": self.status.value}


@dataclass(frozen=True)
class ReadingResult:
    reading: Reading
    status: ReadingStatus
    age_days: Optional[float]
    metrics: Mapping[str, Cell]
    indicators: Mapping[str, Cell]

    def value(self, key: str) -> Optional[float]:
        cell = self.indicators.get(key) or self.metrics.get(key)
        return cell.value if cell is not None else None

    def to_dict(self) -> dict[str, Any]:
        r = self.reading
        return {
            "content_id": r.content_id,
            "published_at": _iso(r.published_at),
            "collected_at": _iso(r.collected_at),
            "window": r.window,
            "format": r.format,
            "topic": r.topic,
            "source": r.source,
            "source_ref": dict(r.source_ref) if r.source_ref else None,
            "note": r.note,
            "status": self.status.value,
            "age_days": self.age_days,
            "metrics": {k: c.to_dict() for k, c in self.metrics.items()},
            "indicators": {k: c.to_dict() for k, c in self.indicators.items()},
        }


@dataclass(frozen=True)
class PanelCell:
    value: Optional[float]
    n: int
    status: CellStatus

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "n": self.n, "status": self.status.value}


# ─── primitives ──────────────────────────────────────────────────────────
def _iso(v: Optional[Temporal]) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _number(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    raise TypeError(f"metric value must be a number or None, got {type(v).__name__}: {v!r}")


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def age_in_days(published_at: Temporal, collected_at: Temporal) -> float:
    """``collected_at - published_at`` in days. Two datetimes → fractional
    days; if either side is a plain date, both are compared as dates (the
    workbook's date cells)."""
    if isinstance(published_at, datetime) and isinstance(collected_at, datetime):
        if (published_at.tzinfo is None) != (collected_at.tzinfo is None):
            raise ValueError("published_at and collected_at must both be tz-aware or both naive")
        return (collected_at - published_at).total_seconds() / 86400.0
    p = published_at.date() if isinstance(published_at, datetime) else published_at
    c = collected_at.date() if isinstance(collected_at, datetime) else collected_at
    return float((c - p).days)


def select_window_observation(
    published_on: date,
    observations: Iterable[tuple[date, Any]],
    window_key: str,
    config: PerformanceConfig,
) -> Optional[tuple[date, Any]]:
    """From a content's daily observations ``[(observed_on, payload), ...]``,
    pick the one that represents ``window_key``: the EARLIEST observation
    whose age lies inside the window's tolerance; for an unbounded-above
    window (``atual``) the LATEST observation. ``None`` = no observation
    falls in the window (the content is too young, or a day was missed)."""
    spec = config.window(window_key)
    if spec is None:
        raise ValueError(f"unknown or disabled window {window_key!r}")
    inside = sorted(
        (o for o in observations if spec.accepts(float((o[0] - published_on).days))),
        key=lambda o: o[0],
    )
    if not inside:
        return None
    return inside[-1] if spec.max_days is None else inside[0]


# ─── per-reading evaluation ──────────────────────────────────────────────
def _metric_cells(reading: Reading, config: PerformanceConfig) -> dict[str, Cell]:
    cells: dict[str, Cell] = {}
    for m in config.metrics:
        if not m.available:
            cells[m.key] = Cell(None, CellStatus.NAO_DISPONIVEL)
            continue
        v = _number(reading.values.get(m.key))
        cells[m.key] = Cell(v, CellStatus.OK if v is not None else CellStatus.AUSENTE)
    return cells


def _indicator_cells(metrics: Mapping[str, Cell], config: PerformanceConfig) -> dict[str, Cell]:
    unavailable = config.unavailable_keys()
    known: dict[str, Cell] = dict(metrics)
    out: dict[str, Cell] = {}
    for ind in config.active_indicators:
        if ind.key in unavailable:
            cell = Cell(None, CellStatus.NAO_DISPONIVEL)
        else:
            vals = [known[i].value for i in ind.inputs]
            value: Optional[float] = None
            if ind.op == "sum_all":
                if all(v is not None for v in vals):
                    value = sum(vals)  # type: ignore[arg-type]
            elif ind.op == "ratio":
                num, den = vals
                if num is not None and den is not None and den > 0:
                    value = num / den
            else:  # pragma: no cover — config validation forbids it
                raise ValueError(f"unknown indicator op {ind.op!r}")
            cell = Cell(value, CellStatus.OK if value is not None else CellStatus.AUSENTE)
        out[ind.key] = cell
        known[ind.key] = cell
    return out


def _is_empty(r: Reading) -> bool:
    return (
        all(_is_blank(v) for v in (r.content_id, r.published_at, r.collected_at, r.window,
                                    r.format, r.topic, r.source, r.note))
        and all(v is None for v in r.values.values())
    )


def evaluate_readings(
    readings: Sequence[Reading], config: PerformanceConfig
) -> list[ReadingResult]:
    """Validate every reading and compute its indicators (DADOS S–Z).
    Duplicates are detected across the WHOLE sequence given."""
    dup_counts = Counter(
        (r.content_id, r.window)
        for r in readings
        if not _is_empty(r) and not _is_blank(r.content_id) and not _is_blank(r.window)
    )
    results: list[ReadingResult] = []
    for r in readings:
        if _is_empty(r):
            results.append(ReadingResult(r, ReadingStatus.VAZIO, None, {}, {}))
            continue
        metrics = _metric_cells(r, config)
        indicators = _indicator_cells(metrics, config)
        age = (
            age_in_days(r.published_at, r.collected_at)
            if r.published_at is not None and r.collected_at is not None
            else None
        )
        results.append(ReadingResult(r, _status(r, age, metrics, config, dup_counts),
                                     age, metrics, indicators))
    return results


def _status(
    r: Reading,
    age: Optional[float],
    metrics: Mapping[str, Cell],
    config: PerformanceConfig,
    dup_counts: Counter,
) -> ReadingStatus:
    if (
        r.published_at is None or r.collected_at is None
        or _is_blank(r.content_id) or _is_blank(r.window)
        or any(metrics[k].value is None for k in config.required_metrics)
    ):
        return ReadingStatus.INCOMPLETO
    assert age is not None
    if age < 0:
        return ReadingStatus.DATA_INVALIDA
    spec = config.window(str(r.window))
    if spec is None:
        return ReadingStatus.JANELA_DESCONHECIDA
    if not spec.accepts(age):
        return ReadingStatus.FORA_DA_JANELA
    if dup_counts[(r.content_id, r.window)] > 1:
        return ReadingStatus.DUPLICADO
    return ReadingStatus.OK


# ─── panel ───────────────────────────────────────────────────────────────
def compute_panel(
    results: Sequence[ReadingResult], config: PerformanceConfig
) -> dict[str, dict[str, PanelCell]]:
    """``{window_key: {panel_line_key: PanelCell}}`` over ``ok`` readings —
    the workbook's PAINEL, one column per window."""
    unavailable = config.unavailable_keys()
    panel: dict[str, dict[str, PanelCell]] = {}
    for w in config.active_windows:
        rows = [x for x in results if x.status is ReadingStatus.OK and x.reading.window == w.key]
        n_valid = len(rows)
        col: dict[str, PanelCell] = {}
        for line in config.active_panel:
            if line.aggregate == "count":
                col[line.key] = PanelCell(n_valid, n_valid, CellStatus.OK)
                continue
            assert line.source is not None
            if line.source in unavailable:
                col[line.key] = PanelCell(None, 0, CellStatus.NAO_DISPONIVEL)
                continue
            present = [v for v in (x.value(line.source) for x in rows) if v is not None]
            k = len(present)
            if line.aggregate == "sample":
                col[line.key] = PanelCell(k, k, CellStatus.OK)
            elif line.aggregate == "sum":
                col[line.key] = (
                    PanelCell(sum(present), k, CellStatus.OK) if n_valid
                    else PanelCell(None, 0, CellStatus.SEM_DADOS)
                )
            elif line.aggregate == "mean":
                col[line.key] = (
                    PanelCell(sum(present) / k, k, CellStatus.OK) if k
                    else PanelCell(None, 0, CellStatus.SEM_DADOS)
                )
            else:  # pragma: no cover — config validation forbids it
                raise ValueError(f"unknown panel aggregate {line.aggregate!r}")
        panel[w.key] = col
    return panel


def status_counts(results: Sequence[ReadingResult]) -> dict[str, int]:
    c = Counter(r.status.value for r in results if r.status is not ReadingStatus.VAZIO)
    return {s.value: c.get(s.value, 0) for s in ReadingStatus if s is not ReadingStatus.VAZIO}


__all__ = [
    "Cell",
    "CellStatus",
    "PanelCell",
    "Reading",
    "ReadingResult",
    "ReadingStatus",
    "age_in_days",
    "compute_panel",
    "evaluate_readings",
    "select_window_observation",
    "status_counts",
]

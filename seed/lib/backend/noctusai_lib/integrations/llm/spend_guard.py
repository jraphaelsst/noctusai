"""The rolling-window spend guard on EVERY LLM call path — per-surface limits as CONFIGURATION.

Sibling of `spend_ceiling.py` (which RESERVES a run's cost cap before a long mechanism starts — Studio eval /
mecanismo runs) and of `budget.py` (the org's MONTHLY BRL budget). This one is the per-call seatbelt: before a call
leaves the process, the org's ACTUAL spend of the last `window_hours` on the call's *surface* (read from the
central ledger `public.ai_usage` through the SQL function `ai_spend_window`, core migration 116) is compared with
the surface's limit.

SURFACE = the call's attributed ``product`` (`attribution.current_attribution()`), optionally narrowed to
``product:feature``; ``*`` = every surface. Resolution: ``product:feature`` → ``product`` → ``*``.

CONFIGURATION (default = NONE = nothing is checked and nothing is read: no limit blocks any traffic)::

    LLM_SPEND_LIMITS='{"agents": {"usd": 25, "mode": "observe"},
                       "agents:/api/x": {"usd": 5, "mode": "enforce", "window_hours": 24},
                       "*": {"usd": 100, "mode": "observe"}}'

  - ``mode: "observe"`` (the default of a configured limit) — shadow mode: crossing the limit logs
    ``llm.spend_guard.would_block`` at WARNING and the call proceeds. This is how an operator sets real limits FROM
    DATA: read the report (view ``public.ai_spend_24h_by_surface``), configure ``observe``, watch the log, flip
    to ``enforce``.
  - ``mode: "enforce"`` — spend ≥ limit raises `SpendCeilingExceeded` (429) BEFORE the provider call. A failed
    read uses the last-known spend of that scope while fresh (`LLM_SPEND_GUARD_LKG_MAX_AGE_S`, 900 s; ERROR
    log) — customer-facing traffic rides out a short blip — and with none raises `SpendCeilingUnverifiable`
    (503). Fail-closed, loud.
  - A broken ``LLM_SPEND_LIMITS`` (bad JSON / entry) is logged at ERROR at boot and ignored (observe-only): the
    process still boots, the misconfiguration is not silent.

The check reads through a short TTL cache (`LLM_SPEND_GUARD_CACHE_TTL_S`, 30 s): an enforce limit can be overshot
by at most the spend of one cache window — it is a seatbelt, not an admission lock (use `spend_ceiling` to reserve).

Seam shape (KB § PATTERNS/backend/seed-fake-real-adapter.md): Protocol = `SpendWindowReader`; Fake =
`InMemorySpendWindowReader`; Real = `SupabaseSpendWindowReader`; factory = `make_spend_window_reader`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol

import anyio.to_thread

from .exceptions import SpendCeilingExceeded, SpendCeilingUnverifiable

logger = logging.getLogger(__name__)

__all__ = [
    "InMemorySpendWindowReader",
    "SpendWindowReader",
    "SupabaseSpendWindowReader",
    "SurfaceLimit",
    "configure_spend_guard",
    "enforce_spend_guard",
    "make_spend_window_reader",
    "parse_limits",
]

_SPEND_RPC = "ai_spend_window"
_DEFAULT_WINDOW_HOURS = 24
_DEFAULT_CACHE_TTL_S = 30.0
_DEFAULT_LKG_MAX_AGE_S = 900.0
_WOULD_BLOCK_LOG_EVERY_S = 600.0
_MODES = ("observe", "enforce")


@dataclass(frozen=True)
class SurfaceLimit:
    surface: str
    usd: float
    mode: str = "observe"
    window_hours: int = _DEFAULT_WINDOW_HOURS


class SpendWindowReader(Protocol):
    def spent_usd(self, *, org_id: str, product: Optional[str], feature: Optional[str], hours: int) -> float:
        """Actual spend of the org in the window (``None`` product/feature = unfiltered). Raises on a failed read."""


class InMemorySpendWindowReader:
    """Fake — a settable total per ``(org, product, feature)``; ``fail_with`` forces a read failure; ``reads`` counts."""

    def __init__(self) -> None:
        self.totals: dict[tuple[str, Optional[str], Optional[str]], float] = {}
        self.fail_with: Optional[Exception] = None
        self.reads = 0

    def spent_usd(self, *, org_id, product, feature, hours):
        self.reads += 1
        if self.fail_with is not None:
            raise self.fail_with
        return self.totals.get((org_id, product, feature), 0.0)


class SupabaseSpendWindowReader:
    """Real — the SQL function ``ai_spend_window`` (core 116) through a SERVICE-ROLE ``public`` client."""

    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._client_factory = core_client_factory

    def spent_usd(self, *, org_id, product, feature, hours):
        data = self._client_factory().rpc(_SPEND_RPC, {
            "p_org_id": org_id, "p_product": product, "p_feature": feature, "p_hours": hours,
        }).execute().data
        return float(data or 0)


def make_spend_window_reader(core_client_factory: Optional[Callable[[], Any]]) -> Optional[SpendWindowReader]:
    """Real when a client factory is available, else ``None`` (no guard: dev/test without a database)."""
    return SupabaseSpendWindowReader(core_client_factory) if core_client_factory is not None else None


# ── configuration ────────────────────────────────────────────────────────────────────────────────────────────


def parse_limits(raw: Optional[str]) -> dict[str, SurfaceLimit]:
    """``LLM_SPEND_LIMITS`` JSON → limits. Anything malformed is logged at ERROR and skipped (never silent)."""
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
    except ValueError as exc:
        logger.error("llm.spend_guard: LLM_SPEND_LIMITS is not valid JSON (%s) — NO limits applied", exc)
        return {}
    limits: dict[str, SurfaceLimit] = {}
    for surface, spec in data.items():
        try:
            mode = str(spec.get("mode", "observe"))
            if mode not in _MODES:
                raise ValueError(f"mode must be one of {_MODES}")
            usd = float(spec["usd"])
            hours = int(spec.get("window_hours", _DEFAULT_WINDOW_HOURS))
            if usd <= 0 or hours <= 0:
                raise ValueError("usd and window_hours must be positive")
            limits[str(surface)] = SurfaceLimit(str(surface), usd, mode, hours)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.error("llm.spend_guard: LLM_SPEND_LIMITS entry %r ignored: %s", surface, exc)
    return limits


_lock = threading.Lock()
_reader: Optional[SpendWindowReader] = None
_limits: dict[str, SurfaceLimit] = {}
#: (org, product, feature, hours) -> (monotonic time, spent_usd)
_cache: dict[tuple[str, Optional[str], Optional[str], int], tuple[float, float]] = {}
_logged_at: dict[str, float] = {}
_clock: Callable[[], float] = time.monotonic


def configure_spend_guard(
    *, reader: Optional[SpendWindowReader], limits: Optional[Mapping[str, SurfaceLimit]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> None:
    """Wire the reader and the limits (``None`` limits = parse ``LLM_SPEND_LIMITS`` from the environment). Called by
    ``create_product_app``; tests inject the Fake reader and explicit limits."""
    global _reader, _limits, _clock
    with _lock:
        _reader = reader
        _limits = dict(limits) if limits is not None else parse_limits(os.environ.get("LLM_SPEND_LIMITS"))
        _clock = clock or time.monotonic
        _cache.clear()
        _logged_at.clear()
    if _limits:
        logger.info(
            "llm.spend_guard: %s",
            ", ".join(f"{s}={l.usd}USD/{l.window_hours}h[{l.mode}]" for s, l in sorted(_limits.items())),
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("llm.spend_guard: %s=%r is not a float; using default %s", name, raw, default)
        return default


def _resolve(product: Optional[str], feature: Optional[str]) -> Optional[tuple[SurfaceLimit, Optional[str], Optional[str]]]:
    """The limit that applies to this call plus the (product, feature) filter its spend is measured over."""
    if product and feature and f"{product}:{feature}" in _limits:
        return _limits[f"{product}:{feature}"], product, feature
    if product and product in _limits:
        return _limits[product], product, None
    if "*" in _limits:
        return _limits["*"], None, None
    return None


def _should_log(key: str) -> bool:
    now = _clock()
    with _lock:
        last = _logged_at.get(key)
        if last is not None and now - last < _WOULD_BLOCK_LOG_EVERY_S:
            return False
        _logged_at[key] = now
    return True


async def enforce_spend_guard(org_id: Optional[str]) -> None:
    """The per-call check — see the module docstring. A no-op when no org, no reader, or no limit applies."""
    if not org_id or _reader is None or not _limits:
        return
    from .attribution import current_attribution

    attr = current_attribution()
    resolved = _resolve(attr.product, attr.feature)
    if resolved is None:
        return
    limit, product, feature = resolved
    key = (str(org_id), product, feature, limit.window_hours)
    now = _clock()
    with _lock:
        cached = _cache.get(key)
        reader = _reader
    if cached is not None and now - cached[0] < _env_float("LLM_SPEND_GUARD_CACHE_TTL_S", _DEFAULT_CACHE_TTL_S):
        spent = cached[1]
    else:
        try:
            spent = float(await anyio.to_thread.run_sync(
                lambda: reader.spent_usd(org_id=str(org_id), product=product, feature=feature, hours=limit.window_hours)
            ))
        except Exception as exc:  # noqa: BLE001 — handled below: last-known / refuse (enforce) or loud log (observe)
            spent = _on_read_failure(limit, str(org_id), cached, now, exc)
        else:
            with _lock:
                _cache[key] = (now, spent)
    if spent < limit.usd:
        return
    if limit.mode == "enforce":
        raise SpendCeilingExceeded(limit.surface, str(org_id), spent, 0.0, limit.usd)
    if _should_log(f"would_block:{org_id}:{limit.surface}"):
        logger.warning(
            "llm.spend_guard.would_block: org=%s surface=%s spent_usd=%.4f limit_usd=%.2f window_h=%d "
            "(mode=observe — the call proceeds)",
            org_id, limit.surface, spent, limit.usd, limit.window_hours,
        )


def _on_read_failure(
    limit: SurfaceLimit, org_id: str, cached: Optional[tuple[float, float]], now: float, exc: Exception
) -> float:
    if limit.mode != "enforce":
        logger.error("llm.spend_guard: spend read failed for org=%s surface=%s (observe mode — proceeding): %s",
                     org_id, limit.surface, exc)
        return 0.0
    if cached is not None and now - cached[0] <= _env_float("LLM_SPEND_GUARD_LKG_MAX_AGE_S", _DEFAULT_LKG_MAX_AGE_S):
        logger.error("llm.spend_guard: spend read failed for org=%s surface=%s — serving the last-known spend: %s",
                     org_id, limit.surface, exc)
        return cached[1]
    logger.error("llm.spend_guard: spend read failed for org=%s surface=%s — no fresh last-known value, REFUSED: %s",
                 org_id, limit.surface, exc)
    raise SpendCeilingUnverifiable(limit.surface, org_id, f"{type(exc).__name__}: {exc}") from exc

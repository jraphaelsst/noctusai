"""ONE rolling-window spend ceiling per org, shared by every mechanism that spends on the org's behalf.

Owner decision 2026-11-09: "$10 daily for all, same ceiling in the seed projected to multiple mechanisms". A caller
names a *ceiling key* (e.g. ``automacao-avaliacoes``) and its mechanism *kind* (``eval_run``, ``mecanismo_run``, the
improver loop...) and asks to reserve ``$X`` for one run (``ref`` = the run id). The answer counts the spend of ALL
kinds under that key for the org inside the window: the ACTUAL cost once a run was settled, the reserved cap while it
is unfinished. Crossing the ceiling raises `SpendCeilingExceeded` (429).

Fail-CLOSED (the `LLMCreditsUnverifiable` rule): a failed lookup raises `SpendCeilingUnverifiable` (503) -- an unknown
total never grants a reservation. A run that crashed and never settled keeps counting its cap for the window.

Why a reservation table and not ``public.ai_usage`` alone: ai_usage is append-only per *finished provider call*, so it
cannot express "this run may still spend $5"; and not every mechanism's calls are tagged per run. The table
(core migration ``114_spend_reservations``) holds one row per run; admission is the atomic RPC ``spend_reserve``.

Seam shape (KB § PATTERNS/backend/seed-fake-real-adapter.md): Protocol = `SpendCeiling`; Fake =
`InMemorySpendCeiling`; Real = `SupabaseSpendCeiling`; factory = `make_spend_ceiling`.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Protocol

from .exceptions import SpendCeilingExceeded, SpendCeilingUnverifiable

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_WINDOW_HOURS",
    "InMemorySpendCeiling",
    "SpendCeiling",
    "SupabaseSpendCeiling",
    "make_spend_ceiling",
]

DEFAULT_WINDOW_HOURS = 24
_RESERVE_RPC = "spend_reserve"
_SETTLE_RPC = "spend_settle"


class SpendCeiling(Protocol):
    def reserve(
        self, *, ceiling_key: str, kind: str, org_id: Any, ref: str, amount_usd: float, ceiling_usd: float,
        window_hours: int = DEFAULT_WINDOW_HOURS,
    ) -> None:
        """Reserve ``amount_usd`` for run ``ref`` or raise `SpendCeilingExceeded` / `SpendCeilingUnverifiable`.
        Idempotent on ``(ceiling_key, kind, ref)``."""

    def settle(self, *, ceiling_key: str, kind: str, ref: str, actual_usd: float) -> None:
        """Replace the reserved cap of ``ref`` with its actual cost. Best-effort: a failure is logged at ERROR and
        leaves the (higher) cap counting -- the safe direction."""


class InMemorySpendCeiling:
    """Fake -- same arithmetic as the RPC, thread-safe, injectable clock, optional forced lookup failure."""

    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.fail_with: Optional[Exception] = None

    def reserve(self, *, ceiling_key, kind, org_id, ref, amount_usd, ceiling_usd, window_hours=DEFAULT_WINDOW_HOURS):
        if self.fail_with is not None:
            raise SpendCeilingUnverifiable(ceiling_key, str(org_id), str(self.fail_with))
        now = self._clock()
        since = now - timedelta(hours=window_hours)
        with self._lock:
            if (ceiling_key, kind, ref) in self._rows:
                return
            spent = sum(
                (r["actual"] if r["actual"] is not None else r["reserved"])
                for r in self._rows.values()
                if r["key"] == ceiling_key and r["org"] == str(org_id) and r["at"] > since
            )
            if spent + amount_usd > ceiling_usd:
                raise SpendCeilingExceeded(ceiling_key, str(org_id), spent, amount_usd, ceiling_usd)
            self._rows[(ceiling_key, kind, ref)] = {
                "key": ceiling_key, "org": str(org_id), "reserved": float(amount_usd), "actual": None, "at": now,
            }

    def settle(self, *, ceiling_key, kind, ref, actual_usd):
        with self._lock:
            row = self._rows.get((ceiling_key, kind, ref))
            if row is not None:
                row["actual"] = float(actual_usd)


class SupabaseSpendCeiling:
    """Real -- the atomic RPCs of core migration 114 through a SERVICE-ROLE ``public`` client (resolved per call)."""

    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._client_factory = core_client_factory

    def reserve(self, *, ceiling_key, kind, org_id, ref, amount_usd, ceiling_usd, window_hours=DEFAULT_WINDOW_HOURS):
        try:
            data = self._client_factory().rpc(_RESERVE_RPC, {
                "p_ceiling_key": ceiling_key, "p_kind": kind, "p_org_id": str(org_id), "p_ref": ref,
                "p_amount_usd": amount_usd, "p_ceiling_usd": ceiling_usd, "p_window_hours": window_hours,
            }).execute().data
            allowed = bool(data["allowed"])
            spent = float(data["spent_usd"])
        except Exception as exc:  # noqa: BLE001 -- fail CLOSED: any lookup failure refuses, loudly
            logger.error("llm.spend_ceiling: reserve lookup failed key=%s org=%s: %s", ceiling_key, org_id, exc)
            raise SpendCeilingUnverifiable(ceiling_key, str(org_id), f"{type(exc).__name__}: {exc}") from exc
        if not allowed:
            raise SpendCeilingExceeded(ceiling_key, str(org_id), spent, amount_usd, ceiling_usd)

    def settle(self, *, ceiling_key, kind, ref, actual_usd):
        try:
            self._client_factory().rpc(_SETTLE_RPC, {
                "p_ceiling_key": ceiling_key, "p_kind": kind, "p_ref": ref, "p_actual_usd": actual_usd,
            }).execute()
        except Exception as exc:  # noqa: BLE001 -- the reserved cap keeps counting (safe direction)
            logger.error("llm.spend_ceiling: settle failed key=%s kind=%s ref=%s: %s", ceiling_key, kind, ref, exc)


def make_spend_ceiling(core_client_factory: Optional[Callable[[], Any]]) -> SpendCeiling:
    """Real when a client factory is available, else the Fake (dev/test without a database)."""
    if core_client_factory is None:
        return InMemorySpendCeiling()
    return SupabaseSpendCeiling(core_client_factory)

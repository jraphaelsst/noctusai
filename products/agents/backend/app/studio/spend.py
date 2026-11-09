"""Agent Studio's projection onto the seed's shared rolling-24h spend ceiling.

Owner decision 2026-11-09: ONE ceiling ($10 per org per rolling 24h, ``settings.daily_spend_ceiling_usd``) for every
mechanism a product token can start. Eval runs and mecanismo runs both reserve under :data:`CEILING_KEY`
(`noctusai_lib.integrations.llm.spend_ceiling`); the improver loop will too. Fail-closed: the seed raises a typed
error (429 over the ceiling, 503 unverifiable) that the framework handler renders.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.config import settings
from noctusai_lib.integrations.llm import (
    InMemorySpendCeiling, SpendCeiling, SpendCeilingExceeded, SpendCeilingUnverifiable, SupabaseSpendCeiling,
)

CEILING_KEY = "automacao-avaliacoes"
KIND_EVAL_RUN = "eval_run"
KIND_MECANISMO_RUN = "mecanismo_run"


def get_spend_ceiling_dep() -> SpendCeiling:
    """Seam over the seed ceiling: Real over the core (``public``) client when a service-role key is configured,
    else a Fake (tests bind a shared one through ``dependency_overrides``)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return InMemorySpendCeiling()
    from app.database import get_core_client

    return SupabaseSpendCeiling(get_core_client)


def reserve_run(ceiling: SpendCeiling, *, org_id: UUID, kind: str, run_id: UUID, amount_usd: float) -> None:
    """Reserve the run's cost cap or raise 429 ``daily_spend_ceiling_exceeded`` / 503
    ``daily_spend_ceiling_unverifiable`` (studio error shape: top-level ``code``); the caller then fails the booked run."""
    try:
        ceiling.reserve(
            ceiling_key=CEILING_KEY, kind=kind, org_id=org_id, ref=str(run_id), amount_usd=amount_usd,
            ceiling_usd=settings.daily_spend_ceiling_usd,
        )
    except SpendCeilingExceeded as exc:
        raise HTTPException(429, detail={"detail": exc.message, "code": "daily_spend_ceiling_exceeded"}) from exc
    except SpendCeilingUnverifiable as exc:
        raise HTTPException(503, detail={"detail": exc.message, "code": "daily_spend_ceiling_unverifiable"}) from exc


def settle_run(ceiling: Any, *, kind: str, run_id: UUID, actual_usd: float) -> None:
    ceiling.settle(ceiling_key=CEILING_KEY, kind=kind, ref=str(run_id), actual_usd=actual_usd)


class SpendSettlingRunWriter:
    """Decorates the eval run writer: when a run ends with a known cost, the seed reservation is settled to it.
    A crashed run (``falhou`` with no cost) keeps its cap counting -- the safe direction. Runs without a
    reservation (platform-admin UI) settle to a no-op."""

    def __init__(self, inner: Any, ceiling: SpendCeiling) -> None:
        self._inner = inner
        self._ceiling = ceiling

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def finish_run(self, org_id: UUID, run_id: UUID, *, status: str, custo_usd: float | None = None, **kw: Any):
        result = self._inner.finish_run(org_id, run_id, status=status, custo_usd=custo_usd, **kw)
        if custo_usd is not None or status == "concluida":
            settle_run(self._ceiling, kind=KIND_EVAL_RUN, run_id=run_id, actual_usd=float(custo_usd or 0.0))
        return result

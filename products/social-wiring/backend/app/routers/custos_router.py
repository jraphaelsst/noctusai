"""Custos — how much this org spends on paid API integrations.

Two sources, both org-scoped:

  - `social_wiring.llm_usage` — every LLM call (chat/vision/embedding/audio)
    goes through `noctusai_lib.integrations.llm`'s `record_usage`, which
    writes native-USD `cost_estimate_usd` per event (see `SupabaseUsageSink`,
    `products/social-wiring/backend/migrations/122_llm_usage.sql`). Turned
    on for this product via `SocialWiringSettings.llm_usage_tracking=True`
    (repo-level default, not a VPS-only env knob).
  - `public.cost_ledger` — native-BRL InfoSimples rows, booked by
    `app.modules.certidoes.cost_ledger.book_infosimples_cost` right after
    each billed certidão call. Cross-schema table (core's migration 046),
    read via `get_core_client()` per `KB § PATTERNS/backend/backend.md
    § Cross-schema reach via get_core_client()`.

USD→BRL conversion uses the LATEST stored `public.fx_rates` bulletin
(BCB PTAX) — not a per-day historical rate. This is a deliberate
simplification for a read endpoint (the daily-accurate per-transaction
rate is what `products/core/backend/app/services/fx_service.py`'s
`resolve_pending_cost_ledger` job computes when it PRICES a cost_ledger
row at booking time — that machinery is core-app-internal and not
reachable from this product). No stored bulletin at all ⇒ every LLM
row's BRL total is explicitly `None` with `fx_pendente=True` on the
response — never a guessed/default rate.

D4Sign and Google Maps are NOT instrumented yet (no per-call price
surfaces from either API today) — see `CLAUDE/backend.md`'s "no invented
prices" posture. Deferred; not represented as zero-cost cards here
(a silent zero would look like "confirmed free", which is false).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.database import get_core_client
from app.dependencies import coerce_org_uuid, get_current_user_org, get_scoped_admin_client
from app.services import table_reads
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/custos", tags=["custos"])


class CustosPorModelo(StrictHttpModel):
    provider: str
    model: str
    chamadas: int
    total_tokens: int
    custo_usd: float
    custo_brl: Optional[float] = None


class CustosPorDia(StrictHttpModel):
    data: str  # YYYY-MM-DD
    custo_brl: float


class CustosIntegracao(StrictHttpModel):
    nome: str
    chamadas: int
    custo_brl: Optional[float] = None
    fx_pendente: bool = False
    observacao: Optional[str] = None


class CustosOut(StrictHttpModel):
    de: str = Field(description="Início do período (YYYY-MM-DD)")
    ate: str = Field(description="Fim do período (YYYY-MM-DD, inclusive)")
    total_brl: float
    fx_pendente: bool
    integracoes: list[CustosIntegracao]
    serie_diaria: list[CustosPorDia]
    llm_por_modelo: list[CustosPorModelo]


def _default_range() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    return today.replace(day=1), today


def _parse_range(from_: Optional[str], to: Optional[str]) -> tuple[date, date]:
    if not from_ or not to:
        return _default_range()
    try:
        return date.fromisoformat(from_), date.fromisoformat(to)
    except ValueError:
        return _default_range()


def _latest_ptax_rate(core_client) -> Optional[Decimal]:
    """Most recent stored `USD/BRL` bulletin, or `None` when the platform
    has never stored one (the daily PTAX job hasn't run / BCB had no
    bulletin yet). Never fetches live — a read endpoint books no state."""
    rows = (
        core_client.table("fx_rates")
        .select("rate")
        .eq("pair", "USD/BRL")
        .order("quote_date", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    try:
        return Decimal(str(rows[0]["rate"]))
    except Exception:
        return None


@router.get("", response_model=CustosOut)
def obter_custos(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org),
) -> CustosOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    de, ate = _parse_range(from_, to)
    de_iso = de.isoformat()
    # Inclusive end-of-day boundary — `ate` is a calendar date, `at`/
    # `created_at` are timestamps.
    ate_ts = (datetime.combine(ate, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
    de_ts = datetime.combine(de, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    sw_client = get_scoped_admin_client("social_wiring")
    core_client = get_core_client()

    llm_rows = table_reads.paged_rows(
        sw_client,
        "llm_usage",
        org_id,
        select="id,provider,model,total_tokens,cost_estimate_usd,at",
        refine=lambda q: q.gte("at", de_ts).lt("at", ate_ts),
        order_col="at",
    )

    infosimples_rows = table_reads.paged_rows(
        core_client,
        "cost_ledger",
        org_id,
        eq_filters={"category": "infosimples"},
        select="id,amount_brl,fx_pending,created_at",
        refine=lambda q: q.gte("created_at", de_ts).lt("created_at", ate_ts),
        order_col="created_at",
    )

    fx_rate = _latest_ptax_rate(core_client)
    llm_fx_pending = fx_rate is None and bool(llm_rows)

    # ── LLM: per (provider, model) + per-day ────────────────────────────
    por_modelo: dict[tuple[str, str], dict] = {}
    por_dia: dict[str, Decimal] = defaultdict(Decimal)
    llm_total_usd = Decimal("0")
    for row in llm_rows:
        key = (row.get("provider") or "?", row.get("model") or "?")
        bucket = por_modelo.setdefault(key, {"chamadas": 0, "total_tokens": 0, "custo_usd": Decimal("0")})
        bucket["chamadas"] += 1
        bucket["total_tokens"] += int(row.get("total_tokens") or 0)
        cost = Decimal(str(row.get("cost_estimate_usd") or 0))
        bucket["custo_usd"] += cost
        llm_total_usd += cost
        if fx_rate is not None:
            day = str(row.get("at") or "")[:10]
            if day:
                por_dia[day] += cost * fx_rate

    llm_por_modelo = [
        CustosPorModelo(
            provider=provider,
            model=model,
            chamadas=v["chamadas"],
            total_tokens=v["total_tokens"],
            custo_usd=float(v["custo_usd"]),
            custo_brl=float(v["custo_usd"] * fx_rate) if fx_rate is not None else None,
        )
        for (provider, model), v in sorted(por_modelo.items())
    ]

    llm_custo_brl = float(llm_total_usd * fx_rate) if fx_rate is not None else None

    # ── InfoSimples ──────────────────────────────────────────────────────
    infosimples_total = Decimal("0")
    infosimples_pending = 0
    for row in infosimples_rows:
        if row.get("fx_pending"):
            infosimples_pending += 1
            continue
        amount = Decimal(str(row.get("amount_brl") or 0))
        infosimples_total += amount
        day = str(row.get("created_at") or "")[:10]
        if day:
            por_dia[day] += amount

    integracoes = [
        CustosIntegracao(
            nome="llm",
            chamadas=len(llm_rows),
            custo_brl=llm_custo_brl,
            fx_pendente=llm_fx_pending,
            observacao=None if fx_rate is not None or not llm_rows else (
                "Nenhuma cotação PTAX armazenada ainda — custo em USD disponível "
                "no detalhamento por modelo."
            ),
        ),
        CustosIntegracao(
            nome="infosimples",
            chamadas=len(infosimples_rows),
            custo_brl=float(infosimples_total),
            fx_pendente=infosimples_pending > 0,
            observacao=(
                f"{infosimples_pending} chamada(s) aguardando cotação PTAX"
                if infosimples_pending else None
            ),
        ),
        CustosIntegracao(
            nome="d4sign",
            chamadas=0,
            custo_brl=None,
            observacao="Custo por chamada não disponível — consulte seu plano D4Sign.",
        ),
        CustosIntegracao(
            nome="google_maps",
            chamadas=0,
            custo_brl=None,
            observacao="Custo por chamada não disponível — consulte seu plano Google Maps.",
        ),
    ]

    total_brl = sum((c.custo_brl or 0.0) for c in integracoes)
    serie_diaria = [
        CustosPorDia(data=day, custo_brl=float(amount))
        for day, amount in sorted(por_dia.items())
    ]

    return CustosOut(
        de=de_iso,
        ate=ate.isoformat(),
        total_brl=total_brl,
        fx_pendente=llm_fx_pending or infosimples_pending > 0,
        integracoes=integracoes,
        serie_diaria=serie_diaria,
        llm_por_modelo=llm_por_modelo,
    )

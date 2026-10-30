"""Platform-admin view of the central AI-usage ledger (``public.ai_usage``, D25).

ONE table holds every LLM call of every product, attributed at write time
(org → product → feature → user / conversation / agent) and priced at write
time (USD + BRL at the PTAX of the day, ``price_version`` recorded) — so this
endpoint no longer keeps a hand-maintained product→schema map: a new product
appears here the moment it makes its first call.

Access: platform admin only — ``public.noctus_users.role == 'admin'`` read from
the database (never ``user_metadata``). Any non-admin call → 403, no token → 401.

LGPD: ledger rows carry identifiers, counts and prices only — never prompt text.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.integrations.llm.ledger_read import (
    AiUsageWindowTooLarge,
    aggregate_ai_usage,
    read_ai_usage_rows,
)
from noctusai_lib.primitives.parsing import parse_iso_or_400 as _parse_iso

from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/llm-usage", tags=["Admin · LLM Usage"])

_MAX_WINDOW_DAYS = 400


@router.get("")
async def aggregate_llm_usage(
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    org_id: Optional[str] = Query(None, description="Filter by org id"),
    product: Optional[str] = Query(None, description="Filter by product slug"),
    feature: Optional[str] = Query(None, description="Filter by feature"),
    from_: Optional[str] = Query(None, alias="from", description="ISO-8601 start (default now-30d)"),
    to: Optional[str] = Query(None, description="ISO-8601 end (default now)"),
):
    """Usage + cost rolled up per org → per product → per feature (+ by model).

    Response::

        {
          "window": {"from": "...", "to": "..."},
          "filters": {"org_id": ..., "product": ..., "feature": ...},
          "totals": {calls, errors, partial, input_tokens, output_tokens, ..., cost_usd, cost_brl},
          "per_org": [{org_id, ...totals, "per_product": [{product, ...,
                        "per_feature": [{feature, ...}], "by_model": [{provider, model, ...}]}]}],
          "per_product": {"<slug>": {...totals summed across orgs}}
        }
    """
    now = datetime.now(tz=timezone.utc)
    start = _parse_iso(from_) or (now - timedelta(days=30))
    end = _parse_iso(to) or now
    if end < start:
        raise HTTPException(status_code=400, detail="'to' precede 'from'")
    if end - start > timedelta(days=_MAX_WINDOW_DAYS):
        raise HTTPException(status_code=400, detail=f"Janela maior que {_MAX_WINDOW_DAYS} dias")

    try:
        rows = await run_blocking(
            lambda: read_ai_usage_rows(
                db, start=start, end=end, org_id=org_id, product=product, feature=feature,
            )
        )
    except AiUsageWindowTooLarge:
        raise HTTPException(status_code=400, detail="Janela grande demais; filtre por org/produto ou reduza o período")

    agg = aggregate_ai_usage(rows)
    per_product: dict[str, dict] = {}
    for org in agg["per_org"]:
        for prod in org["per_product"]:
            bucket = per_product.setdefault(prod["product"], {k: 0 for k in agg["totals"]})
            for k in agg["totals"]:
                bucket[k] += prod[k]
    if product and product not in per_product:
        per_product[product] = {k: 0 for k in agg["totals"]}

    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "filters": {"org_id": org_id, "product": product, "feature": feature},
        **agg,
        "per_product": per_product,
    }

"""Platform-admin endpoint for aggregate LLM token usage + cost.

Reads across every product's `<schema>.llm_usage` table via the service role
(bypasses RLS). Returns a unified view filterable by product, org, and date
window. Used by the Core admin dashboard to track platform-wide LLM spend.

Access: `noctus_role == "admin"` only. Any non-admin call → 403.

LGPD note: each `llm_usage` row carries counts + provider/model/org_id +
cost estimate only — never prompt text. This endpoint inherits that
property; no new risk surface beyond the tables themselves.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.database import get_admin_client
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/llm-usage", tags=["Admin · LLM Usage"])


# Schemas to scan. Add a new product by extending this map. Each entry maps
# a product slug → the schema where its `llm_usage` table lives.
_PRODUCT_SCHEMAS: dict[str, str] = {
    "erp-imobiliario": "erp",
    "therapy-platform": "therapy",
}


async def _require_platform_admin(authorization: Optional[str]) -> None:
    user, _ = await get_current_user(authorization)
    noctus_role = (user.user_metadata or {}).get("noctus_role")
    if noctus_role != "admin":
        raise HTTPException(status_code=403, detail="Platform admin required")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid ISO date: {value}")


@router.get("")
async def aggregate_llm_usage(
    authorization: Optional[str] = Header(None),
    product: Optional[str] = Query(
        None, description="Filter by product slug (default: all products)",
    ),
    org_id: Optional[str] = Query(None, description="Filter by org/clinic id"),
    from_: Optional[str] = Query(None, alias="from", description="ISO-8601 start (default now-30d)"),
    to: Optional[str] = Query(None, description="ISO-8601 end (default now)"),
    limit_per_product: int = Query(10000, ge=1, le=50000),
):
    """Return aggregated LLM usage across all (or one) product schemas.

    Response shape::

        {
          "window": {"from": "...", "to": "..."},
          "per_product": {
            "erp-imobiliario": {
              "calls": N, "total_tokens": N, "cost_estimate_usd": X,
              "by_model": [{ provider, model, calls, ..., cost_estimate_usd }, ...]
            },
            ...
          },
          "totals": { "calls": N, "total_tokens": N, "cost_estimate_usd": X }
        }
    """
    await _require_platform_admin(authorization)

    now = datetime.now(tz=timezone.utc)
    start = _parse_iso(from_) or (now - timedelta(days=30))
    end = _parse_iso(to) or now

    targets = (
        {product: _PRODUCT_SCHEMAS[product]}
        if product and product in _PRODUCT_SCHEMAS
        else _PRODUCT_SCHEMAS
    )
    if product and product not in _PRODUCT_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unknown product: {product}")

    db = get_admin_client()
    per_product: dict[str, dict] = {}
    totals = {"calls": 0, "total_tokens": 0, "cost_estimate_usd": 0.0}

    for slug, schema in targets.items():
        try:
            query = (
                db.schema(schema)
                .table("llm_usage")
                .select("*")
                .gte("at", start.isoformat())
                .lte("at", end.isoformat())
            )
            if org_id:
                query = query.eq("org_id", org_id)
            rows = query.limit(limit_per_product).execute().data or []
        except Exception as exc:
            logger.warning("admin_llm_usage scan failed for %s: %s", slug, exc)
            rows = []

        product_totals = {"calls": 0, "total_tokens": 0, "cost_estimate_usd": 0.0}
        by_model: dict[tuple[str, str], dict] = {}
        for row in rows:
            prov = row.get("provider") or ""
            mdl = row.get("model") or ""
            bucket = by_model.setdefault((prov, mdl), {
                "provider": prov,
                "model": mdl,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_estimate_usd": 0.0,
            })
            bucket["calls"] += 1
            bucket["prompt_tokens"] += row.get("prompt_tokens") or 0
            bucket["completion_tokens"] += row.get("completion_tokens") or 0
            tt = row.get("total_tokens") or 0
            bucket["total_tokens"] += tt
            cost = float(row.get("cost_estimate_usd") or 0)
            bucket["cost_estimate_usd"] += cost

            product_totals["calls"] += 1
            product_totals["total_tokens"] += tt
            product_totals["cost_estimate_usd"] += cost

        per_product[slug] = {
            **product_totals,
            "by_model": sorted(
                by_model.values(),
                key=lambda b: b["total_tokens"],
                reverse=True,
            ),
        }
        totals["calls"] += product_totals["calls"]
        totals["total_tokens"] += product_totals["total_tokens"]
        totals["cost_estimate_usd"] += product_totals["cost_estimate_usd"]

    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "per_product": per_product,
        "totals": totals,
    }

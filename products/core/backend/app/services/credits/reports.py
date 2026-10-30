"""Credit reports — the org's usage (credits + R$ + tokens, org → product → feature)
and the platform margin report (revenue credits vs provider cost per org/product).

The org view NEVER exposes provider cost or margin: its R$ is the retail value
(credits × credit_unit_brl). The admin view does.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from noctusai_lib.integrations.llm.ledger_read import read_ai_usage_rows
from noctusai_lib.integrations.persistence import iter_paged_rows

from app.services.credits.pricing import Pricing

_USAGE_COLUMNS = (
    "id,created_at,org_id,product,feature,status,input_tokens,output_tokens,"
    "cache_read_tokens,cache_write_tokens,charged_credits"
)
_ENTRY_COLUMNS = (
    "id,created_at,org_id,product,kind,source,credits,brl_amount,usd_amount,provider_cost_brl"
)


def _tokens(row: dict[str, Any]) -> int:
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))


def _bucket() -> dict[str, Any]:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens": 0, "credits": 0.0,
            "pending_calls": 0}


def _add(b: dict[str, Any], row: dict[str, Any]) -> None:
    b["calls"] += 1
    b["input_tokens"] += int(row.get("input_tokens") or 0)
    b["output_tokens"] += int(row.get("output_tokens") or 0)
    b["tokens"] += _tokens(row)
    charged = row.get("charged_credits")
    if charged is None:
        b["pending_calls"] += 1
    else:
        b["credits"] += float(charged)


def _finish(b: dict[str, Any], unit: float) -> dict[str, Any]:
    b["credits"] = round(b["credits"], 6)
    b["brl"] = round(b["credits"] * unit, 2)
    return b


def org_usage(
    db: Any, org_id: str, *, start: datetime, end: datetime, pricing: Pricing, product: Optional[str] = None,
) -> dict[str, Any]:
    """Org → product → feature: calls, tokens, credits, R$ (retail) + a daily series per product."""
    rows = read_ai_usage_rows(db, start=start, end=end, org_id=org_id, product=product, columns=_USAGE_COLUMNS)
    unit = float(pricing.credit_unit_brl)
    totals = _bucket()
    products: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        prod_key = row.get("product") or "unattributed"
        _add(totals, row)
        prod = products.setdefault(prod_key, {**_bucket(), "_features": {}})
        _add(prod, row)
        feat = prod["_features"].setdefault(row.get("feature") or "(sem feature)", _bucket())
        _add(feat, row)
        day = str(row.get("created_at") or "")[:10]
        if day:
            daily[day][prod_key] += float(row.get("charged_credits") or 0)
    per_product = []
    for key, prod in products.items():
        features = [{"feature": fk, **_finish(fv, unit)} for fk, fv in prod.pop("_features").items()]
        features.sort(key=lambda f: (f["credits"], f["calls"]), reverse=True)
        per_product.append({"product": key, **_finish(prod, unit), "per_feature": features})
    per_product.sort(key=lambda p: (p["credits"], p["calls"]), reverse=True)
    series = [{"day": d, **{k: round(v, 6) for k, v in vals.items()}} for d, vals in sorted(daily.items())]
    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "credit_unit_brl": unit,
        "totals": _finish(totals, unit),
        "per_product": per_product,
        "daily": series,
        "products": [p["product"] for p in per_product],
    }


def _entries(db: Any, *, start: datetime, end: datetime, org_id: Optional[str]) -> list[dict[str, Any]]:
    def fetch_page(lo: int, hi: int) -> Any:
        q = (db.table("credit_entries").select(_ENTRY_COLUMNS)
             .gte("created_at", start.isoformat()).lte("created_at", end.isoformat()))
        if org_id:
            q = q.eq("org_id", org_id)
        return q.order("id").range(lo, hi).execute().data

    return list(iter_paged_rows(fetch_page, label="credit_entries window"))


def recent_entries(db: Any, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return (
        db.table("credit_entries")
        .select("id,created_at,product,feature,kind,source,credits,balance_after,brl_amount,reason")
        .eq("org_id", org_id).neq("kind", "usage_debit")
        .order("created_at", desc=True).limit(limit).execute().data or []
    )


def margin_report(db: Any, *, start: datetime, end: datetime, org_id: Optional[str] = None) -> dict[str, Any]:
    """Per org → per product: usage revenue (credits charged, at retail R$) vs provider
    cost (R$ at the row's PTAX), and the cash side (purchases) vs grants (no cash)."""
    orgs: dict[str, dict[str, Any]] = {}

    def org_bucket(key: str) -> dict[str, Any]:
        return orgs.setdefault(key, {
            "org_id": key, "revenue_brl": 0.0, "provider_cost_brl": 0.0, "debited_credits": 0.0,
            "byok_calls": 0, "purchased_brl": 0.0, "granted_brl": 0.0, "refunded_brl": 0.0, "_products": {},
        })

    for e in _entries(db, start=start, end=end, org_id=org_id):
        ob = org_bucket(str(e["org_id"]))
        kind = e.get("kind")
        brl = float(e.get("brl_amount") or 0)
        if kind == "usage_debit":
            pb = ob["_products"].setdefault(e.get("product") or "unattributed", {
                "revenue_brl": 0.0, "provider_cost_brl": 0.0, "debited_credits": 0.0, "byok_calls": 0})
            cost = float(e.get("provider_cost_brl") or 0)
            if e.get("source") == "byok":
                ob["byok_calls"] += 1
                pb["byok_calls"] += 1
                continue
            for b in (ob, pb):
                b["revenue_brl"] += brl
                b["provider_cost_brl"] += cost
                b["debited_credits"] += -float(e.get("credits") or 0)
        elif kind == "purchase":
            ob["purchased_brl"] += brl
        elif kind == "grant":
            ob["granted_brl"] += brl
        elif kind == "refund":
            ob["refunded_brl"] += -brl

    def finish(b: dict[str, Any]) -> dict[str, Any]:
        rev, cost = b["revenue_brl"], b["provider_cost_brl"]
        b["gross_margin_brl"] = round(rev - cost, 2)
        b["gross_margin_pct"] = round((rev - cost) / rev, 4) if rev > 0 else None
        for k in ("revenue_brl", "provider_cost_brl", "debited_credits", "purchased_brl", "granted_brl", "refunded_brl"):
            if k in b:
                b[k] = round(b[k], 2 if k.endswith("_brl") else 6)
        return b

    per_org = []
    totals = {"revenue_brl": 0.0, "provider_cost_brl": 0.0, "purchased_brl": 0.0, "granted_brl": 0.0}
    for ob in orgs.values():
        products = [{"product": k, **finish(v)} for k, v in ob.pop("_products").items()]
        products.sort(key=lambda p: p["revenue_brl"], reverse=True)
        for k in totals:
            totals[k] += ob[k]
        per_org.append({**finish(ob), "per_product": products})
    per_org.sort(key=lambda o: o["revenue_brl"], reverse=True)
    rev, cost = totals["revenue_brl"], totals["provider_cost_brl"]
    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "totals": {**{k: round(v, 2) for k, v in totals.items()},
                   "gross_margin_brl": round(rev - cost, 2),
                   "gross_margin_pct": round((rev - cost) / rev, 4) if rev > 0 else None},
        "per_org": per_org,
    }


__all__ = ["margin_report", "org_usage", "recent_entries"]

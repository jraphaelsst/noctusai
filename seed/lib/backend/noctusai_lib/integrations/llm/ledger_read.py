"""Reading the central AI-usage ledger (``public.ai_usage``, roadmap D25).

One reader + one aggregator shared by every surface that shows LLM spend —
core's platform-admin ``/api/admin/llm-usage``, the seed ``/api/llm/usage``
every product inherits, social-wiring's custos page — so the per org →
per product → per feature roll-up is computed in exactly one place.

The read is paged (PostgREST caps every response at 1 000 rows —
KB § PATTERNS/backend/postgrest-row-cap.md) and bounded: a window larger
than ``max_pages`` pages raises `AiUsageWindowTooLarge` instead of
returning a silently truncated total.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.paging import PagerOverflowError

from .ledger import AI_USAGE_TABLE

__all__ = [
    "AI_USAGE_COLUMNS",
    "AiUsageWindowTooLarge",
    "aggregate_ai_usage",
    "read_ai_usage_rows",
]

AI_USAGE_COLUMNS = (
    "id,created_at,org_id,product,feature,purpose,user_id,agent_key,provider,model,operation,"
    "input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,image_input_tokens,"
    "image_output_tokens,cost_usd,cost_brl,status"
)
_DEFAULT_MAX_PAGES = 200  # 200 000 rows


class AiUsageWindowTooLarge(PagerOverflowError):
    """The filtered window holds more rows than one request may aggregate."""


def read_ai_usage_rows(
    db: Any,
    *,
    start: datetime,
    end: datetime,
    org_id: Optional[str] = None,
    product: Optional[str] = None,
    feature: Optional[str] = None,
    columns: str = AI_USAGE_COLUMNS,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> list[dict]:
    """Every ``public.ai_usage`` row in ``[start, end]`` matching the filters.

    ``db`` must target the ``public`` schema (core's admin client, a product's
    ``get_core_client()``, or a user client already pinned to ``public`` —
    RLS then limits the rows to the caller's orgs). Sync — call it off the
    event loop."""

    def fetch_page(lo: int, hi: int) -> Any:
        q = (
            db.table(AI_USAGE_TABLE)
            .select(columns)
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat())
        )
        if org_id:
            q = q.eq("org_id", org_id)
        if product:
            q = q.eq("product", product)
        if feature:
            q = q.eq("feature", feature)
        return q.order("id").range(lo, hi).execute().data

    return list(
        iter_paged_rows(
            fetch_page, max_pages=max_pages, label="ai_usage window",
            overflow_error=AiUsageWindowTooLarge,
        )
    )


def _bucket() -> dict[str, Any]:
    return {
        "calls": 0,
        "errors": 0,
        "partial": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "image_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "cost_brl": 0.0,
    }


def _add(bucket: dict[str, Any], row: dict) -> None:
    bucket["calls"] += 1
    status = row.get("status") or "ok"
    if status == "error":
        bucket["errors"] += 1
    elif status == "partial":
        bucket["partial"] += 1
    inp = int(row.get("input_tokens") or 0)
    out = int(row.get("output_tokens") or 0)
    bucket["input_tokens"] += inp
    bucket["output_tokens"] += out
    bucket["cache_read_tokens"] += int(row.get("cache_read_tokens") or 0)
    bucket["cache_write_tokens"] += int(row.get("cache_write_tokens") or 0)
    bucket["image_tokens"] += int(row.get("image_input_tokens") or 0) + int(row.get("image_output_tokens") or 0)
    bucket["total_tokens"] += inp + out
    bucket["cost_usd"] += float(row.get("cost_usd") or 0)
    bucket["cost_brl"] += float(row.get("cost_brl") or 0)


def _round(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["cost_usd"] = round(bucket["cost_usd"], 6)
    bucket["cost_brl"] = round(bucket["cost_brl"], 6)
    return bucket


def _sorted_children(children: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    out = []
    for key, node in children.items():
        out.append({key_name: key, **node})
    out.sort(key=lambda n: n["cost_usd"], reverse=True)
    return out


def aggregate_ai_usage(rows: Iterable[dict]) -> dict[str, Any]:
    """Roll rows up: ``totals`` + ``per_org[] → per_product[] → per_feature[]``
    (+ ``by_model[]`` per product), each level sorted by cost desc."""
    totals = _bucket()
    orgs: dict[str, dict[str, Any]] = {}
    for row in rows:
        _add(totals, row)
        org_key = str(row.get("org_id") or "")
        org = orgs.setdefault(org_key, {**_bucket(), "_products": {}})
        _add(org, row)
        prod_key = row.get("product") or "unattributed"
        prod = org["_products"].setdefault(prod_key, {**_bucket(), "_features": {}, "_models": {}})
        _add(prod, row)
        feat = prod["_features"].setdefault(row.get("feature") or "(sem feature)", _bucket())
        _add(feat, row)
        model = prod["_models"].setdefault(f"{row.get('provider') or ''}\x00{row.get('model') or ''}", _bucket())
        _add(model, row)

    per_org = []
    for org_key, org in orgs.items():
        products = []
        for prod_key, prod in org.pop("_products").items():
            features = [_round(f) for f in _sorted_children(prod.pop("_features"), "feature")]
            models = []
            for mk, m in prod.pop("_models").items():
                provider, model = mk.split("\x00", 1)
                models.append({"provider": provider, "model": model, **_round(m)})
            models.sort(key=lambda m: m["cost_usd"], reverse=True)
            products.append({"product": prod_key, **_round(prod), "per_feature": features, "by_model": models})
        products.sort(key=lambda p: p["cost_usd"], reverse=True)
        per_org.append({"org_id": org_key or None, **_round(org), "per_product": products})
    per_org.sort(key=lambda o: o["cost_usd"], reverse=True)
    return {"totals": _round(totals), "per_org": per_org}

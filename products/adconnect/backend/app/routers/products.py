from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..data.store import store

router = APIRouter()


@router.get("/")
def list_products(
    category: str | None = None,
    q: str | None = None,
    sort: str | None = Query(None, pattern="^(name|price|cashback)$"),
    inStockOnly: bool | None = None,
) -> dict[str, Any]:
    items = list(store.products)

    if category and category != "all":
        items = [p for p in items if p["category"] == category]

    if q and q.strip():
        ql = q.lower()
        items = [
            p
            for p in items
            if ql in p["name"].lower() or ql in p["sku"].lower()
        ]

    if inStockOnly:
        items = [p for p in items if p["inStock"]]

    if sort == "price":
        items.sort(key=lambda p: p["priceB2B"])
    elif sort == "cashback":
        items.sort(key=lambda p: -p["cashback"])
    else:
        items.sort(key=lambda p: p["name"])

    return {"data": items}


@router.get("/categories")
def list_categories() -> dict[str, Any]:
    result = []
    for c in store.categories:
        count = sum(1 for p in store.products if p["category"] == c["id"])
        result.append({**c, "count": count})
    return {"data": result}


@router.get("/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    p = next((x for x in store.products if x["id"] == product_id), None)
    if not p:
        raise HTTPException(404, "Produto não encontrado")
    return p

from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException

from ..data.store import store


def find_product(pid: str) -> dict[str, Any]:
    p = next((x for x in store.products if x["id"] == pid), None)
    if not p:
        raise HTTPException(404, f"Produto {pid} não encontrado")
    return p


def calc_quote(
    items: Iterable[dict[str, Any]],
    use_cashback: bool = False,
    use_verba: bool = False,
    cashback_balance: float = 0.0,
    verba_balance: float = 0.0,
) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for item in items:
        p = find_product(item["productId"])
        qty = int(item["quantity"])
        warnings: list[str] = []

        if not p["inStock"]:
            warnings.append("Produto indisponível")
        if qty < p["minOrder"]:
            raise HTTPException(
                400,
                f"Quantidade mínima do produto {p['sku']} é {p['minOrder']}un",
            )
        if qty % p["multiple"] != 0:
            raise HTTPException(
                400,
                f"Quantidade do produto {p['sku']} deve ser múltiplo de {p['multiple']}un",
            )

        line_total = p["priceB2B"] * qty
        cashback_value = line_total * p["cashback"] / 100
        # Verba MKT: metade (arredondada p/ baixo) do % de cashback — mesmo critério do mock original.
        verba_mkt_value = line_total * (p["cashback"] // 2) / 100

        lines.append(
            {
                "productId": p["id"],
                "sku": p["sku"],
                "name": p["name"],
                "quantity": qty,
                "priceB2B": p["priceB2B"],
                "cashbackPct": p["cashback"],
                "lineTotal": line_total,
                "cashbackValue": cashback_value,
                "verbaMktValue": verba_mkt_value,
                "warnings": warnings,
            }
        )

    subtotal = sum(line_val["lineTotal"] for line_val in lines)
    total_cashback = sum(line_val["cashbackValue"] for line_val in lines)
    total_verba = sum(line_val["verbaMktValue"] for line_val in lines)

    cashback_applied = (
        min(cashback_balance, subtotal * 0.15) if use_cashback else 0.0
    )
    verba_applied = (
        min(verba_balance, (subtotal - cashback_applied) * 0.10) if use_verba else 0.0
    )
    discount = cashback_applied + verba_applied
    total = subtotal - discount

    return {
        "lines": lines,
        "subtotal": subtotal,
        "totalCashbackEarned": total_cashback,
        "totalVerbaMktEarned": total_verba,
        "cashbackApplied": cashback_applied,
        "verbaMktApplied": verba_applied,
        "discount": discount,
        "total": total,
    }

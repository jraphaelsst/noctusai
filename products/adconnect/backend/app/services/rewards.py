from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..data.store import store

TIER_CONFIG: list[dict[str, Any]] = [
    {"key": "STARTER", "label": "Starter", "annualMin": 0, "annualMax": 500_000},
    {"key": "INSIDER", "label": "Insider", "annualMin": 500_000, "annualMax": 1_000_000},
    {"key": "MASTER", "label": "Master", "annualMin": 1_000_000, "annualMax": 2_000_000},
    {"key": "SMARTER", "label": "Smarter", "annualMin": 2_000_000, "annualMax": float("inf")},
]


def resolve_tier(annual_revenue: float) -> str:
    for t in TIER_CONFIG:
        if t["annualMin"] <= annual_revenue < t["annualMax"]:
            return t["key"]
    return "STARTER"


def history_for(distributor_id: str) -> list[dict[str, Any]]:
    return [h for h in store.rewards_history if h.get("distributorId") == distributor_id]


def balance_for(distributor_id: str) -> dict[str, float]:
    rows = history_for(distributor_id)

    def sum_by(type_: str, status: str) -> float:
        return sum(r["amount"] for r in rows if r["type"] == type_ and r["status"] == status)

    return {
        "cashbackAvailable": sum_by("cashback", "Liberado") - sum_by("cashback", "Utilizado"),
        "cashbackPending": sum_by("cashback", "Pendente"),
        "cashbackUsed": sum_by("cashback", "Utilizado"),
        "verbaMktAvailable": sum_by("verba_mkt", "Liberado") - sum_by("verba_mkt", "Utilizado"),
        "verbaMktPending": sum_by("verba_mkt", "Pendente"),
        "verbaMktUsed": sum_by("verba_mkt", "Utilizado"),
    }


def tier_status(distributor_id: str) -> dict[str, Any]:
    d = next((x for x in store.distributors if x["id"] == distributor_id), None)
    if not d:
        raise HTTPException(404, "Distribuidor não encontrado")

    current = resolve_tier(d["annualRevenue"])
    idx = next((i for i, t in enumerate(TIER_CONFIG) if t["key"] == current), -1)
    nxt = TIER_CONFIG[idx + 1] if 0 <= idx < len(TIER_CONFIG) - 1 else None

    meta = d.get("annualGoal") or (TIER_CONFIG[idx]["annualMax"] if idx >= 0 else 1) or 1
    progress = min(100, round((d["annualRevenue"] / meta) * 100)) if meta else 0

    return {
        "current": current,
        "currentLabel": TIER_CONFIG[idx]["label"] if idx >= 0 else current,
        "annualRevenue": d["annualRevenue"],
        "annualGoal": d.get("annualGoal"),
        "progressPct": progress,
        "next": nxt["key"] if nxt else None,
        "nextLabel": nxt["label"] if nxt else None,
        "remainingToNext": max(0, nxt["annualMin"] - d["annualRevenue"]) if nxt else 0,
    }

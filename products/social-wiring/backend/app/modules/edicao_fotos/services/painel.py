"""`GET /api/edicao-fotos/painel` — contract §8, one RPC round-trip.

Thin wrapper, same shape as `app.modules.leads.services.analytics_service`'s
SQL-side functions: build the RPC params, call the one matching SQL function
(`social_wiring.fotos_painel`, migration 133), return its JSONB payload
as-is. The aggregation itself lives in Postgres — see that migration's
header for the scope rules (org filter, platform-wide queue, absent
billing)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


def painel(
    client: Any,
    *,
    org_id: Optional[str],
    desde: Optional[date],
    ate: Optional[date],
) -> dict:
    params = {
        "p_org_id": org_id,
        "p_desde": desde.isoformat() if desde else None,
        "p_ate": ate.isoformat() if ate else None,
    }
    resp = client.rpc("fotos_painel", params).execute()
    return resp.data or {}


__all__ = ["painel"]

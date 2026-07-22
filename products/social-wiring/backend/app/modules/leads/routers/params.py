"""The canonical Leads filter set (§5.1), shared verbatim by
``routers/leads.py`` and ``routers/analytics.py`` — one FastAPI dependency,
one place the query-param shape is declared. Unknown query params are
never 422'd (FastAPI's default: undeclared params are ignored), matching
"the FE adds params over time" from the contract.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import Query

from app.modules.leads.services.query import LeadFilters


def get_lead_filters(
    de: Optional[date] = Query(default=None),
    ate: Optional[date] = Query(default=None),
    ano: Optional[list[int]] = Query(default=None),
    mes: Optional[list[int]] = Query(default=None),
    origem_id: Optional[list[UUID]] = Query(default=None),
    corretor_id: Optional[list[UUID]] = Query(default=None),
    tipo: Optional[list[str]] = Query(default=None),
    tier: Optional[list[str]] = Query(default=None),
    empreendimento: Optional[list[str]] = Query(default=None),
    regiao: Optional[list[str]] = Query(default=None),
    needs_review: Optional[bool] = Query(default=None),
    q: Optional[str] = Query(default=None),
) -> LeadFilters:
    return LeadFilters(
        de=de,
        ate=ate,
        ano=ano or [],
        mes=mes or [],
        origem_id=origem_id or [],
        corretor_id=corretor_id or [],
        tipo=tipo or [],
        tier=tier or [],
        empreendimento=empreendimento or [],
        regiao=regiao or [],
        needs_review=needs_review,
        q=q,
    )


__all__ = ["get_lead_filters"]

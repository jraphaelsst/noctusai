"""Relatórios — comercial e financeiro (roadmap E1).

  GET /api/relatorios/{tipo}?inicio=&fim=&formato=json|pdf|csv

`tipo` is `comercial` or `financeiro`; `formato` defaults to `json` (the
seed `{"data": ...}` envelope) and switches to a downloadable `csv`/`pdf`
otherwise. All the actual computation lives in `app/services/relatorios.py`
as pure data (`gerar_relatorio`) — this router is HTTP plumbing only: parse
the query, call the service, pick a rendering.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.services.relatorios import gerar_relatorio, para_csv, para_pdf
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])

Formato = Literal["json", "pdf", "csv"]


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


@router.get("/{tipo}")
async def obter_relatorio(
    tipo: Literal["comercial", "financeiro"],
    inicio: date,
    fim: date,
    formato: Formato = Query(default="json"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
):
    """Funnel/won-lost/orçamentos (comercial) or faturamento/DRE-lite
    (financeiro) for `[inicio, fim]`. See `gerar_relatorio`'s docstring for
    exactly what each field means — this is the one function computing it,
    whether the caller is this route, a cron job, or an MCP tool."""
    org_id = _org(auth)
    try:
        relatorio = gerar_relatorio(repos, org_id, tipo, inicio, fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if formato == "csv":
        nome = f"relatorio-{tipo}-{inicio}-{fim}.csv"
        return StreamingResponse(
            iter([para_csv(relatorio)]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    if formato == "pdf":
        nome = f"relatorio-{tipo}-{inicio}-{fim}.pdf"
        return StreamingResponse(
            iter([para_pdf(relatorio)]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    return success_response(relatorio)

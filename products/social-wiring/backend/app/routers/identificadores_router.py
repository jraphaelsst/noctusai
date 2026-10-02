"""`GET /api/identificadores/nao-conformes` — the operators' queue of stored
document numbers that do not fit their type (migration 187's
`vw_identificadores_nao_conformes`), with a pt-BR reason and where to fix each.

READ ONLY. Correcting a value goes through the existing manual-edit endpoints
(clientes PATCH / imovel dados PATCH), which canonicalize and validate on
write. Org-scoped by the caller's org; no token → 401.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.dependencies import coerce_org_uuid, get_current_user_org, get_scoped_admin_client
from app.services import identificadores_revisao as revisao

router = APIRouter(prefix="/api/identificadores", tags=["identificadores"])


@router.get("/nao-conformes")
def listar_nao_conformes(
    situacao: Literal["nao_cabe", "canonizavel"] = Query("nao_cabe"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    return revisao.listar_nao_conformes(
        client, org_id, situacao=situacao, page=page, page_size=page_size
    )

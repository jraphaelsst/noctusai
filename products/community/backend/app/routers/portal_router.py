"""Member portal router — contract §Member portal, slice BE-A
(`GET /api/portal/minha-conta` only). `POST /api/portal/assinatura/
cancelar` and `/api/portal/grupoterapia*` belong to other slices and are
mounted from their own router modules.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_admin_client, get_membro_context
from app.schemas.portal import MinhaContaOut
from app.services.portal_service import minha_conta

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("/minha-conta", response_model=MinhaContaOut)
async def get_minha_conta(auth: tuple = Depends(get_membro_context)) -> MinhaContaOut:
    _user, _token, org_id, membro = auth
    client = get_admin_client()
    result = await minha_conta(client, org_id=org_id, membro=membro)
    return MinhaContaOut(**result)

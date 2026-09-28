"""Member-portal grupoterapia router — contract §Grupoterapia, member side
(slice BE-D).

Auth: `Depends(get_membro_context)` on every route — 401 with no/invalid
JWT (the base auth chain), 403 "Área exclusiva para membros." for a
non-`membro` JWT. See `app/services/portal_grupoterapia_service.py` for
the tier-first / service-role-read security rationale.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.dependencies import (
    actor_uuid,
    get_admin_client,
    get_membro_context,
    get_user_client,
    http_error,
)
from app.schemas.grupoterapia import ReservaStatus, SessaoPortalListResponse
from app.services.portal_grupoterapia_service import (
    PortalGrupoterapiaError,
    PortalGrupoterapiaService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal/grupoterapia", tags=["portal-grupoterapia"])


def _service(auth: tuple) -> PortalGrupoterapiaService:
    _user, token, org_id, membro = auth
    return PortalGrupoterapiaService(
        user_client=get_user_client(token),
        admin_client=get_admin_client(),
        org_id=org_id,
        membro=membro,
    )


@router.get("", response_model=SessaoPortalListResponse)
async def listar_sessoes(
    auth: tuple = Depends(get_membro_context),
) -> SessaoPortalListResponse:
    result = await _service(auth).listar()
    return SessaoPortalListResponse(**result)


@router.post("/{sessao_id}/reserva", response_model=ReservaStatus)
async def reservar(
    sessao_id: str,
    auth: tuple = Depends(get_membro_context),
) -> ReservaStatus:
    user, _token, _org_id, _membro = auth
    try:
        outcome = await _service(auth).reservar(
            sessao_id=sessao_id, autor_id=actor_uuid(user),
        )
    except PortalGrupoterapiaError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return ReservaStatus(status=outcome)


@router.delete("/{sessao_id}/reserva", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar_reserva(
    sessao_id: str,
    auth: tuple = Depends(get_membro_context),
) -> None:
    user, _token, _org_id, _membro = auth
    await _service(auth).cancelar(sessao_id=sessao_id, autor_id=actor_uuid(user))
    return None

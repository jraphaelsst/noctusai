"""`GET|PUT /api/edicao-fotos/notificacoes/preferencias` — self-service
per-user opt-in for the "batch ready" notification (plan §1
"Notifications", migration 131).

Any authenticated member manages their OWN row only (`actor.user_id`,
never a body-supplied id) — the platform + org on/off switches live
elsewhere (`/configuracoes/plataforma`, `/configuracoes`); this route is
ONLY the per-user layer. `ativo=true` only matters when the caller is an
agency admin (`AGENCY_ADMIN_ROLES`) — the fan-out
(`services/notifier.py`) never reads a non-admin's `ativo`, but every
member (including a corretor who might one day create a batch) can still
register a WhatsApp number here for when THEY are the creator."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from noctusai_lib.domain.photo_editing import Actor

from app.modules.edicao_fotos.deps import get_preferences_repository, require_member
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import notificacao_preferencia_out
from app.modules.edicao_fotos.schemas import NotificacaoPreferenciaBody
from app.modules.edicao_fotos.services.notificacoes_preferencias import (
    InvalidWhatsappNumberError,
    NotificationPreferencesRepository,
)

router = APIRouter(prefix="/api/edicao-fotos/notificacoes", tags=["edicao-fotos"])


@router.get("/preferencias")
async def get_preferencia_route(
    actor: Actor = Depends(require_member),
    preferences: NotificationPreferencesRepository = Depends(get_preferences_repository),
) -> dict:
    pref = await preferences.get(org_id=actor.org_id, user_id=actor.user_id)
    return notificacao_preferencia_out(pref)


@router.put("/preferencias")
async def put_preferencia_route(
    body: NotificacaoPreferenciaBody,
    actor: Actor = Depends(require_member),
    preferences: NotificationPreferencesRepository = Depends(get_preferences_repository),
) -> dict:
    try:
        pref = await preferences.save(
            org_id=actor.org_id,
            user_id=actor.user_id,
            ativo=body.ativo,
            whatsapp_number=body.whatsapp_number,
        )
    except InvalidWhatsappNumberError as exc:
        raise api_error(422, "whatsapp_invalido", str(exc)) from exc
    return notificacao_preferencia_out(pref)

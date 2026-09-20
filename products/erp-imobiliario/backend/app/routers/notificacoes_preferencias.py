"""
Notificação Preferências Router — per-channel/event notification toggles.

`erp.notificacao_preferencias` (migration 001_erp_imobiliario.sql) has
existed since the table's own migration, but no route ever read or wrote
it: the FE panel (`pages/Notificacoes.tsx`, `hooks/useNotificacoes.ts`)
called `GET`/`PATCH /api/notificacoes/preferencias`, which no router
declared — every one of the panel's 24 channel switches rendered "on"
regardless of stored state (`getPrefAtivo`'s not-found fallback) and
flipping one persisted nothing (2026-09-20 wiring audit, task 8). This
router is the missing piece; the table + its RLS policy are untouched.

Mounted at the SAME `/api/notificacoes` prefix the seed framework's
standard `notificacoes` router already owns (`GET ""`, `GET /contagem`,
`PATCH /{id}/ler`, `POST /ler-todas`) — this adds only the `/preferencias`
sub-resource, which is erp-local (the table lives in `erp`, not a shared
schema), so it is a product router, not a seed one.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import Field

from app.dependencies import get_current_user, get_org_id, get_user_client
from app.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notificacoes", tags=["Notificações"])

#: Mirrors the migration's own CHECK (`canal IN ('app','email','whatsapp')`).
CanalNotificacao = str


class AtualizarPreferenciaRequest(StrictHttpModel):
    canal: str = Field(..., pattern="^(app|email|whatsapp)$")
    tipo_evento: str = Field(..., min_length=1, max_length=100)
    ativo: bool


@router.get("/preferencias")
async def listar_preferencias(auth=Depends(get_current_user)):
    """List the caller's stored preference rows.

    An unlisted `(canal, tipo_evento)` pair simply has no row yet — the
    FE's `getPrefAtivo` already treats an absent row as `ativo=true`
    (opt-out model), so this endpoint returns only what has ever been
    explicitly saved, never a synthesized full 24-row grid.
    """
    user, token = auth
    db = get_user_client(token)
    result = (
        db.table("notificacao_preferencias")
        .select("canal, tipo_evento, ativo")
        .eq("user_id", user.id)
        .execute()
    )
    return success_response(result.data or [])


@router.patch("/preferencias")
async def atualizar_preferencia(
    body: AtualizarPreferenciaRequest,
    auth=Depends(get_current_user),
):
    """Upsert one `(canal, tipo_evento)` preference row for the caller.

    `UNIQUE(user_id, canal, tipo_evento)` (migration 001) is the
    upsert's own conflict target, so flipping the same switch twice is
    idempotent rather than a duplicate-row error.
    """
    user, token = auth
    db = get_user_client(token)
    org_id: Optional[str] = get_org_id(user)

    payload = {
        "org_id": org_id,
        "user_id": user.id,
        "canal": body.canal,
        "tipo_evento": body.tipo_evento,
        "ativo": body.ativo,
    }
    result = (
        db.table("notificacao_preferencias")
        .upsert(payload, on_conflict="user_id,canal,tipo_evento")
        .execute()
    )
    row = result.data[0] if result.data else payload
    return success_response(row)

"""The `/julia/agente` page backend: LINE ROUTING only (julia-v2 CONTRACT Q4 / 0.3, white-label, per org).

Julia is hosted in agents. How she behaves (on / draining / off, the content, the qualification, the conversations) is
configured THERE and this page is not wired to it -- it only links to it. What this page owns is TRANSPORT config, and it
must work for ANY org (no org-specific names, no behaviour):

  GET /api/julia/roteamento                         member   the org's WhatsApp lines: which ones feed the agent, who gets the
                                                             hand-off note, the link to the agent's own settings
  PUT /api/julia/roteamento/linhas/{connection_id}  admin    {alimenta: bool, destino_handoff_user_id?: uuid|null}
                                                             "this number feeds the agent" + the hand-off notification target

`alimenta` is `whatsapp_connections.agente_leads_ativo` (the routing switch, a separate thing from the agent's own
ligado / drenando / desligado in agents). Turning it ON keeps every precondition of the legacy surface (authorised
numbers, webhook HMAC, a complete privacy notice and the 11.1 snapshot of the existing chats) -- the SAME function
(`julia_agente_router.aplicar_conexao`) does the work, so there is one routing implementation, not two.

The hand-off target defaults to the ORG OWNER (julia-v2 0.4 owner decision); a configured user wins while still owner/admin.
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_settings
from app.routers.julia_agente_router import _record_or_404, _require_admin, aplicar_conexao
from app.routers.whatsapp_connections_router import get_connection_store, get_waha_client_factory
from app.services import julia_agente_service as julia
from app.services.whatsapp_connection_store import WhatsAppConnectionRecord, WhatsAppConnectionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["julia-roteamento"])


class LinhaRoteamentoUpdate(StrictHttpModel):
    #: "this number feeds the agent".
    alimenta: bool
    #: Absent = keep; explicit null = back to the default (the org owner).
    destino_handoff_user_id: Optional[UUID] = None


def _linha_out(c: WhatsAppConnectionRecord) -> dict[str, Any]:
    return {
        "connection_id": str(c.id),
        "label": c.label,
        "alimenta": bool(c.agente_leads_ativo),
        "alimenta_desde": c.agente_leads_ativado_em,
        "numeros_autorizados": len([n for n in (c.authorized_numbers or []) if str(n).strip()]),
        # None = the default (the org owner)
        "destino_handoff_user_id": str(c.agente_handoff_notificar_user_id) if c.agente_handoff_notificar_user_id else None,
    }


@router.get("/api/julia/roteamento")
def get_roteamento(
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    """The org's lines and the routing of each. No agent state, no behaviour: that is agents' (`agents_url` links there)."""
    org_id = coerce_org_uuid(auth[2])
    dono = julia.dono_da_org(get_core_client(), org_id)
    return {"data": {
        "linhas": [_linha_out(c) for c in store.list_connections(org_id=org_id)],
        "destino_handoff_padrao": {"tipo": "dono_da_organizacao", "user_id": str(dono) if dono else None},
        # Resolved server-side from the product-URL registry, never hard-coded in the FE. Null = unresolvable.
        "agents_url": julia.agents_base_url(),
    }}


@router.put("/api/julia/roteamento/linhas/{connection_id}")
async def put_linha(
    connection_id: UUID,
    payload: LinhaRoteamentoUpdate,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    cfg=Depends(get_settings),
    waha_factory=Depends(get_waha_client_factory),
    request: Request = None,
) -> dict[str, Any]:
    _user, org_id = _require_admin(auth, request, "O roteamento")
    record = _record_or_404(store, connection_id, org_id, decrypt=True)
    updated = await aplicar_conexao(
        record=record, org_id=org_id, store=store, cfg=cfg, waha_factory=waha_factory,
        ativo=payload.alimenta, key=None,
        handoff_definido="destino_handoff_user_id" in payload.model_fields_set,
        handoff_alvo=payload.destino_handoff_user_id,
    )
    return {"data": _linha_out(updated)}


__all__ = ["router"]

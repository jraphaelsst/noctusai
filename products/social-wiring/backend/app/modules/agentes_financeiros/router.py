"""HTTP surface for the financing-agent registry.

Auth pattern: `Depends(get_current_user_org)` for the user/org, PLUS
`Depends(get_social_wiring_client)` for the caller's own RLS-scoped
`social_wiring` client — a real `Depends()` seam, not a manual
`get_user_client(token)` call inside the route body (that shape does not
chain via `Depends(get_user_client)` because its positional `token` argument
becomes a required query parameter, AND it re-derives `.schema(...)` fresh
per call, which silently loses every prior write against
`MockSupabaseClient` — see `app.dependencies.get_scoped_user_client`'s
docstring). See `KB § PATTERNS/backend.md § Auth — canonical pattern`.

🔴 THE USER'S OWN TOKEN, NOT THE ADMIN CLIENT. Migration 100 gives this table
a write policy for `authenticated`, so RLS is what scopes every read and write
here — see `service.py`'s header for why this table is shaped that way when
most of the schema is not.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_social_wiring_client,
)
from app.modules.agentes_financeiros import service as svc
from app.modules.agentes_financeiros.schemas import (
    AgenteFinanceiroCreateBody,
    AgenteFinanceiroPatchBody,
)

router = APIRouter(prefix="/api/agentes-financeiros", tags=["agentes-financeiros"])


def _parts(auth: tuple, client: Any):
    user, _token, raw_org = auth
    return user, client, coerce_org_uuid(raw_org)


@router.get("")
def list_agentes_route(
    incluir_inativos: bool = Query(
        default=False,
        description=(
            "Include retired agents. The card's dropdown leaves this false so "
            "it cannot offer a retired bank; the management page passes true, "
            "since it is where one is reactivated."
        ),
    ),
    auth: tuple = Depends(get_current_user_org),
    supabase: Any = Depends(get_social_wiring_client),
) -> dict:
    _user, client, org_id = _parts(auth, supabase)
    return svc.listar(client, org_id, incluir_inativos=incluir_inativos)


@router.post("", status_code=201)
def create_agente_route(
    body: AgenteFinanceiroCreateBody,
    auth: tuple = Depends(get_current_user_org),
    supabase: Any = Depends(get_social_wiring_client),
) -> dict:
    user, client, org_id = _parts(auth, supabase)
    return svc.criar(
        client,
        org_id,
        dados=body.model_dump(exclude_unset=True),
        user_id=getattr(user, "id", None),
    )


@router.patch("/{agente_id}")
def update_agente_route(
    agente_id: UUID,
    body: AgenteFinanceiroPatchBody,
    auth: tuple = Depends(get_current_user_org),
    supabase: Any = Depends(get_social_wiring_client),
) -> dict:
    user, client, org_id = _parts(auth, supabase)
    # `exclude_unset` is what makes this a PATCH rather than a PUT: an omitted
    # field is left alone, an explicit null clears it.
    return svc.atualizar(
        client,
        org_id,
        agente_id,
        dados=body.model_dump(exclude_unset=True),
        user_id=getattr(user, "id", None),
    )


@router.delete("/{agente_id}", status_code=204)
def delete_agente_route(
    agente_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    supabase: Any = Depends(get_social_wiring_client),
):
    # No return annotation: FastAPI reads `-> None` as a declared response
    # model and refuses it against 204, which must not carry a body.
    _user, client, org_id = _parts(auth, supabase)
    svc.remover(client, org_id, agente_id)


__all__ = ["router"]

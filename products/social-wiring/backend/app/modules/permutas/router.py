"""HTTP surface for property-swap matching.

Auth pattern: `Depends(get_current_user_org)` returning
`(user, token, raw_org_id)`, then `get_user_client(token)` inside the body —
the seed's `Depends(get_user_client)` shape does not chain because its
positional `token` argument becomes a required query parameter. See
`KB § PATTERNS/backend.md § Auth — canonical pattern`.

🔴 ROUTE ORDER: `/matches` and `/gerar` are declared BEFORE `/{ativo_id}`.
FastAPI resolves in registration order, so a literal second segment must
precede the dynamic one or `/api/permutas/matches` binds to `/{ativo_id}` and
422s on "matches" not being a UUID — the same hazard `main.py` documents at the
MODULES level for `clientes_router`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import coerce_org_uuid, get_current_user_org, get_user_client
from app.modules.permutas import embeddings as emb
from app.modules.permutas import service as svc
from app.modules.permutas.schemas import (
    AtivoCreateBody,
    AtivoPatchBody,
    EmbutirBody,
    EtapaPatchBody,
    GerarMatchesBody,
)

router = APIRouter(prefix="/api/permutas", tags=["permutas"])


def _parts(auth: tuple):
    user, token, raw_org = auth
    return user, get_user_client(token), coerce_org_uuid(raw_org)


# ── Matches (literal paths first — see the module header) ───────────────────


@router.get("/matches")
def list_matches_route(
    etapa: Optional[str] = Query(default=None),
    ativo_id: Optional[UUID] = Query(default=None),
    score_minimo: Optional[float] = Query(default=None, ge=0, le=100),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, client, org_id = _parts(auth)
    return svc.listar_matches(
        client, org_id, etapa=etapa, ativo_id=ativo_id, score_minimo=score_minimo
    )


@router.patch("/matches/{match_id}")
def patch_match_route(
    match_id: UUID,
    body: EtapaPatchBody,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, client, org_id = _parts(auth)
    return svc.atualizar_etapa(
        client,
        org_id,
        match_id,
        etapa=body.etapa,
        observacoes=body.observacoes,
        user_id=getattr(user, "id", None),
    )


@router.post("/gerar")
def gerar_route(
    body: GerarMatchesBody,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, client, org_id = _parts(auth)
    kwargs = {"ativo_id": body.ativo_id}
    if body.score_minimo is not None:
        kwargs["score_minimo"] = body.score_minimo
    return svc.gerar_matches(client, org_id, **kwargs)


@router.post("/embeddings")
async def embutir_route(
    body: EmbutirBody,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    """Generate both vectors for the org's ativos.

    Async because the provider call is; everything else in this router is
    sync, which is correct — the Supabase client is blocking and marking those
    handlers async would only move the block onto the event loop.
    """
    _user, client, org_id = _parts(auth)
    return await emb.embutir_ativos(
        client,
        org_id,
        apenas_pendentes=body.apenas_pendentes,
        ativo_ids=body.ativo_ids,
    )


# ── Registry ────────────────────────────────────────────────────────────────


@router.get("")
def list_ativos_route(
    natureza: Optional[str] = Query(default=None),
    corretor_id: Optional[UUID] = Query(default=None),
    incluir_inativos: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, client, org_id = _parts(auth)
    return svc.listar_ativos(
        client,
        org_id,
        natureza=natureza,
        corretor_id=corretor_id,
        incluir_inativos=incluir_inativos,
    )


@router.post("", status_code=201)
def create_ativo_route(
    body: AtivoCreateBody,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, client, org_id = _parts(auth)
    return svc.criar_ativo(
        client,
        org_id,
        dados=_dump(body),
        user_id=getattr(user, "id", None),
    )


@router.get("/{ativo_id}")
def get_ativo_route(
    ativo_id: UUID,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, client, org_id = _parts(auth)
    return svc.obter_ativo(client, org_id, ativo_id)


@router.patch("/{ativo_id}")
def patch_ativo_route(
    ativo_id: UUID,
    body: AtivoPatchBody,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, client, org_id = _parts(auth)
    return svc.atualizar_ativo(
        client,
        org_id,
        ativo_id,
        dados=_dump(body),
        user_id=getattr(user, "id", None),
    )


@router.delete("/{ativo_id}", status_code=204)
def delete_ativo_route(
    ativo_id: UUID,
    auth: tuple = Depends(get_current_user_org),
):
    # No return annotation: FastAPI reads `-> None` as a declared response
    # model and refuses it against 204, which must not carry a body.
    _user, client, org_id = _parts(auth)
    svc.remover_ativo(client, org_id, ativo_id)


def _dump(body) -> dict:
    """`exclude_unset` dict, with nested interests flattened to plain dicts.

    `exclude_unset` is what makes a PATCH a PATCH: an omitted field is left
    alone, an explicit null clears it. The nested models need the same
    treatment or the service receives `InteresseBody` instances and its
    `k in item` membership tests silently match nothing.
    """
    dados = body.model_dump(exclude_unset=True)
    if dados.get("interesses") is not None:
        dados["interesses"] = [
            i if isinstance(i, dict) else i.model_dump(exclude_unset=True)
            for i in dados["interesses"]
        ]
    # UUIDs go back out over PostgREST as JSON.
    if dados.get("corretor_id") is not None:
        dados["corretor_id"] = str(dados["corretor_id"])
    return dados


__all__ = ["router"]

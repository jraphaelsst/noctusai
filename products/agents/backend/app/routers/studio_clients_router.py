"""``/api/studio/agents/{key}/clients`` — the client brain (contract §D2).

A client is agent-scoped durable context (brand, audience, positioning,
locks, decisions…) that the compiler appends as ``# Cliente em foco`` when a
conversation is bound to it. Clients are NOT versioned: they evolve on their
own clock, and every turn recompiles (§D6 "compiled_hash is recomputed per
turn").

Same auth/scoping rules as ``studio_agents_router`` (whose resolution helpers
this module reuses): member reads, admin writes, agent resolved by
``(ctx.org_id, key)``, a client/entry of another agent or org → 404.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import require_admin, require_member
from app.routers.studio_agents_router import (
    get_studio_definition_store_dep,
    http_error,
    patch_fields,
    resolve_agent,
    resolve_client,
    store_errors,
)
from app.schemas.studio import (
    ClientCreateRequest,
    ClientEntryCreateRequest,
    ClientEntryOut,
    ClientEntryUpdateRequest,
    ClientListOut,
    ClientOut,
    ClientSummaryOut,
    ClientUpdateRequest,
)
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents/{key}/clients", tags=["studio"])


def _entry_out(e) -> ClientEntryOut:
    return ClientEntryOut(
        id=e.id, tipo=e.tipo, titulo=e.titulo, conteudo=e.conteudo, status=e.status, created_at=e.created_at,
    )


def _client_out(store, org_id: UUID, client) -> ClientOut:
    return ClientOut(
        id=client.id, slug=client.slug, nome=client.nome, resumo=client.resumo, ativo=client.ativo,
        entradas=[_entry_out(e) for e in store.list_client_entries(org_id, client.id)],
    )


def _resolve_entry(store, org_id: UUID, client_id: UUID, entry_id: UUID):
    try:
        entry = store.get_client_entry(org_id, entry_id)
    except NotFound as exc:
        raise http_error(404, "entry_not_found", "Entrada não encontrada.") from exc
    if entry.client_id != client_id:
        raise http_error(404, "entry_not_found", "Entrada não encontrada.")
    return entry


@router.get("", response_model=ClientListOut)
async def list_clients(
    key: str,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_definition_store_dep),
) -> ClientListOut:
    agent = resolve_agent(store, ctx.org_id, key)
    return ClientListOut(items=[
        ClientSummaryOut(
            id=c.id, slug=c.slug, nome=c.nome, resumo=c.resumo, ativo=c.ativo,
            total_entradas=c.total_entradas or 0,
        )
        for c in store.list_clients(ctx.org_id, agent.id)
    ])


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    key: str,
    payload: ClientCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> ClientOut:
    agent = resolve_agent(store, ctx.org_id, key)
    with store_errors():
        client = store.create_client(
            ctx.org_id, agent.id, slug=payload.slug, nome=payload.nome, resumo=payload.resumo, ativo=payload.ativo,
        )
    return _client_out(store, ctx.org_id, client)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    key: str,
    client_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_definition_store_dep),
) -> ClientOut:
    agent = resolve_agent(store, ctx.org_id, key)
    return _client_out(store, ctx.org_id, resolve_client(store, ctx.org_id, agent, client_id))


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    key: str,
    client_id: UUID,
    payload: ClientUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> ClientOut:
    agent = resolve_agent(store, ctx.org_id, key)
    resolve_client(store, ctx.org_id, agent, client_id)
    fields = patch_fields(payload)
    with store_errors():
        client = store.update_client(ctx.org_id, client_id, fields)
    return _client_out(store, ctx.org_id, client)


@router.post("/{client_id}/entries", response_model=ClientEntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    key: str,
    client_id: UUID,
    payload: ClientEntryCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> ClientEntryOut:
    agent = resolve_agent(store, ctx.org_id, key)
    resolve_client(store, ctx.org_id, agent, client_id)
    with store_errors():
        entry = store.create_client_entry(
            ctx.org_id, client_id, tipo=payload.tipo, titulo=payload.titulo,
            conteudo=payload.conteudo, status=payload.status,
        )
    return _entry_out(entry)


@router.patch("/{client_id}/entries/{entry_id}", response_model=ClientEntryOut)
async def update_entry(
    key: str,
    client_id: UUID,
    entry_id: UUID,
    payload: ClientEntryUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> ClientEntryOut:
    agent = resolve_agent(store, ctx.org_id, key)
    resolve_client(store, ctx.org_id, agent, client_id)
    _resolve_entry(store, ctx.org_id, client_id, entry_id)
    fields = patch_fields(payload)
    with store_errors():
        entry = store.update_client_entry(ctx.org_id, entry_id, fields)
    return _entry_out(entry)


@router.delete("/{client_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    key: str,
    client_id: UUID,
    entry_id: UUID,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> Response:
    agent = resolve_agent(store, ctx.org_id, key)
    resolve_client(store, ctx.org_id, agent, client_id)
    _resolve_entry(store, ctx.org_id, client_id, entry_id)
    with store_errors():
        store.delete_client_entry(ctx.org_id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]

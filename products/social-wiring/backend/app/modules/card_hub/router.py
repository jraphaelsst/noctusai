"""`/api/clientes/...` — the card's data surface (lead-card-hub Phase 2).

Contract: `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md` §3.
Envelope conventions (house, contract §3): list responses are
`{"items": [...], "total": n}`; errors go through `AppException` ->
`{"error": {"code", "message"}}`, never `{"detail": ...}`. All routes are
org-scoped (`Depends(get_current_user_org)`) and auth-required.

🔴 ROUTE-ORDERING HAZARD, cross-router (mirrors
`app/routers/clientes_router.py`'s own `/revisao`-before-`/{cliente_id}`
note, generalised across routers): `GET/POST /api/clientes/tags` is a
literal 1-segment path structurally identical to `clientes_router.py`'s
bare `/{cliente_id}` — FastAPI/Starlette match routes by PATH SHAPE
first (plain-string param converters, no automatic UUID regex), so
whichever router mounts FIRST in `app/main.py`'s `MODULES` assembly
order wins that shape for EVERY request matching it. `app/main.py`
places `_card_hub` BEFORE `_register_media_wiring` for exactly this
reason — see that file's comment. Every other path in this router is
disambiguated by segment COUNT or a distinct 2nd-segment literal
(`/{id}/timeline`, `/{id}/notas`, `/documentos/tipos`, ...), so no other
ordering constraint applies within this file.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.dependencies import coerce_org_uuid, get_current_user_org

from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub import timeline_service
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend
from app.modules.card_hub.schemas import (
    ChecklistCreateBody,
    ChecklistItemCreateBody,
    ChecklistItemUpdateBody,
    ChecklistUpdateBody,
    ClienteTagsSetBody,
    DatasPatchBody,
    MembrosSetBody,
    NotaCreateBody,
    NotaUpdateBody,
    TagCreateBody,
    TagUpdateBody,
)

router = APIRouter(prefix="/api/clientes", tags=["card_hub"])


def _auth_parts(auth):
    user, _token, raw_org = auth
    return user, coerce_org_uuid(raw_org)


# ─── Tags (org catalogue — literal path, see module docstring) ─────────


@router.get("/tags")
async def list_tags_route(
    auth=Depends(get_current_user_org), client=Depends(get_card_hub_client)
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.list_tags(client, org_id)


@router.post("/tags", status_code=201)
async def create_tag_route(
    body: TagCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.create_tag(client, org_id, nome=body.nome, cor=body.cor)


@router.patch("/tags/{tag_id}")
async def update_tag_route(
    tag_id: UUID,
    body: TagUpdateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.update_tag(client, org_id, tag_id, nome=body.nome, cor=body.cor)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag_route(
    tag_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.delete_tag(client, org_id, tag_id)


# ─── Documentos tipos catalogue (literal path) ─────────────────────────


@router.get("/documentos/tipos")
async def list_tipos_documento_route(
    auth=Depends(get_current_user_org), client=Depends(get_card_hub_client)
) -> dict:
    _auth_parts(auth)
    return docs_svc.list_tipos_documento(client)


# ─── Timeline ───────────────────────────────────────────────────────────


@router.get("/{cliente_id}/timeline")
async def get_timeline_route(
    cliente_id: UUID,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    kinds: Optional[str] = Query(None),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    kind_set = {k.strip() for k in kinds.split(",") if k.strip()} if kinds else None
    return timeline_service.get_timeline(
        client, org_id, cliente_id, kinds=kind_set, cursor=cursor, limit=limit
    )


# ─── Notas ──────────────────────────────────────────────────────────────


@router.post("/{cliente_id}/notas", status_code=201)
async def create_nota_route(
    cliente_id: UUID,
    body: NotaCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.create_nota(
        client, org_id, cliente_id, corpo=body.corpo, tipo=body.tipo, autor_id=getattr(user, "id", None)
    )


@router.patch("/{cliente_id}/notas/{nota_id}")
async def update_nota_route(
    cliente_id: UUID,
    nota_id: UUID,
    body: NotaUpdateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.update_nota(client, org_id, cliente_id, nota_id, corpo=body.corpo)


@router.delete("/{cliente_id}/notas/{nota_id}", status_code=204)
async def delete_nota_route(
    cliente_id: UUID,
    nota_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.delete_nota(client, org_id, cliente_id, nota_id)


# ─── Cliente <-> tags ───────────────────────────────────────────────────


@router.put("/{cliente_id}/tags")
async def set_cliente_tags_route(
    cliente_id: UUID,
    body: ClienteTagsSetBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.set_cliente_tags(
        client, org_id, cliente_id, tag_ids=body.tag_ids, criado_por=getattr(user, "id", None)
    )


# ─── Membros ────────────────────────────────────────────────────────────


@router.get("/{cliente_id}/membros")
async def get_membros_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.get_membros(client, org_id, cliente_id)


@router.put("/{cliente_id}/membros")
async def set_membros_route(
    cliente_id: UUID,
    body: MembrosSetBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.set_membros(client, org_id, cliente_id, lead_corretor_ids=body.lead_corretor_ids)


# ─── Datas + lembretes ──────────────────────────────────────────────────


@router.patch("/{cliente_id}/datas")
async def patch_datas_route(
    cliente_id: UUID,
    body: DatasPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    updates = body.model_dump(exclude_unset=True)
    return svc.patch_datas(
        client,
        org_id,
        cliente_id,
        data_inicio=updates.get("data_inicio", ...),
        data_entrega=updates.get("data_entrega", ...),
        entrega_concluida=updates.get("entrega_concluida", ...),
        lembrete_minutos_antes=updates.get("lembrete_minutos_antes", ...),
        recorrencia=updates.get("recorrencia", ...),
    )


# ─── Checklists ─────────────────────────────────────────────────────────


@router.get("/{cliente_id}/checklists")
async def list_checklists_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.list_checklists(client, org_id, cliente_id)


@router.post("/{cliente_id}/checklists", status_code=201)
async def create_checklist_route(
    cliente_id: UUID,
    body: ChecklistCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.create_checklist(client, org_id, cliente_id, titulo=body.titulo)


@router.patch("/{cliente_id}/checklists/{checklist_id}")
async def update_checklist_route(
    cliente_id: UUID,
    checklist_id: UUID,
    body: ChecklistUpdateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.update_checklist(client, org_id, cliente_id, checklist_id, titulo=body.titulo, posicao=body.posicao)


@router.delete("/{cliente_id}/checklists/{checklist_id}", status_code=204)
async def delete_checklist_route(
    cliente_id: UUID,
    checklist_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.delete_checklist(client, org_id, cliente_id, checklist_id)


@router.post("/{cliente_id}/checklists/{checklist_id}/itens", status_code=201)
async def create_checklist_item_route(
    cliente_id: UUID,
    checklist_id: UUID,
    body: ChecklistItemCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.create_checklist_item(client, org_id, cliente_id, checklist_id, texto=body.texto)


@router.patch("/{cliente_id}/checklists/{checklist_id}/itens/{item_id}")
async def update_checklist_item_route(
    cliente_id: UUID,
    checklist_id: UUID,
    item_id: UUID,
    body: ChecklistItemUpdateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.update_checklist_item(
        client,
        org_id,
        cliente_id,
        checklist_id,
        item_id,
        texto=body.texto,
        concluido=body.concluido,
        posicao=body.posicao,
        concluido_por=getattr(user, "id", None),
    )


@router.delete("/{cliente_id}/checklists/{checklist_id}/itens/{item_id}", status_code=204)
async def delete_checklist_item_route(
    cliente_id: UUID,
    checklist_id: UUID,
    item_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.delete_checklist_item(client, org_id, cliente_id, checklist_id, item_id)


# ─── Documentos (LGPD) ──────────────────────────────────────────────────


@router.get("/{cliente_id}/documentos")
async def list_documentos_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return docs_svc.list_documentos(client, org_id, cliente_id)


@router.post("/{cliente_id}/documentos", status_code=201)
async def upload_documento_route(
    cliente_id: UUID,
    file: UploadFile = File(...),
    tipo_documento: str = Form(...),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    data = await file.read()
    return await docs_svc.upload_documento(
        client,
        storage,
        org_id,
        cliente_id,
        filename=file.filename or "arquivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=getattr(user, "id", None),
    )


@router.get("/{cliente_id}/documentos/{documento_id}/url")
async def get_documento_url_route(
    cliente_id: UUID,
    documento_id: UUID,
    intent: str = Query("view", pattern="^(view|download)$"),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    return await docs_svc.get_documento_url(
        client, storage, org_id, cliente_id, documento_id, usuario_id=getattr(user, "id", None), intent=intent
    )


@router.delete("/{cliente_id}/documentos/{documento_id}", status_code=204)
async def delete_documento_route(
    cliente_id: UUID,
    documento_id: UUID,
    # Contract correction: the seed `ApiClient.delete()` has no body
    # parameter, and a DELETE-with-body is poorly supported across the
    # stack generally. `motivo` is a REQUIRED query param instead — an
    # LGPD delete without a recorded reason is not an LGPD delete.
    motivo: str = Query(..., min_length=1),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
):
    user, org_id = _auth_parts(auth)
    await docs_svc.delete_documento(
        client, storage, org_id, cliente_id, documento_id, motivo=motivo, usuario_id=getattr(user, "id", None)
    )


@router.get("/{cliente_id}/documentos/{documento_id}/acessos")
async def list_acessos_route(
    cliente_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return docs_svc.list_acessos(client, org_id, cliente_id, documento_id)


# ─── Card summary ───────────────────────────────────────────────────────


@router.get("/{cliente_id}/card")
async def get_card_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return timeline_service.get_card_resumo(client, org_id, cliente_id)


__all__ = ["router"]

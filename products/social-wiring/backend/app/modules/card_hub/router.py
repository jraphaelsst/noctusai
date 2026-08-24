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

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from app.dependencies import coerce_org_uuid, get_current_user_org

from app.modules.card_hub import agendamentos_service as agenda_svc
from app.modules.card_hub import documento_checklist_service as doc_checklist_svc
from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub import timeline_service
from app.modules.card_hub.deps import (
    get_card_hub_client,
    get_identity_extractor_factory,
    get_storage_backend,
)
from app.modules.card_hub.schemas import (
    AgendamentoCreateBody,
    AgendamentoPatchBody,
    ChecklistCreateBody,
    ChecklistItemCreateBody,
    ChecklistItemUpdateBody,
    ChecklistUpdateBody,
    ClienteTagsSetBody,
    DocumentoChecklistPatchBody,
    ExtracaoSugestaoBody,
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


# ─── Documento checklist (migration 067) ────────────────────────────────
#
# The item LIST is canonical and lives in `documento_checklist_service.ITENS`;
# only the ticks are per-client. So there is no create/delete here — you cannot
# add an item to a checklist that is the same for everyone by definition. Two
# routes is the whole surface: read the six, toggle one.


@router.get("/{cliente_id}/documento-checklist")
async def list_documento_checklist_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return doc_checklist_svc.listar(client, org_id, cliente_id)


@router.patch("/{cliente_id}/documento-checklist/{item_key}")
async def patch_documento_checklist_route(
    cliente_id: UUID,
    item_key: str,
    body: DocumentoChecklistPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    try:
        return doc_checklist_svc.marcar(
            client,
            org_id,
            cliente_id,
            item_key,
            concluido=body.concluido,
            user_id=getattr(user, "id", None),
        )
    except KeyError:
        # An unknown key is a client bug, not a missing resource: the six are
        # a closed set the caller can read from the GET above.
        raise HTTPException(
            status_code=422,
            detail=(
                f"item_key must be one of {list(doc_checklist_svc.ITEM_KEYS)}, "
                f"got {item_key!r}"
            ),
        )


# ─── Agendamentos (migration 061 — many per atendimento) ────────────────
#
# Mounted under `/api/clientes/{cliente_id}` even though an agendamento belongs
# to an ATENDIMENTO, because the card is the person and reads across all of
# their atendimentos. Every route proves the row belongs to this cliente before
# touching it — an id alone must never be enough to edit someone else's.


@router.get("/{cliente_id}/agendamentos")
async def list_agendamentos_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return agenda_svc.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/agendamentos", status_code=201)
async def create_agendamento_route(
    cliente_id: UUID,
    body: AgendamentoCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    # `AmbiguousAtendimento` is an AppException and carries its own 409 +
    # structured details, so there is nothing to translate here.
    return agenda_svc.criar(
        client,
        org_id,
        cliente_id,
        quando=body.quando,
        tipo=body.tipo,
        nota=body.nota,
        lembrete_minutos_antes=body.lembrete_minutos_antes,
        atendimento_id=body.atendimento_id,
    )


@router.patch("/{cliente_id}/agendamentos/{agendamento_id}")
async def patch_agendamento_route(
    cliente_id: UUID,
    agendamento_id: UUID,
    body: AgendamentoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    updates = body.model_dump(exclude_unset=True)
    return agenda_svc.atualizar(
        client,
        org_id,
        cliente_id,
        agendamento_id,
        quando=updates.get("quando", ...),
        tipo=updates.get("tipo", ...),
        nota=updates.get("nota", ...),
        lembrete_minutos_antes=updates.get("lembrete_minutos_antes", ...),
    )


@router.delete("/{cliente_id}/agendamentos/{agendamento_id}", status_code=204)
async def delete_agendamento_route(
    cliente_id: UUID,
    agendamento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    # No `-> None` annotation: FastAPI turns a return annotation into a
    # response model, and a 204 must not declare a body. Same shape as every
    # other 204 in this router.
    _user, org_id = _auth_parts(auth)
    agenda_svc.remover(client, org_id, cliente_id, agendamento_id)


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
    background: BackgroundTasks,
    file: UploadFile = File(...),
    tipo_documento: str = Form(...),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_identity_extractor_factory),
) -> dict:
    user, org_id = _auth_parts(auth)
    data = await file.read()
    documento = await docs_svc.upload_documento(
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

    # An identity document gets its birthdate read AFTER the response. The
    # ladder's vision rung takes seconds to tens of seconds, so doing it inline
    # would make a successful upload feel broken and would couple it to an LLM
    # provider being reachable. The upload is already committed and stamped
    # `extracao_status='pendente'`; the job only ever moves that forward.
    if identidade_svc.deve_extrair(tipo_documento):
        background.add_task(
            identidade_svc.extrair_identidade,
            client,
            storage,
            org_id,
            cliente_id,
            UUID(documento["id"]),
            extractor=extractor_factory(str(org_id)),
        )
    return documento


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


# ─── Extraction suggestions (migration 069) ─────────────────────────────
#
# A low-confidence read is a QUESTION, not a fact, so both answers are explicit
# routes. There is deliberately no "apply all suggestions" convenience: the
# whole reason these values are not already on the record is that a person has
# to look at each one.


@router.post("/{cliente_id}/documentos/{documento_id}/extracao/confirmar")
async def confirmar_extracao_route(
    cliente_id: UUID,
    documento_id: UUID,
    body: Optional[ExtracaoSugestaoBody] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Accept a machine-read value onto the client record.

    422 when a first-writer-wins field is already filled — two operators on
    the same card otherwise race and the loser silently overwrites the winner.
    A document-owned field (`nome_oficial`) has no such conflict: the newer
    reading is meant to win, and the one it replaces is still on its own
    document row.
    """
    user, org_id = _auth_parts(auth)
    return identidade_svc.confirmar_sugestao(
        client, org_id, cliente_id, documento_id,
        item_key=body.item_key if body else None,
        user_id=getattr(user, "id", None),
    )


@router.post("/{cliente_id}/documentos/{documento_id}/extracao/descartar")
async def descartar_extracao_route(
    cliente_id: UUID,
    documento_id: UUID,
    body: Optional[ExtracaoSugestaoBody] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Turn a suggestion down so the card stops offering it.

    The extracted value is kept — this records a judgement about the read, it
    does not erase what was read.

    Discarding is per DOCUMENT: it stops every field this document suggested,
    not just the one named. See `descartar_sugestao` for why that is the
    correct scope rather than an oversight.
    """
    user, org_id = _auth_parts(auth)
    return identidade_svc.descartar_sugestao(
        client, org_id, cliente_id, documento_id,
        item_key=body.item_key if body else None,
        user_id=getattr(user, "id", None),
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

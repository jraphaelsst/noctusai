"""``/api/studio/agents/{key}/knowledge`` + ``.../documents`` (contract
§D3, slice BE-KE).

Auth: ``require_member`` for reads, ``require_admin`` for writes (the
SAME deps every other studio router uses). The agent is resolved through
BE-DEF's ``StudioDefinitionStore`` and its ``resolve_agent`` — ONE resolver
for every studio route: 404 ``agent_not_found`` for an unknown key, 409
``not_studio_agent`` for a legacy agent. A foreign ``col_id``/``doc_id``
404s, never 403-leaks (contract §H.1). Typed store errors map through the
shared ``store_errors`` (409 ``slug_taken`` / 422 ``invalid_field``).

Caps (wave-1 security review): the list filter ``q`` ≤ 200 chars (L4 — and
it travels as a bound SQL parameter, never a PostgREST filter string);
search ``q`` ≤ 512 (L5).

``POST .../documents/batch`` (UI-KB-BACKEND): bulk ingest for the Studio UI
(a 382-document corpus can't go through one-document-per-call) — up to
``DOCUMENTS_BATCH_MAX`` items, reusing the importer's
``upsert_document_by_source_sha`` (idempotent re-upload, no revision spam)
so its semantics are IDENTICAL for a UI batch upload and a bundle import.
PER-ITEM results: one bad document never loses the other 99 — every
store error (``ValueError`` invalid slug/tipo/size, ``StudioConflict``
``slug_in_other_collection``) is caught per item, never propagated as a
500/409 for the whole call. ``app.main`` raises this route's body-size cap
(``DOCUMENTS_BATCH_BODY_LIMIT_PATTERN``) the same way it does for
``.../import`` — the 1 MB webhook-DoS default would 413 a realistic batch.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_admin, require_member
from app.routers.studio_agents_router import (
    get_studio_definition_store_dep,
    resolve_agent,
    store_errors,
)
from app.schemas.studio_ke import (
    CollectionCreateRequest,
    CollectionListOut,
    CollectionOut,
    CollectionUpdateRequest,
    DocumentBatchCreateRequest,
    DocumentBatchItemResultOut,
    DocumentBatchResultOut,
    DocumentCreateRequest,
    DocumentListItemOut,
    DocumentListOut,
    DocumentOut,
    DocumentUpdateRequest,
    RevisionListOut,
    RevisionOut,
    SearchItemOut,
    SearchOut,
)
from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord
from app.stores.studio_knowledge import (
    CollectionInput,
    DocumentInput,
    _UNSET,
)
from app.studio.models import LIST_QUERY_MAX, SEARCH_QUERY_MAX
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-knowledge"])

#: The body-cap pattern ``app.main`` registers (whole-segment wildcard,
#: same shape as ``studio_import_router.IMPORT_BODY_LIMIT_PATTERN``).
DOCUMENTS_BATCH_BODY_LIMIT_PATTERN = "/api/studio/agents/*/knowledge/*/documents/batch"
#: 100 items × `document.conteudo` (2 MB) is a pathological upper bound
#: nobody hits in practice (a real knowledge corpus runs KB-hundred KB per
#: doc); 20 MB gives generous headroom over realistic batches while staying
#: well under the pathological max — narrower than the 25 MB bundle import
#: cap since this is one collection's slice, not a whole agent.
DOCUMENTS_BATCH_MAX_BYTES = 20 * 1024 * 1024


# ── DI seams ─────────────────────────────────────────────────────────────


def get_studio_knowledge_store_dep():
    from app.config import settings
    from app.stores.studio_knowledge import get_studio_knowledge_store

    return get_studio_knowledge_store(settings)


def resolve_studio_agent(defs, org_id: UUID, key: str) -> StudioAgentRecord:
    """BE-DEF's resolver (studio-only) — shared with ``studio_evals_router``."""
    return resolve_agent(defs, org_id, key)


def _not_found(detail: str = "Recurso não encontrado.", code: str = "not_found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"detail": detail, "code": code})


def _collection_out(record, total_documentos: int) -> CollectionOut:
    return CollectionOut(
        id=record.id, slug=record.slug, nome=record.nome, tag=record.tag,
        descricao=record.descricao, ordem=record.ordem, total_documentos=total_documentos,
    )


def _document_list_item_out(record) -> DocumentListItemOut:
    return DocumentListItemOut(
        id=record.id, slug=record.slug, titulo=record.titulo, tipo=record.tipo,
        resumo=record.resumo, chars=len(record.conteudo), ativo=record.ativo,
        updated_at=record.updated_at,
    )


def _document_out(record) -> DocumentOut:
    return DocumentOut(
        id=record.id, collection_id=record.collection_id, slug=record.slug, titulo=record.titulo,
        tipo=record.tipo, resumo=record.resumo, conteudo=record.conteudo,
        proveniencia=record.proveniencia, ativo=record.ativo, chars=len(record.conteudo),
        updated_at=record.updated_at,
    )


# ── Collections ────────────────────────────────────────────────────────


@router.get("/{key}/knowledge", response_model=CollectionListOut)
async def list_collections(
    key: str,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> CollectionListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    records = store.list_collections(ctx.org_id, agent.id)
    colecoes = [
        _collection_out(r, store.count_documents(ctx.org_id, agent.id, r.id))
        for r in records
    ]
    return CollectionListOut(colecoes=colecoes)


@router.post("/{key}/knowledge", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    key: str,
    payload: CollectionCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> CollectionOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    with store_errors():
        record = store.create_collection(
            ctx.org_id, agent.id,
            CollectionInput(slug=payload.slug, nome=payload.nome, tag=payload.tag,
                             descricao=payload.descricao, ordem=payload.ordem),
        )
    return _collection_out(record, 0)


@router.patch("/{key}/knowledge/{col_id}", response_model=CollectionOut)
async def update_collection(
    key: str,
    col_id: UUID,
    payload: CollectionUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> CollectionOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    fields = payload.model_dump(exclude_unset=True)
    try:
        with store_errors():
            record = store.update_collection(
                ctx.org_id, agent.id, col_id,
                nome=fields.get("nome", _UNSET), tag=fields.get("tag", _UNSET),
                descricao=fields.get("descricao", _UNSET), ordem=fields.get("ordem", _UNSET),
            )
    except NotFound as exc:
        raise _not_found("Coleção não encontrada.", "collection_not_found") from exc
    total = store.count_documents(ctx.org_id, agent.id, col_id)
    return _collection_out(record, total)


# ── Documents ──────────────────────────────────────────────────────────


@router.get("/{key}/knowledge/{col_id}/documents", response_model=DocumentListOut)
async def list_documents(
    key: str,
    col_id: UUID,
    q: str | None = Query(None, max_length=LIST_QUERY_MAX),
    tipo: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> DocumentListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        store.get_collection(ctx.org_id, agent.id, col_id)
    except NotFound as exc:
        raise _not_found("Coleção não encontrada.", "collection_not_found") from exc
    with store_errors():
        records, total = store.list_documents(
            ctx.org_id, agent.id, col_id, q=q, tipo=tipo, page=page, page_size=page_size,
        )
    return DocumentListOut(items=[_document_list_item_out(r) for r in records], total=total)


@router.post(
    "/{key}/knowledge/{col_id}/documents", response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    key: str,
    col_id: UUID,
    payload: DocumentCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> DocumentOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        store.get_collection(ctx.org_id, agent.id, col_id)
    except NotFound as exc:
        raise _not_found("Coleção não encontrada.", "collection_not_found") from exc
    with store_errors():
        record = store.create_document(
            ctx.org_id, agent.id, col_id,
            DocumentInput(
                slug=payload.slug, titulo=payload.titulo, tipo=payload.tipo,
                conteudo=payload.conteudo, resumo=payload.resumo, proveniencia=payload.proveniencia,
            ),
            author_id=ctx.user_id,
        )
    return _document_out(record)


_BATCH_STATUS_PT = {"created": "criado", "updated": "atualizado", "unchanged": "inalterado"}


@router.post(
    "/{key}/knowledge/{col_id}/documents/batch", response_model=DocumentBatchResultOut,
)
async def create_documents_batch(
    key: str,
    col_id: UUID,
    payload: DocumentBatchCreateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> DocumentBatchResultOut:
    """Bulk ingest into ONE collection (contract §D3 batch, UI-KB-BACKEND).

    Reuses ``upsert_document_by_source_sha`` — the SAME idempotent-upsert
    semantics the §F importer uses (change-detected on content hash, no
    revision written when unchanged). Every item's validation/conflict
    error is caught individually so one bad document never sinks the call.
    """
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        store.get_collection(ctx.org_id, agent.id, col_id)
    except NotFound as exc:
        raise _not_found("Coleção não encontrada.", "collection_not_found") from exc

    resultados: list[DocumentBatchItemResultOut] = []
    counts = {"criado": 0, "atualizado": 0, "inalterado": 0, "erro": 0}
    for item in payload.documentos:
        try:
            record, op = store.upsert_document_by_source_sha(
                ctx.org_id, agent.id, col_id,
                slug=item.slug, titulo=item.titulo, tipo=item.tipo,
                resumo=item.resumo, proveniencia=item.proveniencia, conteudo=item.conteudo,
                author_id=ctx.user_id,
            )
        except (ValueError, StudioConflict) as exc:
            counts["erro"] += 1
            resultados.append(DocumentBatchItemResultOut(slug=item.slug, status="erro", erro=str(exc)))
            continue
        status_pt = _BATCH_STATUS_PT[op]
        counts[status_pt] += 1
        resultados.append(DocumentBatchItemResultOut(slug=item.slug, status=status_pt, doc_id=record.id))
    return DocumentBatchResultOut(
        resultados=resultados, criados=counts["criado"], atualizados=counts["atualizado"],
        inalterados=counts["inalterado"], erros=counts["erro"],
    )


@router.get("/{key}/documents/{doc_id}", response_model=DocumentOut)
async def get_document(
    key: str,
    doc_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> DocumentOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        record = store.get_document(ctx.org_id, agent.id, doc_id)
    except NotFound as exc:
        raise _not_found("Documento não encontrado.", "document_not_found") from exc
    return _document_out(record)


@router.patch("/{key}/documents/{doc_id}", response_model=DocumentOut)
async def update_document(
    key: str,
    doc_id: UUID,
    payload: DocumentUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> DocumentOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    fields = payload.model_dump(exclude_unset=True)
    motivo = fields.pop("motivo", None)
    try:
        with store_errors():
            record = store.update_document(
                ctx.org_id, agent.id, doc_id, author_id=ctx.user_id, motivo=motivo,
                titulo=fields.get("titulo", _UNSET), tipo=fields.get("tipo", _UNSET),
                resumo=fields.get("resumo", _UNSET), conteudo=fields.get("conteudo", _UNSET),
                proveniencia=fields.get("proveniencia", _UNSET), ativo=fields.get("ativo", _UNSET),
            )
    except NotFound as exc:
        raise _not_found("Documento não encontrado.", "document_not_found") from exc
    return _document_out(record)


@router.get("/{key}/documents/{doc_id}/revisions", response_model=RevisionListOut)
async def list_revisions(
    key: str,
    doc_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> RevisionListOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    try:
        records = store.list_revisions(ctx.org_id, agent.id, doc_id)
    except NotFound as exc:
        raise _not_found("Documento não encontrado.", "document_not_found") from exc
    return RevisionListOut(items=[
        RevisionOut(id=r.id, op=r.op, motivo=r.motivo, author_id=r.author_id, created_at=r.created_at)
        for r in records
    ])


# ── Search — the SAME function `kb_buscar` calls (contract §D3) ─────────


@router.get("/{key}/knowledge/search", response_model=SearchOut)
async def search_knowledge(
    key: str,
    q: str = Query(..., min_length=1, max_length=SEARCH_QUERY_MAX),
    colecao: str | None = Query(None),
    limite: int = Query(8, ge=1, le=20),
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_knowledge_store_dep),
    defs=Depends(get_studio_definition_store_dep),
) -> SearchOut:
    agent = resolve_studio_agent(defs, ctx.org_id, key)
    with store_errors():
        results = store.search(ctx.org_id, agent.id, q, colecao=colecao, limite=limite)
    return SearchOut(items=[
        SearchItemOut(
            doc_id=r.doc_id, slug=r.slug, titulo=r.titulo, colecao=r.colecao,
            tag=r.tag, tipo=r.tipo, trecho=r.trecho, rank=r.rank,
        )
        for r in results
    ])


# Public alias — `studio_evals_router.py` shares the 404 helper.
not_found_error = _not_found


__all__ = ["router", "resolve_studio_agent", "not_found_error", "get_studio_knowledge_store_dep"]

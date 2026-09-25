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

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)

from noctusai_lib.api.auth.session import is_org_admin, require_org_admin_role
from noctusai_lib.domain.card_hub import CardHubContext, card_hub_routers

from app.dependencies import get_core_client, get_current_user_org

from app.modules.card_hub import agendamentos_service as agenda_svc
from app.modules.card_hub import certidoes_matriz_service as certidoes_matriz_svc
from app.modules.card_hub import certidoes_matriz_linhas_service as certidoes_matriz_linhas_svc
from app.modules.card_hub import compradores_service as compradores_svc
from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import documento_checklist_service as doc_checklist_svc
from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub import empresas_service as empresas_svc
from app.modules.card_hub import financiamento_service as financiamento_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub import negociacao_estruturada_service as neg_estruturada_svc
from app.modules.card_hub import negociacao_extracao_service as negociacao_extracao_svc
from app.modules.card_hub import negociacao_service as negociacao_svc
from app.modules.card_hub.assinatura_router import router as assinatura_router
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.contrato_gerador.router import (
    router as contrato_gerador_router,
)
from app.modules.card_hub.contrato_testemunhas_router import (
    router as contrato_testemunhas_router,
)
from app.modules.card_hub.negociacao_estruturada_router import (
    router as negociacao_estruturada_router,
)
from app.modules.card_hub.proveniencia.router import router as proveniencia_router
from app.modules.card_hub import roteiro_pdf_service as roteiro_pdf_svc
from app.modules.card_hub import roteiros_service as roteiros_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub.config import CARD_HUB
from app.modules.card_hub.deps import (
    get_card_hub_client,
    get_conflict_notification_service,
    get_identity_extractor_factory,
    get_storage_backend,
)
from app.modules.empresas.deps import (
    BUCKET as _EMPRESAS_BUCKET,
    get_storage_backend as get_empresas_storage_backend,
)
from app.modules.card_hub.schemas import (
    CompradorCreateBody,
    ContratoPatchBody,
    EmpresaManualCreateBody,
    FinanciamentoPatchBody,
    LinhaMatrizCreateBody,
    LinhaMatrizPatchBody,
    NegociacaoDefaultsPatchBody,
    NegociacaoPatchBody,
    AgendamentoCreateBody,
    AgendamentoPatchBody,
    DecidirConflitoBody,
    DocumentoChecklistPatchBody,
    ExtracaoSugestaoBody,
    PartePapelPatchBody,
    ProcessoLegadoBody,
    ResolverConflitoNegociacaoBody,
    RoteiroCreateBody,
    RoteiroOrdemBody,
    RoteiroPatchBody,
    VisitaCreateBody,
    VisitaPatchBody,
    VisitaPropostaBody,
)

router = APIRouter(prefix="/api/clientes", tags=["card_hub"])
logger = logging.getLogger(__name__)

# 🔴 THE ONE INCLUDE LINE — migration 108's parcelas/favorecidos/
# intermediários routes. See `negociacao_estruturada_router.py`'s own
# docstring for why they live in a separate file rather than growing this
# already-1300-line one, and why this is additive (no other line in this
# file changes for it).
router.include_router(negociacao_estruturada_router)
# F5 — contract generation (GET .../contratos/{id}/geracao, POST .../gerar).
router.include_router(contrato_gerador_router)
# Contract signing (migration 134) — .../contratos/{id}/assinatura[/cancelar].
# The webhook (§3.4) is NOT here — see `assinatura_router.py`'s own docstring.
router.include_router(assinatura_router)
# Per-contract witness selection (migration 168) — .../contratos/{id}/testemunhas.
router.include_router(contrato_testemunhas_router)

#: Shared with the included routers — see `card_hub/auth.py`.
_auth_parts = auth_parts


# ─── The seed card hub (`noctusai_lib.domain.card_hub`) ─────────────────
#
# The card's generic routes (tags, tipos, timeline, notas, cliente<->tags,
# membros, checklist extras, checklists, documentos, acessos, card) are the
# seed router factory's, bound to `CARD_HUB`. They arrive as two routers
# (collection = literal paths, entity = `/{cliente_id}/...`), but this
# product's own routes sit BETWEEN them — so rather than mounting the two
# wholesale (which would reorder the `/api/clientes*` route table), each
# factory route is `_splice`d into `router` at the exact position its
# hand-written predecessor held. Route order, names, operation ids, paths,
# methods and status codes are therefore unchanged.
#
# 🔴 NOT spliced: the factory's `upload_documento_route`. This product's
# upload does two things the factory's cannot: it enforces
# `documentos_service.MAX_UPLOAD_BYTES` read at CALL time (the shim passes it
# as `max_bytes=`), and it queues the identity extraction with the
# per-request, DI-overridable extractor factory. It stays below, local.
# Every other factory route MUST be spliced — `_assert_all_spliced()` at the
# bottom of this file refuses an import that dropped one.


def _card_hub_context(auth: tuple, db: Any) -> CardHubContext:
    user, org_id = _auth_parts(auth)
    return CardHubContext(db=db, org_id=org_id, user_id=getattr(user, "id", None))


_collection_router, _entity_router = card_hub_routers(
    CARD_HUB,
    auth_dependency=get_current_user_org,
    resolve_context=_card_hub_context,
    get_db=get_card_hub_client,
    get_storage=get_storage_backend,
    prefix="/api/clientes",
    tags=["card_hub"],
)
_LOCAL_OVERRIDES = frozenset({"upload_documento_route"})
_factory_routes = {
    route.name: route
    for route in (*_collection_router.routes, *_entity_router.routes)
    if route.name not in _LOCAL_OVERRIDES
}


def _splice(*names: str) -> None:
    """Append these factory routes to `router`, in order, here."""
    for name in names:
        router.routes.append(_factory_routes.pop(name))


def _assert_all_spliced() -> None:
    if _factory_routes:
        raise RuntimeError(
            "card_hub router: seed factory routes never spliced into "
            f"/api/clientes: {sorted(_factory_routes)} — splice each one where "
            "it belongs, or declare it in _LOCAL_OVERRIDES with a reason."
        )


# ─── Tags · tipos · timeline · notas · cliente<->tags · membros (seed) ──
#
# `/tags` and `/documentos/tipos` are the literal paths — see the module
# docstring's route-ordering hazard; they stay FIRST among this file's own
# routes, exactly where they always were.

_splice(
    "list_tags_route",
    "create_tag_route",
    "update_tag_route",
    "delete_tag_route",
    "list_tipos_documento_route",
    "get_timeline_route",
    "create_nota_route",
    "update_nota_route",
    "delete_nota_route",
    "set_cliente_tags_route",
    "get_membros_route",
    "set_membros_route",
)


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


# ─── Contract completeness (migration 110) ───────────────────────────────
#
# A stricter question than the Documentos checklist above — see
# `documento_checklist_service.completude_contratual`'s own docstring for
# why it is a separate function rather than another checklist item. Read
# only: there is nothing to PATCH here, the missing fields are the same
# `clientes` / `documento-checklist` columns every other route already
# writes.


@router.get("/{cliente_id}/qualificacao-completude")
async def get_qualificacao_completude_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return doc_checklist_svc.completude_contratual(client, org_id, cliente_id)


# ─── Checklist extras (migration 083) ───────────────────────────────────
#
# The OTHER half of the same on-screen surface. Where the block above has no
# create/delete — the mandatory list is the same for everyone and lives in code
# — these lines are authored per client and so carry the full CRUD the other
# half deliberately lacks. Two route groups rather than one polymorphic set,
# because the two are not variants of one resource: one is a tick against a
# code-owned definition, the other is a row somebody wrote.
#
# `tipo` mismatches come back as 422, matching
# `patch_documento_checklist_route`'s answer to an unknown `item_key` — the
# frontend drives both halves from one component and should not need two
# mappings for "you sent the wrong shape".


_splice(
    "list_checklist_extras_route",
    "create_checklist_extra_route",
    "patch_checklist_extra_route",
    "delete_checklist_extra_route",
    "upload_checklist_extra_documento_route",
    "delete_checklist_extra_documento_route",
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


# ─── Roteiros e visitas (migration 082) ─────────────────────────────────
#
# Mounted under `/api/clientes/{cliente_id}` for the same reason agendamentos
# are: a roteiro belongs to an ATENDIMENTO, but the card is the person and
# reads across all of their atendimentos. Every route proves the row belongs to
# this cliente before touching it — and a visita route proves BOTH legs, so
# reaching a visita through someone else's roteiro id fails exactly as reaching
# the roteiro itself would.


@router.get("/{cliente_id}/roteiros")
async def list_roteiros_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return roteiros_svc.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/roteiros", status_code=201)
async def create_roteiro_route(
    cliente_id: UUID,
    body: RoteiroCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    # `AmbiguousAtendimento` is an AppException carrying its own 409, and an
    # unknown código raises `NotFoundError` from `ensure_imovel` — both already
    # structured, so there is nothing to translate here.
    return roteiros_svc.criar(
        client,
        org_id,
        cliente_id,
        imoveis=body.imoveis,
        titulo=body.titulo,
        atendimento_id=body.atendimento_id,
    )


@router.patch("/{cliente_id}/roteiros/{roteiro_id}")
async def patch_roteiro_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    body: RoteiroPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    updates = body.model_dump(exclude_unset=True)
    return roteiros_svc.atualizar(
        client, org_id, cliente_id, roteiro_id, titulo=updates.get("titulo", ...)
    )


@router.delete("/{cliente_id}/roteiros/{roteiro_id}", status_code=204)
async def delete_roteiro_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    user, org_id = _auth_parts(auth)
    # `usuario_id` is threaded because deleting a roteiro can WITHDRAW an
    # accepted proposta and clear the deal's imóvel — a provenance-bearing
    # write, not a bare tombstone.
    roteiros_svc.remover(
        client, org_id, cliente_id, roteiro_id, usuario_id=getattr(user, "id", None)
    )


@router.put("/{cliente_id}/roteiros/{roteiro_id}/ordem")
async def reorder_roteiro_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    body: RoteiroOrdemBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return roteiros_svc.reordenar(client, org_id, cliente_id, roteiro_id, body.visita_ids)


@router.get("/{cliente_id}/roteiros/{roteiro_id}/pdf")
async def roteiro_pdf_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> Response:
    """The cronograma, one imóvel per page, in visiting order.

    `Response` with explicit bytes rather than `StreamingResponse`: the whole
    document is built in memory anyway (it is a handful of text pages), so
    streaming would add a generator and remove the Content-Length.
    """
    _user, org_id = _auth_parts(auth)
    cliente = svc.ensure_cliente(client, org_id, cliente_id)
    roteiro = roteiros_svc.obter(client, org_id, cliente_id, roteiro_id)
    pdf = roteiro_pdf_svc.gerar(
        roteiro,
        cliente_nome=cliente.get("nome_oficial") or cliente.get("nome"),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{roteiro_pdf_svc.nome_arquivo(roteiro)}"'
            )
        },
    )


@router.post("/{cliente_id}/roteiros/{roteiro_id}/visitas", status_code=201)
async def create_visita_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    body: VisitaCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return roteiros_svc.adicionar_visita(
        client, org_id, cliente_id, roteiro_id, body.codigo
    )


@router.patch("/{cliente_id}/roteiros/{roteiro_id}/visitas/{visita_id}")
async def patch_visita_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    body: VisitaPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    updates = body.model_dump(exclude_unset=True)
    return roteiros_svc.atualizar_visita(
        client,
        org_id,
        cliente_id,
        roteiro_id,
        visita_id,
        status=updates.get("status", ...),
        observacao=updates.get("observacao", ...),
    )


@router.patch("/{cliente_id}/roteiros/{roteiro_id}/visitas/{visita_id}/proposta")
async def patch_visita_proposta_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    body: VisitaPropostaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Record a proposta on a visita, and its acceptance.

    🔴 A SEPARATE ROUTE FROM THE VISITA PATCH, matching migration 104's
    separation of the two axes. Accepting here is what writes
    `atendimento_negociacao.imovel_codigo` — the property the contract
    automation is about — so it refuses rather than guesses when the deal
    already names a different imóvel, and unwinds the deal when an acceptance
    is undone. `roteiros_service.registrar_proposta` carries the rules.

    `model_dump(exclude_unset=True)` and the `...` sentinel: `false` is a real
    value (undo), so ABSENCE is the only thing that can mean "leave alone".
    """
    user, org_id = _auth_parts(auth)
    updates = body.model_dump(exclude_unset=True)
    return roteiros_svc.registrar_proposta(
        client,
        org_id,
        cliente_id,
        roteiro_id,
        visita_id,
        proposta=updates.get("proposta", ...),
        aceita=updates.get("aceita", ...),
        usuario_id=getattr(user, "id", None),
    )


@router.delete(
    "/{cliente_id}/roteiros/{roteiro_id}/visitas/{visita_id}", status_code=204
)
async def delete_visita_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    user, org_id = _auth_parts(auth)
    roteiros_svc.remover_visita(
        client,
        org_id,
        cliente_id,
        roteiro_id,
        visita_id,
        usuario_id=getattr(user, "id", None),
    )


# ─── Checklists ─────────────────────────────────────────────────────────


_splice(
    "list_checklists_route",
    "create_checklist_route",
    "update_checklist_route",
    "delete_checklist_route",
    "create_checklist_item_route",
    "update_checklist_item_route",
    "delete_checklist_item_route",
)


# ─── Documentos (LGPD) ──────────────────────────────────────────────────


_splice(
    "list_documentos_route",
)


# 🔴 Local, not the factory's — see `_LOCAL_OVERRIDES` above.
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
    notification_service=Depends(get_conflict_notification_service),
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
            extractor=extractor_factory(str(org_id), tipo_documento),
            notification_service=notification_service,
        )
    return documento


@router.post("/{cliente_id}/documentos/{documento_id}/extrair")
async def reextrair_documento_route(
    cliente_id: UUID,
    documento_id: UUID,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_identity_extractor_factory),
    notification_service=Depends(get_conflict_notification_service),
) -> dict:
    """Re-queue extraction for a document that was never read, or whose
    reading ended in `erro`.

    See `documentos_service.reextrair_documento` for the full contract
    (refusals, and why `extracao_tentativas` is not reset). The background
    task scheduled below is the SAME call `upload_documento_route` schedules
    for a brand-new upload — this is a re-run of that job, not a second
    implementation of it.
    """
    _user, org_id = _auth_parts(auth)
    documento = docs_svc.reextrair_documento(client, org_id, cliente_id, documento_id)
    background.add_task(
        identidade_svc.extrair_identidade,
        client,
        storage,
        org_id,
        cliente_id,
        documento_id,
        extractor=extractor_factory(str(org_id), documento["tipo_documento"]),
        notification_service=notification_service,
    )
    return documento


_splice(
    "get_documento_url_route",
    "delete_documento_route",
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


# ─── Admin-adjudicated field conflicts (migration 138) ─────────────────
#
# Any CAMPOS-driven extraction (identity documents here, matrícula
# qualification in `app.modules.matriculas`) that disagrees with an
# existing `clientes` value lands here instead of silently applying or
# silently skipping — see `identidade_extracao_service.aplicar_campos_ao
# _cliente` / `.resolver_conflito`.


@router.get("/conflitos")
async def listar_conflitos_route(
    cliente_id: Optional[UUID] = Query(
        None,
        description=(
            "Scope to one person's pending conflicts (the card's own "
            "admin-confirmation notice — see `DadosPessoaisForm`). Omitted: "
            "every pending conflict in the org, the org-wide admin queue."
        ),
    ),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list:
    """Every pending field conflict in the org — the admin's queue. Each
    row carries `valor_anterior` (typed/prior) beside `valor_proposto`
    (extracted, or a human's edit of a document-sourced field — migration
    138's reverse direction, `clientes_service.update_cliente`'s
    admin-confirmation gate) plus `origem_proposto` — the comparison an
    admin needs to decide without opening anything else. Read-only; not
    admin-gated (same posture `documento-retencao`'s READ half takes —
    seeing what's pending is not the sensitive half, deciding it is)."""
    _user, org_id = _auth_parts(auth)
    return identidade_svc.conflitos_pendentes(client, org_id, cliente_id)


@router.put("/conflitos/{conflito_id}/decidir")
async def decidir_conflito_route(
    conflito_id: UUID,
    body: DecidirConflitoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Accept or reject a pending conflict. Accepting overwrites
    `clientes.<campo>` with the proposed value (the prior value stays on
    the conflict row); rejecting leaves `clientes` untouched. Refuses
    (422) a conflict that already has a decision — idempotent,
    first-decision-wins.

    🔴 Owner/admin only — the TRUSTED `public.noctus_users` row, never
    `user_metadata` (see `clientes_router._is_org_admin`'s own docstring
    for the exact spoof this closes). Deciding a conflict IS the
    "admin confirmation" the owner's provenance directive names; letting
    any authenticated org member decide would make that confirmation
    meaningless."""
    user, org_id = _auth_parts(auth)
    if not is_org_admin(get_core_client(), getattr(user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail="Decidir um conflito de dados é restrito a administradores.",
        )
    return identidade_svc.resolver_conflito(
        client,
        org_id,
        conflito_id,
        aceitar=body.aceitar,
        decidido_por=getattr(user, "id", None),
    )


_splice(
    "list_acessos_route",
)


# ─── Card summary ───────────────────────────────────────────────────────


_splice(
    "get_card_route",
)


# ─── Compradores / partes do atendimento (migration 073) ─────────────────────
#
# Mounted under `/api/clientes/{cliente_id}` rather than under the atendimento,
# following `agendamentos`: the CARD is the surface these are managed from, the
# card is a person, and making the frontend resolve an atendimento id before it
# can render a panel would push a decision the service already knows how to
# make out into every caller.


@router.get("/{cliente_id}/compradores")
async def list_compradores_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    lado: Optional[str] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Parties on one SIDE of this card's atendimento.

    🔴 ONE ENDPOINT PAIR SERVES BOTH TABS, selected by `?lado=`. The Vendedor
    tab is the Comprador tab reading different rows — same resolution, same
    linking rules, same person model (migration 098) — so a second
    `/vendedores` route would be the same handler twice, and the copy that
    stopped being edited would be the bug.

    The path keeps its `compradores` spelling: renaming it to `/partes` would
    break every client for a word, and `lado` already says which side.
    """
    _user, org_id = _auth_parts(auth)
    return compradores_svc.listar(
        client, org_id, cliente_id, atendimento_id=atendimento_id, lado=lado
    )


@router.post("/{cliente_id}/compradores", status_code=201)
async def create_comprador_route(
    cliente_id: UUID,
    body: CompradorCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    # `AmbiguousAtendimento` is an AppException carrying its own 409 + the
    # candidate ids, so it needs no translation here — same as agendamentos.
    return compradores_svc.adicionar(
        client,
        org_id,
        cliente_id,
        parte_cliente_id=body.cliente_id,
        nome=body.nome,
        celular=body.celular,
        # Left as None so the SERVICE picks the side's default — `comprador`
        # for the buyer side, `proprietario` for the seller's. Defaulting here
        # would hard-code the buyer's answer for both.
        papel=body.papel,
        observacao=body.observacao,
        atendimento_id=body.atendimento_id,
        lado=body.lado,
        user_id=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/compradores/{parte_id}")
async def patch_comprador_route(
    cliente_id: UUID,
    parte_id: UUID,
    body: PartePapelPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Correct a party's role — the only field on this edge worth changing.

    🔴 THE MISSING THIRD VERB. This block had `listar / adicionar / remover` and
    the add-dialog sends neither `papel` nor `lado`, so the side's default was
    the first and last word on every party ever created. The UI now edits the
    badge it was already showing.

    A 409 here is the spouse link refusing to overwrite a different spouse
    (`_recusar_conjuge_ocupado`), NOT a duplicate-party conflict — and it is
    raised before anything is written, so a refused request changed nothing.

    No `lado` in the body, on purpose: see `PartePapelPatchBody`.
    """
    _user, org_id = _auth_parts(auth)
    return compradores_svc.atualizar_papel(
        client, org_id, cliente_id, parte_id, papel=body.papel
    )


@router.delete("/{cliente_id}/compradores/{parte_id}", status_code=204)
async def delete_comprador_route(
    cliente_id: UUID,
    parte_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    compradores_svc.remover(client, org_id, cliente_id, parte_id)


# ─── Empresas (migration 167, P0c) ────────────────────────────────────────
#
# The company-graph panel: which PJs this card's people (titular + both
# sides' partes + every vendedor's registered spouse) are tied to, and
# whether the deal needs certidões for them. `empresa_documentos`/Cartão
# CNPJ upload lifecycle lives under `/api/empresas/*` instead
# (`app.modules.empresas.router`) — this pair only lists/links.


@router.get("/{cliente_id}/empresas")
async def list_empresas_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return empresas_svc.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/empresas", status_code=201)
async def create_empresa_route(
    cliente_id: UUID,
    body: EmpresaManualCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return empresas_svc.adicionar_manual(
        client, org_id, cliente_id,
        cnpj=body.cnpj,
        participante_cliente_id=body.participante_cliente_id,
        razao_social=body.razao_social,
        participacao_pct=body.participacao_pct,
        confirmado_por=getattr(user, "id", None),
    )


@router.delete("/{cliente_id}/empresas/{empresa_id}")
async def delete_empresa_route(
    cliente_id: UUID,
    empresa_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_empresas_storage_backend),
) -> dict:
    """Unlinks `empresa_id` from `cliente_id`; the `empresas` row (and its
    CASCADE-linked `empresa_documentos`) is hard-deleted, and its certidões
    soft-deleted through the audited certidões mechanism, only when this
    was the last participação — see `dados_service.remover_participacao`'s
    docstring. ADMIN/OWNER ONLY (same trusted-DB gate `excluir_cliente_
    route` uses, same reasoning: this can delete real rows + storage
    files, irreversibly, the moment the last link goes).

    Storage is deleted AFTER the DB rows are gone — same ordering
    `excluir_cliente_route` takes and for the same reason (a storage
    delete that ran first could leave a file gone with its row still
    pointing at it, if the DB call then failed). A failure here is
    reported in `storage_falhas`, never swallowed. Certidão FILES are
    NEVER touched here — the soft-delete this cascades into never removes
    a blob (owner rule: every deletion is recoverable + attributable); the
    already-existing 30-day `certidoes.service.purge_excluidas` scheduled
    job is the only thing that ever hard-deletes them."""
    user, org_id = _auth_parts(auth)
    require_org_admin_role(
        get_core_client(), getattr(user, "id", None), "Excluir empresa"
    )

    resultado = empresas_svc.remover(
        client, org_id, cliente_id, empresa_id,
        acting_user_id=getattr(user, "id", None),
    )

    storage_falhas: list[str] = []
    for documento in resultado["documentos"]:
        storage_path = documento.get("storage_path")
        if not storage_path:
            continue
        try:
            await storage.delete(bucket=_EMPRESAS_BUCKET, key=storage_path)
        except Exception:
            logger.exception(
                "delete_empresa_route: falha ao remover arquivo do storage "
                "empresa_id=%s storage_path=%s", empresa_id, storage_path,
            )
            storage_falhas.append(storage_path)

    return {
        "participacao_removida": resultado["participacao_removida"],
        "empresa_removida": resultado["empresa_removida"],
        "documentos_removidos": len(resultado["documentos"]),
        "certidoes_removidas": resultado["certidoes_removidas"],
        "storage_falhas": storage_falhas,
    }


# ─── Certidões — Levantamento matriz (Levantamento de Certidões.xlsx) ─────
#
# The "Certidões" card tab: every certidão type crossed with every vendedor
# party + their PJ-requiring empresas, aggregated server-side — see
# `certidoes_matriz_service`'s own module docstring.


@router.get("/{cliente_id}/certidoes/matriz")
async def get_certidoes_matriz_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return certidoes_matriz_svc.montar_matriz(client, org_id, cliente_id)


@router.post("/{cliente_id}/certidoes/matriz/linhas", status_code=201)
async def criar_linha_matriz_route(
    cliente_id: UUID,
    body: LinhaMatrizCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return certidoes_matriz_linhas_svc.criar(
        client, org_id, cliente_id, nome=body.nome, created_by=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/certidoes/matriz/linhas/{linha_id}")
async def renomear_linha_matriz_route(
    cliente_id: UUID,
    linha_id: UUID,
    body: LinhaMatrizPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return certidoes_matriz_linhas_svc.renomear(client, org_id, cliente_id, linha_id, nome=body.nome)


@router.delete("/{cliente_id}/certidoes/matriz/linhas/{linha_id}", status_code=204)
async def remover_linha_matriz_route(
    cliente_id: UUID,
    linha_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> None:
    _user, org_id = _auth_parts(auth)
    certidoes_matriz_linhas_svc.remover(client, org_id, cliente_id, linha_id)


# ─── Negociação (migration 077) ─────────────────────────────────────────


@router.get("/{cliente_id}/negociacao")
async def get_negociacao_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return negociacao_svc.obter(client, org_id, cliente_id)


@router.patch("/{cliente_id}/negociacao")
async def patch_negociacao_route(
    cliente_id: UUID,
    body: NegociacaoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    # `model_fields_set`, NOT `exclude_none`: `None` is a real value here
    # (clearing a valor entered by mistake), so absence is the only thing
    # that can mean "leave alone".
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    resultado = negociacao_svc.atualizar(
        client, org_id, cliente_id, valores=valores,
        usuario_id=getattr(user, "id", None),
    )
    # H4 — a `valor_negociado` PATCH is one of the derived intermediária
    # suggestion's inputs; recompute it here rather than inside
    # `negociacao_service`/`negociacao_estruturada_service` themselves,
    # which would need a cross-module import cycle (the ROUTER already
    # imports both services, so it is the natural orchestration point).
    if "valor_negociado" in valores:
        neg_estruturada_svc.sincronizar_parcela_intermediaria_derivada(
            client, org_id, cliente_id,
        )
    return resultado


# ─── Negociação — D2 conflitos (S2 contract §E5.4) ──────────────────────


@router.get("/{cliente_id}/negociacao/conflitos")
async def list_negociacao_conflitos_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Every pending `atendimento_campo_conflitos` row for this deal — the
    admin's queue (house envelope: `{"items": [...]}`)."""
    _user, org_id = _auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    items = negociacao_extracao_svc.listar_conflitos(client, org_id, atendimento_id)
    return {"items": items, "total": len(items)}


@router.post("/{cliente_id}/negociacao/conflitos/{conflito_id}/resolver")
async def resolver_negociacao_conflito_route(
    cliente_id: UUID,
    conflito_id: UUID,
    body: ResolverConflitoNegociacaoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Accept or reject a pending conflict — owner/admin only, same
    restriction `decidir_conflito_route` takes for migration 138: deciding a
    conflict IS the "admin confirmation" the D1/D2 contract names."""
    user, org_id = _auth_parts(auth)
    if not is_org_admin(get_core_client(), getattr(user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail="Decidir um conflito de dados é restrito a administradores.",
        )
    resultado = negociacao_extracao_svc.resolver_conflito(
        client, org_id, conflito_id,
        aceitar=body.decisao == "aceitar",
        decidido_por=getattr(user, "id", None),
    )
    # An accepted valor_negociado/parcela conflict is also an H4 input.
    neg_estruturada_svc.sincronizar_parcela_intermediaria_derivada(client, org_id, cliente_id)
    return resultado


# ─── Financiamento / Escritura (migration 078) ──────────────────────────


@router.get("/{cliente_id}/financiamento")
async def get_financiamento_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return financiamento_svc.obter(client, org_id, cliente_id)


@router.patch("/{cliente_id}/financiamento")
async def patch_financiamento_route(
    cliente_id: UUID,
    body: FinanciamentoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return financiamento_svc.atualizar(
        client, org_id, cliente_id, valores=valores,
        usuario_id=getattr(user, "id", None),
    )


@router.post("/{cliente_id}/financiamento/documentos")
async def upload_financiamento_documento_route(
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
    documento = await financiamento_svc.upload(
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
    # S2 contract §E1 — the extractor factory routes on `fontes.FONTES[tipo]
    # .extrator`, the same seam `deps._build_identity_extractor` already
    # uses for `serasa_crednet`/`cartao_cnpj` (widened here for `guia_itbi`/
    # `proposta_financiamento`/`contrato_financiamento`).
    if financiamento_svc.deve_extrair(tipo_documento):
        atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
        background.add_task(
            negociacao_extracao_svc.extrair,
            client, storage, org_id, atendimento_id, UUID(documento["id"]),
            extractor=extractor_factory(str(org_id), tipo_documento),
            # NOC-REMEDIATE[atendimento-conflito-notificacao] — no atendimento-
            # scoped notifier exists yet (`app/services/notification_service.py`
            # is outside this slice's file scope); `campo_conflitos.
            # notificar_conflitos` degrades to a WARNING log naming every
            # unannounced conflict, never a silent drop.
            notification_service=None,
        )
    return documento


@router.post("/{cliente_id}/financiamento/documentos/{documento_id}/extrair")
async def reextrair_financiamento_documento_route(
    cliente_id: UUID,
    documento_id: UUID,
    background: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_identity_extractor_factory),
) -> dict:
    """Re-run extraction. Refused (422) while the document is already
    `pendente`/`processando` — same posture `empresas.router.
    reextrair_documento_route` takes (S2 contract §E5.1)."""
    from noctusai_lib.primitives.exceptions import ValidationError_

    _user, org_id = _auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    documento = financiamento_svc.STORE.exigir(client, org_id, atendimento_id, documento_id)
    if documento.get("extracao_status") in ("pendente", "processando"):
        raise ValidationError_(
            "Este documento já está em processamento.", field="extracao_status"
        )
    from app.services import table_reads as _table_reads

    _table_reads.table(client, financiamento_svc.DOCUMENTOS_TABLE).update(
        {"extracao_status": "pendente"}
    ).eq("id", str(documento_id)).execute()
    background.add_task(
        negociacao_extracao_svc.extrair,
        client, storage, org_id, atendimento_id, documento_id,
        extractor=extractor_factory(str(org_id), documento["tipo_documento"]),
        notification_service=None,
    )
    return {**documento, "extracao_status": "pendente"}


@router.post("/{cliente_id}/financiamento/documentos/{documento_id}/extracao/confirmar")
async def confirmar_financiamento_extracao_route(
    cliente_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """D2 — stamps `confirmado_por`/`confirmado_em` on every still-pending
    value whose `*_documento_id == documento_id` (S2 contract §E5.2)."""
    user, org_id = _auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    financiamento_svc.STORE.exigir(client, org_id, atendimento_id, documento_id)
    return negociacao_extracao_svc.confirmar_leitura(
        client, org_id, atendimento_id, documento_id,
        confirmado_por=getattr(user, "id", None),
    )


@router.post("/{cliente_id}/financiamento/documentos/{documento_id}/extracao/descartar")
async def descartar_financiamento_extracao_route(
    cliente_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return financiamento_svc.descartar_extracao(
        client, org_id, cliente_id, documento_id, usuario_id=getattr(user, "id", None),
    )


@router.get("/{cliente_id}/financiamento/documentos/{documento_id}/url")
async def get_financiamento_documento_url_route(
    cliente_id: UUID,
    documento_id: UUID,
    intent: str = Query("view"),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    return await financiamento_svc.url_do_documento(
        client, storage, org_id, cliente_id, documento_id,
        usuario_id=getattr(user, "id", None), intent=intent,
    )


@router.get("/{cliente_id}/financiamento/documentos/{documento_id}/acessos")
async def list_financiamento_acessos_route(
    cliente_id: UUID,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return financiamento_svc.listar_acessos(client, org_id, cliente_id, documento_id)


@router.delete(
    "/{cliente_id}/financiamento/documentos/{documento_id}", status_code=204
)
async def delete_financiamento_documento_route(
    cliente_id: UUID,
    documento_id: UUID,
    # A required query param, not a body — the seed `ApiClient.delete()` has
    # no body parameter. An LGPD delete without a recorded reason is not one.
    motivo: str = Query(..., min_length=1, max_length=500),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    user, org_id = _auth_parts(auth)
    financiamento_svc.remover(
        client, org_id, cliente_id, documento_id, motivo=motivo,
        usuario_id=getattr(user, "id", None),
    )


# ─── Contratos (migration 106) ───────────────────────────────────────────


@router.get("/{cliente_id}/contratos")
async def list_contratos_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return contratos_svc.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/contratos", status_code=201)
async def create_contrato_route(
    cliente_id: UUID,
    file: UploadFile = File(...),
    titulo: str = Form(..., min_length=1, max_length=200),
    modelo: str = Form("compra_venda"),
    rotulo: Optional[str] = Form(None, max_length=120),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    data = await file.read()
    return await contratos_svc.criar(
        client,
        storage,
        org_id,
        cliente_id,
        titulo=titulo,
        modelo=modelo,
        rotulo=rotulo,
        filename=file.filename or "arquivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        criado_por=getattr(user, "id", None),
    )


@router.post("/{cliente_id}/contratos/{contrato_id}/versoes", status_code=201)
async def create_contrato_versao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    file: UploadFile = File(...),
    rotulo: Optional[str] = Form(None, max_length=120),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    data = await file.read()
    return await contratos_svc.nova_versao(
        client,
        storage,
        org_id,
        cliente_id,
        contrato_id,
        filename=file.filename or "arquivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        rotulo=rotulo,
        usuario_id=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/contratos/{contrato_id}")
async def patch_contrato_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: ContratoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return contratos_svc.atualizar(
        client, org_id, cliente_id, contrato_id, valores=valores,
        usuario_id=getattr(user, "id", None),
    )


@router.put("/{cliente_id}/contratos/{contrato_id}/processo-legado")
async def put_contrato_processo_legado_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: ProcessoLegadoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Migration 151. Owner directive, 2026-09-22: an EXPLICIT, admin-only,
    logged switch per contract — never an automatic date heuristic. When
    `ativo=True`, the contract gate's certidão TIME rules (emission age /
    validade — never `CERTIDAO_EMITIDA_APOS_ASSINATURA`, a data error, not
    an age rule) become warnings instead of blocks for THIS deal, because
    it started before the platform (`contrato_gerador.derivacao._certidoes`).

    🔴 Owner/admin only — same TRUSTED `noctus_users` row (never
    `user_metadata`) `decidir_conflito_route` reads for migration 138; see
    that route's own docstring for the exact spoof this closes. Strict
    `== 401`/`== 403` per `KB § PATTERNS/compliance/auth-boundary-false-green.md`.
    """
    user, org_id = _auth_parts(auth)
    if not is_org_admin(get_core_client(), getattr(user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail="Marcar um contrato como processo anterior à plataforma "
            "é restrito a administradores.",
        )
    return contratos_svc.definir_processo_legado(
        client, org_id, cliente_id, contrato_id,
        ativo=body.ativo, motivo=body.motivo,
        usuario_id=getattr(user, "id", None),
    )


@router.get("/{cliente_id}/contratos/{contrato_id}/versoes/{versao_id}/url")
async def get_contrato_versao_url_route(
    cliente_id: UUID,
    contrato_id: UUID,
    versao_id: UUID,
    intent: str = Query("view"),
    formato: str = Query("pdf"),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    user, org_id = _auth_parts(auth)
    return await contratos_svc.url_versao(
        client, storage, org_id, cliente_id, contrato_id, versao_id,
        usuario_id=getattr(user, "id", None), intent=intent, formato=formato,
    )


@router.delete(
    "/{cliente_id}/contratos/{contrato_id}/versoes/{versao_id}", status_code=204
)
async def delete_contrato_versao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    versao_id: UUID,
    motivo: str = Query(..., min_length=1, max_length=500),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    user, org_id = _auth_parts(auth)
    contratos_svc.remover_versao(
        client, org_id, cliente_id, contrato_id, versao_id, motivo=motivo,
        usuario_id=getattr(user, "id", None),
    )


@router.delete("/{cliente_id}/contratos/{contrato_id}", status_code=204)
async def delete_contrato_route(
    cliente_id: UUID,
    contrato_id: UUID,
    motivo: str = Query(..., min_length=1, max_length=500),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    user, org_id = _auth_parts(auth)
    contratos_svc.remover_contrato(
        client, org_id, cliente_id, contrato_id, motivo=motivo,
        usuario_id=getattr(user, "id", None),
    )


_assert_all_spliced()


# ─── The org's split rule ────────────────────────────────────────────────
#
# 🔴 A SEPARATE ROUTER, on `/api/negociacao`, deliberately.
#
# These are ORG settings, not a cliente resource, and hanging them off
# `/api/clientes` would need a literal 1-segment path — which is exactly the
# shape that structurally collides with `clientes_router`'s bare
# `/{cliente_id}` (see this module's header for the `/tags` incident). A
# distinct prefix has no such shape to collide with, so no mount-order
# constraint applies to it at all.

defaults_router = APIRouter(prefix="/api/negociacao", tags=["negociacao"])


@defaults_router.get("/defaults")
async def get_negociacao_defaults_route(
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return negociacao_svc.obter_defaults(client, org_id)


@defaults_router.patch("/defaults")
async def patch_negociacao_defaults_route(
    body: NegociacaoDefaultsPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return negociacao_svc.atualizar_defaults(
        client, org_id, valores=valores, usuario_id=getattr(user, "id", None)
    )


__all__ = ["defaults_router", "proveniencia_router", "router"]

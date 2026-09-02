"""`/api/matriculas/*` — upload a matrícula PDF, get its full text back.

Ported from `erp-imobiliario`'s `app/routers/matriculas.py` (2026-09-02).
The route shapes, status codes and Portuguese are identical; three things
changed, and each one is a decision rather than a translation:

1. 🔴 ORG COMES FROM THE DB, NOT THE JWT — and now not from this file
   either. ERP had to read `noctus_users` by hand (`resolve_org_id_db`)
   because its `get_current_user` returned no org; a stale JWT claim
   yielded a NULL org, the app omitted the NOT NULL column, and the insert
   500'd for a freshly-provisioned user (erp incident 2026-07-07, migration
   038). This product's canonical dep `get_current_user_org` already
   resolves org from `public.noctus_users` FIRST and 403s when there is
   none, so the hand-rolled lookup and its 400 branch are gone — the
   incident is closed one layer down instead of re-litigated here.
   Migration 090 additionally stamps `org_id DEFAULT public.current_org_id()`,
   so the INSERT below deliberately does NOT send an org: the DB derives it
   from the same table RLS trusts, and the app cannot get it wrong.

2. 🔴 NO `log_action`. ERP audited upload + delete through
   `app.dependencies.log_action`; this product has no audit-log table and
   no such helper. The calls are dropped rather than shimmed — inventing a
   product-local audit trail to keep two call sites company is a fork, not
   a port. Surfaced as `drift-found:` for a real decision.

3. 🔴 THE REQUEST PATH USES THE CALLER'S TOKEN; THE BACKGROUND TASK DOES
   NOT. RLS decides which org's rows a request can reach — application
   `.eq("org_id", ...)` filters are a second lock, not the first one. But a
   background task outlives the request that spawned it, so it cannot hold
   that token (a long vision pass can outlive its expiry, and the write
   would then fail with nobody left to tell). It writes service-role, which
   is exactly why every write in `service.py` carries an explicit `org_id`
   predicate.

Route ordering: every path here is under the literal `/api/matriculas`
prefix, and the only dynamic segment (`/extracoes/{extracao_id}`) sits
below a literal one. Nothing in this module can shadow, or be shadowed by,
another router.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from noctusai_lib.api.crud_safety import delete_or_404

from app.dependencies import coerce_org_uuid, get_current_user_org, get_user_client
from app.modules.matriculas.deps import (
    TranscriberFactory,
    get_background_client,
    get_transcriber_factory,
)
from app.modules.matriculas.service import (
    TABLE,
    check_required_credentials,
    processar_extracao,
)
from app.responses import (
    calculate_pagination,
    ok_response,
    paginated_response,
    success_response,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matriculas", tags=["Matrículas"])

#: Ceiling for one upload. A matrícula is a handful of scanned pages; 20 MB
#: is generous for that and is the number ERP shipped.
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

#: 🔴 THE APP REFUSES TO BOOT WITHOUT THIS ENTRY IN `main.py`.
#: `noctusai_seed.upload_route_overrides` requires every mounted route that
#: declares an `UploadFile` to carry a `max_body_path_overrides` entry — the
#: platform-wide 1 MB default exists to DoS-guard inbound webhooks and would
#: silently 413 every realistic matrícula. The tech-lead merges this dict
#: into `main.py`'s `_MAX_BODY_PATH_OVERRIDES` in the SAME commit that
#: appends this module to `MODULES`. Declared here, next to the number it
#: mirrors, so the two cannot drift.
MAX_BODY_PATH_OVERRIDES = {"/api/matriculas/extrair": MAX_FILE_SIZE}

#: Selected for the history list. `texto_extraido` is deliberately absent —
#: a full matrícula transcription is tens of KB, and a 50-row page of them
#: is megabytes nobody on that screen reads.
_COLUNAS_LISTA = (
    "id,nome_arquivo,tamanho_bytes,num_paginas,status,erro_mensagem,created_at"
)


def _auth_parts(auth) -> tuple[object, str, str]:
    """`(user, token, org_id)` with the org normalised to a UUID string.

    `get_current_user_org` is `required=True`, so an unprovisioned caller is
    already a 403 before this runs — there is no org-less branch to handle.
    """
    user, token, raw_org = auth
    return user, token, str(coerce_org_uuid(raw_org))


@router.post("/extrair")
async def extrair_matricula(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    auth=Depends(get_current_user_org),
    background_db=Depends(get_background_client),
    transcriber_factory: TranscriberFactory = Depends(get_transcriber_factory),
):
    """Upload a matrícula PDF and start text extraction in the background."""
    user, token, org_id = _auth_parts(auth)
    db = get_user_client(token)

    # Validated up front: the extraction runs detached, so a missing key
    # discovered there reaches the user as a row that failed 40 seconds
    # later instead of as an answer to the request that caused it.
    missing = check_required_credentials(org_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Configure em Configurações → Chaves de API.",
        )

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Arquivo muito grande ({len(pdf_bytes) // (1024 * 1024)}MB). "
                f"Máximo: {MAX_FILE_SIZE // (1024 * 1024)}MB."
            ),
        )
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    # 🔴 `org_id` is deliberately absent: migration 090 defaults the column
    # to `public.current_org_id()`, the same trusted source RLS reads. The
    # app never names the org on a write, so it can never name the wrong one.
    result = (
        db.table(TABLE)
        .insert(
            {
                "user_id": user.id,
                "nome_arquivo": file.filename or "matricula.pdf",
                "tamanho_bytes": len(pdf_bytes),
                "status": "pendente",
            }
        )
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar extração")
    extracao = result.data[0]

    # 🔴 The org the DETACHED half writes with comes from the ROW, not from
    # this request. The two agree — the dep resolved the org from
    # `noctus_users` and the column DEFAULT reads the same table — but
    # "agree" is a claim about two code paths, while `extracao["org_id"]` is
    # the org the row ACTUALLY landed in. A background UPDATE scoped to the
    # wrong org is not an error, it is a no-op: the row stays `processando`
    # forever and only the hourly sweep ever notices.
    org_da_linha = str(extracao.get("org_id") or org_id)

    background_tasks.add_task(
        _run_extraction,
        extracao["id"],
        pdf_bytes,
        org_da_linha,
        background_db,
        transcriber_factory,
    )

    return success_response(extracao)


@router.get("/extracoes")
async def listar_extracoes(
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth=Depends(get_current_user_org),
):
    """List extraction history — without `texto_extraido` (see `_COLUNAS_LISTA`)."""
    _user, token, _org_id = _auth_parts(auth)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    count_query = db.table(TABLE).select("id", count="exact")
    if busca:
        count_query = count_query.ilike("nome_arquivo", f"%{busca}%")
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    query = db.table(TABLE).select(_COLUNAS_LISTA).order("created_at", desc=True)
    if busca:
        query = query.ilike("nome_arquivo", f"%{busca}%")
    # Bounded by `page_size` (≤ 200), so this read cannot reach PostgREST's
    # 1 000-row cap — no pager needed.
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(
        result.data or [], total, validated_page, validated_page_size
    )


@router.get("/extracoes/{extracao_id}")
async def obter_extracao(extracao_id: str, auth=Depends(get_current_user_org)):
    """Get a single extraction WITH its full text."""
    _user, token, _org_id = _auth_parts(auth)
    db = get_user_client(token)

    # `maybe_single`, not `single`: PostgREST's `single` raises on zero rows
    # (PGRST116) rather than returning empty, which surfaces as a 500 for
    # what is an ordinary 404.
    result = db.table(TABLE).select("*").eq("id", extracao_id).maybe_single().execute()
    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Extração não encontrada")

    return success_response(result.data)


@router.delete("/extracoes/{extracao_id}")
async def excluir_extracao(extracao_id: str, auth=Depends(get_current_user_org)):
    """Delete an extraction."""
    _user, token, _org_id = _auth_parts(auth)
    db = get_user_client(token)

    delete_or_404(db, TABLE, ("id", extracao_id), message="Extração não encontrada")

    return ok_response("Extração excluída com sucesso")


def _run_extraction(
    extracao_id: str,
    pdf_bytes: bytes,
    org_id: str,
    db,
    transcriber_factory: TranscriberFactory,
) -> None:
    """Bridge the async pipeline into FastAPI's sync background-task slot.

    A sync task runs in the threadpool, so `asyncio.run` here spins its own
    loop without touching the request loop. `processar_extracao` never
    raises, so this cannot leave a thread dying silently.
    """
    asyncio.run(
        processar_extracao(
            extracao_id,
            pdf_bytes,
            org_id,
            db,
            transcriber_factory=transcriber_factory,
        )
    )


__all__ = ["MAX_BODY_PATH_OVERRIDES", "MAX_FILE_SIZE", "router"]

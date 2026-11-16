"""Estruturas library -- the LOAD (estruturas-contract.md section 6.3, tier ``platform``; mechanism section 7).

Platform admins only (``require_platform_admin``). The router must be included BEFORE the two ``/estruturas`` routers of
EST-1 so ``/importacoes`` is not swallowed by ``/{estrutura_id}``. There is NO model call anywhere on this path.

* ``POST /estruturas/importacoes`` -- ``dry_run`` (default) simulates synchronously (200) and writes only the
  ``simulada`` lote row; an apply (``dry_run=false``) needs a same-sha simulation from the last 24 h (409
  ``simulacao_obrigatoria``), allows one run at a time (409 ``importacao_em_andamento``), stores the document in the
  private bucket and enqueues the ``estruturas.importar`` job (202).
* ``GET /estruturas/importacoes/{id}`` / ``GET /estruturas/importacoes`` -- poll / list. Counts and reason codes only.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import json
import logging
import uuid

from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.dependencies import get_admin_client, require_platform_admin
from app.modules.certidoes.deps import storage_for
from app.modules.media_creation.deps import BIBLIOTECA_BUCKET
from app.modules.media_creation.schemas.estruturas_importacao import ImportacaoCreate
from app.modules.media_creation.services import estruturas_import as imp
from app.modules.media_creation.services import geracao_jobs

logger = logging.getLogger(__name__)

router = make_router(
    tier="platform", guard=require_platform_admin, prefix="/api/media-creation/estruturas/importacoes",
    tags=["Media Creation — Estruturas (importação)"],
)


def get_importacao_storage() -> StorageBackend:
    """Private ``sw-biblioteca`` bucket (the document waits here for the job). Tests MUST override with a Fake."""
    return storage_for(get_admin_client())


def get_importacao_jobs() -> JobRepository:
    return geracao_jobs.make_jobs_repository(get_admin_client())


def get_importacao_store() -> imp.ImportStore:
    """The library I/O seam (PostgREST reads + the EST-1 RPCs). Tests override it with an in-memory double."""
    return imp.SupabaseImportStore(get_admin_client())


def _svc(auth, store: imp.ImportStore | None = None) -> imp.ImportacaoService:
    return imp.ImportacaoService(
        get_admin_client(), user_id=str(getattr(auth[0], "id", "") or ""), limite_perfis=int(settings.biblioteca_max_perfis_plataforma),
        store=store,
    )


def _raise(exc: imp.ImportacaoError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("", status_code=202)
async def importar(
    body: ImportacaoCreate, auth=Depends(require_platform_admin), storage: StorageBackend = Depends(get_importacao_storage),
    jobs: JobRepository = Depends(get_importacao_jobs), store: imp.ImportStore = Depends(get_importacao_store),
):
    svc = _svc(auth, store)
    conteudo = body.model_dump(mode="json")["conteudo"]
    try:
        if body.dry_run:
            relatorio = await run_blocking(svc.simular, body.fonte, conteudo, body.arquivo_nome)
            return JSONResponse(status_code=200, content=success_response(relatorio))
        geracao_jobs.assert_geracao_disponivel()
        lote = await run_blocking(svc.iniciar, body.fonte, conteudo, body.arquivo_nome)
    except imp.ImportacaoError as exc:
        _raise(exc)
    importacao_id = lote["id"]
    try:
        await storage.put(
            bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(importacao_id), data=json.dumps(conteudo, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        await jobs.enqueue(
            type=imp.JOB_TYPE, payload={"importacao_id": importacao_id}, dedupe_key=f"{imp.JOB_TYPE}:{importacao_id}", max_retries=2,
        )
    except Exception as exc:  # noqa: BLE001 - settle the lote as failed (never leave a spinner), then surface a 503
        logger.error("estruturas.importar: falha ao iniciar o lote %s (%s)", importacao_id, type(exc).__name__)
        await run_blocking(svc.falhar, importacao_id, "falha_ao_iniciar")
        try:
            await storage.delete(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(importacao_id))
        except Exception:  # noqa: BLE001 - best effort; the lote is already settled
            logger.exception("estruturas.importar: documento do lote %s não removido", importacao_id)
        raise HTTPException(status_code=503, detail={"code": "geracao_indisponivel", "detail": "A geração está indisponível no momento."}) from exc
    return JSONResponse(status_code=202, content=success_response({"id": importacao_id, "status": "em_andamento"}))


@router.get("/{importacao_id}")
async def obter_importacao(importacao_id: uuid.UUID, auth=Depends(require_platform_admin)):
    try:
        return success_response(await run_blocking(_svc(auth).obter, str(importacao_id)))
    except imp.ImportacaoError as exc:
        _raise(exc)


@router.get("")
async def listar_importacoes(
    limit: int = Query(default=20, ge=1, le=imp.LISTA_MAX), offset: int = Query(default=0, ge=0, le=100_000),
    auth=Depends(require_platform_admin),
):
    return success_response(await run_blocking(_svc(auth).listar, limit, offset))

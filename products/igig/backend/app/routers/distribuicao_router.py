"""Distribuição e Métricas — Módulo 5.

  PUBLICAÇÃO  /api/distribuicao/publicacoes …   schedule, run, cancel
  MÉTRICAS    /api/distribuicao/metricas …      snapshot ingest + read
  BI          /api/distribuicao/bi/eficiencia   taxa de refação + custo real

**What is real today.** Scheduling, the queue, status transitions, retry
accounting, metric snapshots and the entire BI rollup are real and tested. The
outbound network calls are not: no channel credentials exist, so
`get_publisher` returns the Fake in development and the real adapters raise
`PublisherNotConfigured`. A publish therefore either genuinely succeeds or
fails LOUDLY — nothing is ever marked `publicada` without a platform-confirmed
id, because a post the client never saw showing as published is the one
outcome that destroys trust in this module.

Metrics ingest is a POST rather than a scheduled pull for the same reason:
until the platform APIs are homologated there is nothing to pull from, and an
endpoint that accepts a snapshot lets the dashboard be built and verified now.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py for the slowapi/PEP 563 interaction.
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.distribuicao import (
    AgendarPublicacao,
    EficienciaOut,
    MetricaIn,
    MetricaOut,
    PublicacaoOut,
)
from app.services.bi_service import BIService
from app.services.publicacao_publisher import PublisherNotConfigured, get_publisher
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/distribuicao", tags=["distribuicao"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _token_do_canal(repos: Repositorios, org_id: str, canal: str) -> str | None:
    """Resolve the channel token: per-org credential first, env fallback second.

    Mirrors the platform's own credential precedence (`org_settings` →
    `platform_settings` → env). Returning ``None`` is a normal outcome — the
    factory then yields the Fake, and nothing is ever reported as published.
    """
    if settings.igig_cofre_key:
        try:
            token = repos.integracao.token_de(
                org_id, canal, settings.igig_cofre_key.encode("utf-8")
            )
        except Exception:  # noqa: BLE001 — a bad stored token must not 500 the
            # publish path; it degrades to "not configured" and is recorded.
            logger.warning("token de %s ilegível para org=%s", canal, org_id)
            token = None
        if token:
            return token
    if canal in ("instagram", "facebook"):
        return settings.igig_meta_token or None
    if canal == "tiktok":
        return settings.igig_tiktok_token or None
    return settings.igig_linkedin_token or None


# ── Publicações ─────────────────────────────────────────────────────
@router.get("/publicacoes", response_model=list[PublicacaoOut])
async def listar_publicacoes(
    pauta_id: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[PublicacaoOut]:
    org_id = _org(auth)
    linhas = (
        repos.publicacao.da_pauta(org_id, pauta_id) if pauta_id else repos.publicacao.listar(org_id)
    )
    return [PublicacaoOut(**p) for p in linhas]


@router.post("/publicacoes", response_model=PublicacaoOut, status_code=status.HTTP_201_CREATED)
async def agendar_publicacao(
    payload: AgendarPublicacao,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PublicacaoOut:
    """Schedule a pauta on one channel.

    A second schedule for the same pauta+canal is a 409, enforced by a partial
    unique index — a duplicate would double-post to the client's real account.
    """
    org_id = _org(auth)
    try:
        repos.pauta.buscar(org_id, payload.pauta_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Pauta não encontrada")

    from noctusai_lib.integrations.persistence import PersistenceError

    try:
        registro = repos.publicacao.agendar(
            org_id, payload.pauta_id, payload.canal, payload.agendada_para
        )
    except PersistenceError:
        raise HTTPException(
            status_code=409,
            detail=f"Esta pauta já tem publicação ativa em {payload.canal}",
        )
    return PublicacaoOut(**registro)


@router.post("/publicacoes/{publicacao_id}/executar", response_model=PublicacaoOut)
async def executar_publicacao(
    publicacao_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PublicacaoOut:
    """Publish now.

    Success requires a platform-confirmed `external_id`. Any failure — missing
    credentials included — marks the row `falhou` with the reason and bumps
    the attempt count; it NEVER reports success.
    """
    org_id = _org(auth)
    try:
        publicacao = repos.publicacao.buscar(org_id, publicacao_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if publicacao.get("status") == "publicada":
        raise HTTPException(status_code=409, detail="Publicação já enviada")

    canal = str(publicacao["canal"])
    pauta = repos.pauta.buscar(org_id, str(publicacao["pauta_id"]))
    pecas = repos.peca.da_pauta(org_id, str(pauta["id"]))
    publisher = get_publisher(canal, token=_token_do_canal(repos, org_id, canal))

    try:
        resultado = publisher.publicar(
            texto=str(pauta.get("copy_texto") or ""),
            midia_urls=[str(p["storage_key"]) for p in pecas],
        )
    except Exception as exc:  # noqa: BLE001 — every failure path is the same:
        # record it and NEVER report success. Distinguishing exception types
        # here would only change the log line, not the outcome.
        atualizado = repos.publicacao.marcar_falha(org_id, publicacao_id, str(exc))
        if isinstance(exc, PublisherNotConfigured):
            # Surface it on the integration too, so the setup screen can say
            # "reconectar" rather than leaving the operator to correlate.
            repos.integracao.registrar_erro(org_id, canal, str(exc))
        logger.warning("publicação falhou org=%s id=%s: %s", org_id, publicacao_id, exc)
        return PublicacaoOut(**atualizado)

    atualizado = repos.publicacao.marcar_publicada(
        org_id, publicacao_id,
        external_id=resultado.external_id, permalink=resultado.permalink,
    )
    logger.info("publicada org=%s id=%s external=%s", org_id, publicacao_id, resultado.external_id)
    return PublicacaoOut(**atualizado)


@router.post("/publicacoes/{publicacao_id}/cancelar", response_model=PublicacaoOut)
async def cancelar_publicacao(
    publicacao_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PublicacaoOut:
    """Cancel a scheduled publication.

    Cancelling frees the pauta+canal slot (the unique index excludes
    `cancelada`), so the piece can be rescheduled without deleting history.
    """
    org_id = _org(auth)
    try:
        atual = repos.publicacao.buscar(org_id, publicacao_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if atual.get("status") == "publicada":
        raise HTTPException(status_code=409, detail="Publicação já enviada não pode ser cancelada")
    return PublicacaoOut(**repos.publicacao.atualizar(org_id, publicacao_id, {"status": "cancelada"}))


@router.get("/fila", response_model=list[PublicacaoOut])
async def fila(
    ate: str | None = Query(default=None, description="ISO-8601; padrão = agora"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[PublicacaoOut]:
    """Scheduled publications already due — what a worker would pick up."""
    limite = ate or datetime.now(timezone.utc).isoformat()
    return [PublicacaoOut(**p) for p in repos.publicacao.pendentes(_org(auth), limite)]


# ── Métricas ────────────────────────────────────────────────────────
@router.post("/publicacoes/{publicacao_id}/metricas", response_model=MetricaOut,
             status_code=status.HTTP_201_CREATED)
async def registrar_metrica(
    publicacao_id: str,
    payload: MetricaIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> MetricaOut:
    """Append an engagement snapshot.

    Append, never overwrite: metrics move, and replacing them would destroy
    the only record of how a post performed over its first week.
    """
    org_id = _org(auth)
    try:
        repos.publicacao.buscar(org_id, publicacao_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    return MetricaOut(**repos.metrica.registrar(org_id, publicacao_id, **payload.model_dump()))


@router.get("/publicacoes/{publicacao_id}/metricas", response_model=list[MetricaOut])
async def listar_metricas(
    publicacao_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[MetricaOut]:
    """Snapshot history, newest first."""
    return [MetricaOut(**m) for m in repos.metrica.da_publicacao(_org(auth), publicacao_id)]


# ── BI de eficiência ────────────────────────────────────────────────
@router.get("/bi/eficiencia", response_model=list[EficienciaOut])
async def bi_eficiencia(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[EficienciaOut]:
    """Taxa de refação + custo real do job, per client.

    `alertas` is part of the contract, not decoration: hours logged by someone
    with no resolvable rate are counted and reported rather than silently
    treated as free, so a reader knows when the cost is understated.
    """
    linhas = BIService(repos).eficiencia_por_cliente(_org(auth))
    return [
        EficienciaOut(
            cliente_id=e.cliente_id,
            cliente_nome=e.cliente_nome,
            tarefas=e.tarefas,
            refacoes=e.refacoes,
            taxa_refacao=e.taxa_refacao,
            horas=e.horas,
            custo_reais=e.custo_reais,
            alertas=e.alertas,
        )
        for e in linhas
    ]

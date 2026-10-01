"""Distribuição e Métricas — Módulo 5.

  PUBLICAÇÃO  /api/distribuicao/publicacoes …   schedule, run, cancel
  MÉTRICAS    /api/distribuicao/metricas …      snapshot ingest + read
  BI          /api/distribuicao/bi/eficiencia   taxa de refação + custo real

**What is real today.** Scheduling, the queue, status transitions, retry
accounting, metric snapshots and the entire BI rollup are real and tested. The
outbound network calls are not: no channel has a homologated vendor
integration yet. A publish without a usable channel token REFUSES outright
(409 `canal_nao_configurado`/`credencial_ilegivel`) before any attempt — it is
never simulated. A publish WITH a token reaches the real adapter, which raises
`CanalNaoHomologado` (`NOC-REMEDIATE[igig-publishing]`). Either way, nothing is
ever marked `publicada` without a platform-confirmed id, because a post the
client never saw showing as published is the one outcome that destroys trust
in this module.

Metrics ingest is a POST rather than a scheduled pull for the same reason:
until the platform APIs are homologated there is nothing to pull from, and an
endpoint that accepts a snapshot lets the dashboard be built and verified now.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py for the slowapi/PEP 563 interaction.
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import RecordNotFound, UniqueViolation

from app.config import get_settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.distribuicao import (
    AgendarPublicacao,
    EditarPublicacao,
    EficienciaOut,
    MetricaIn,
    MetricaOut,
    PublicacaoOut,
)
from app.services.bi_service import BIService
from app.services.publicacao_publisher import (
    CanalNaoHomologado,
    CredencialIlegivel,
    PublisherNotConfigured,
    get_publisher,
    resolver_token,
)
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/distribuicao", tags=["distribuicao"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


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

    try:
        registro = repos.publicacao.agendar(
            org_id, payload.pauta_id, payload.canal, payload.agendada_para.isoformat()
        )
    except UniqueViolation:
        # `agendada_para` is now schema-validated (a real datetime, 422 on
        # anything else), so this is the partial unique index the message
        # below describes — catching the specific member rather than the
        # broader `PersistenceError` means a DIFFERENT constraint failure
        # here surfaces as a real 500, not a mislabelled 409.
        raise HTTPException(
            status_code=409,
            detail=f"Esta pauta já tem publicação ativa em {payload.canal}",
        )
    return PublicacaoOut(**registro)


@router.patch("/publicacoes/{publicacao_id}", response_model=PublicacaoOut)
async def editar_publicacao(
    publicacao_id: str,
    payload: EditarPublicacao,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PublicacaoOut:
    """Edit / reschedule a publication that is still `agendada`.

    The queue worker polls `agendada_para` (`PublicacaoRepository.pendentes`),
    so persisting the new value IS the reschedule — no job id to move. Any
    other status (publicando/publicada/falhou/cancelada) is a 409: the post is
    in flight or already decided. Same auth as POST; the same partial unique
    index guards a channel change onto a pauta+canal already scheduled.
    """
    org_id = _org(auth)
    try:
        atual = repos.publicacao.buscar(org_id, publicacao_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if atual.get("status") != "agendada":
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Só é possível editar publicações agendadas.",
                "code": "publicacao_nao_editavel",
            },
        )
    mudancas: dict[str, Any] = {}
    if payload.canal is not None:
        mudancas["canal"] = payload.canal
    if payload.agendada_para is not None:
        mudancas["agendada_para"] = payload.agendada_para.isoformat()
    try:
        registro = repos.publicacao.atualizar(org_id, publicacao_id, mudancas)
    except UniqueViolation:
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
    cfg: Any = Depends(get_settings),
) -> PublicacaoOut:
    """Publish now.

    Success requires a platform-confirmed `external_id`. A missing/unusable
    credential REFUSES with a 409 before any attempt is made — never a Fake,
    never a `falhou` row (see `publicacao_publisher`'s module docstring for
    why the earlier "fall back to a simulated publish" behaviour was wrong).
    Any OTHER failure — including the real vendor call not being homologated
    yet — marks the row `falhou` with the reason and bumps the attempt count;
    it NEVER reports success.
    """
    org_id = _org(auth)
    try:
        publicacao = repos.publicacao.buscar(org_id, publicacao_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    status_atual = publicacao.get("status")
    if status_atual == "publicada":
        raise HTTPException(status_code=409, detail="Publicação já enviada")
    if status_atual == "cancelada":
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Publicação cancelada não pode ser executada.",
                "code": "publicacao_cancelada",
            },
        )
    if status_atual == "publicando":
        # The in-flight claim — see `publicacao_publisher.processar_fila_publicacao`'s
        # docstring. Closes the other half of finding #6: two overlapping
        # `executar` calls (a double-tap, or the queue worker racing a manual
        # click) must not both reach the publisher for the same row.
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Esta publicação já está sendo executada.",
                "code": "publicacao_em_andamento",
            },
        )

    canal = str(publicacao["canal"])
    try:
        token = resolver_token(repos, org_id, canal, cfg)
    except CredencialIlegivel as exc:
        repos.integracao.registrar_erro(org_id, canal, str(exc))
        raise HTTPException(
            status_code=409,
            detail={"detail": str(exc), "code": "credencial_ilegivel"},
        ) from exc
    if not token:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": (
                    f"Canal {canal} não está configurado. Conecte um token em "
                    "Integrações antes de publicar."
                ),
                "code": "canal_nao_configurado",
            },
        )

    pauta = repos.pauta.buscar(org_id, str(publicacao["pauta_id"]))
    pecas = repos.peca.da_pauta(org_id, str(pauta["id"]))

    # Claim the row right before the actual attempt — a credential refusal
    # above never touches the row's status, so a retry after fixing the
    # credential still finds it `agendada`/`falhou`, not stuck `publicando`.
    repos.publicacao.atualizar(org_id, publicacao_id, {"status": "publicando"})

    try:
        resultado = get_publisher(canal, token=token).publicar(
            texto=str(pauta.get("copy_texto") or ""),
            midia_urls=[str(p["storage_key"]) for p in pecas],
        )
    except CanalNaoHomologado as exc:
        # A pending vendor homologation is NOT a credential problem — never
        # stamp `ultimo_erro`, or the setup screen tells the operator to
        # reconnect something that reconnecting cannot fix.
        atualizado = repos.publicacao.marcar_falha(org_id, publicacao_id, str(exc))
        logger.warning(
            "publicação não homologada org=%s id=%s: %s", org_id, publicacao_id, exc
        )
        return PublicacaoOut(**atualizado)
    except PublisherNotConfigured as exc:
        atualizado = repos.publicacao.marcar_falha(org_id, publicacao_id, str(exc))
        # Surface it on the integration too, so the setup screen can say
        # "reconectar" rather than leaving the operator to correlate.
        repos.integracao.registrar_erro(org_id, canal, str(exc))
        logger.warning(
            "publicação falhou (credencial) org=%s id=%s: %s", org_id, publicacao_id, exc
        )
        return PublicacaoOut(**atualizado)
    except Exception as exc:  # noqa: BLE001 — every other failure path is the
        # same: record it and NEVER report success.
        atualizado = repos.publicacao.marcar_falha(org_id, publicacao_id, str(exc))
        logger.warning("publicação falhou org=%s id=%s: %s", org_id, publicacao_id, exc)
        return PublicacaoOut(**atualizado)

    atualizado = repos.publicacao.marcar_publicada(
        org_id, publicacao_id,
        external_id=resultado.external_id, permalink=resultado.permalink,
    )
    # The pauta's own publish date — documented as existing, never written
    # (finding #10, 2026-09 audit).
    repos.pauta.atualizar(
        org_id, str(pauta["id"]), {"publicado_em": datetime.now(timezone.utc).isoformat()}
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
    status_atual = atual.get("status")
    if status_atual == "publicada":
        raise HTTPException(status_code=409, detail="Publicação já enviada não pode ser cancelada")
    if status_atual == "cancelada":
        return PublicacaoOut(**atual)
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

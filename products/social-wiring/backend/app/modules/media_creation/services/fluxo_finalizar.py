"""The chat saga's two queue jobs (``specs/estruturas-contract.md`` 9.3 and 16.6 step 4).

* ``fluxo.finalizar_card`` -- reads the roteiro: ``completo`` -> the roteiro goes up for approval (S3 A1, idempotent),
  the card's caption is produced (``LegendaService.gerar``: format-aware; a ``post`` takes its own ``### Legenda``) and
  saved to ``cs_posts.legenda`` **only while it is NULL** (a user's edit is never overwritten) -> ``roteiro_gerado``,
  ``legenda_gerada`` (``codigo`` = sha256 of the saved text) | ``legenda_falhou`` (the code), ``fluxo_concluido``.
  ``falha`` -> ``roteiro_falhou`` + ``fluxo_concluido``. ``criando|processando|perguntas`` -> reschedule in ~10 s
  (jittered, no retry spent) until 15 min after the job was enqueued, then ``roteiro_falhou`` ``codigo='demorou'``.
  Polling budget: <= 200 flows/day x <= 90 ticks x 1 indexed read, only while a flow is active (no idle poller).
* ``fluxo.headline_do_roteiro`` -- ONE model call (``prompts/headline_do_roteiro.py``) -> the headline validator; an
  invalid output gets ONE retry, then ``headline_falhou`` + ``fluxo_etapa='falhou'`` / ``headline_invalida`` (the roteiro
  stays, no card). A valid one is saved by ``cs_chat_proposta_salvar_headline(..., p_texto)`` and the job runs steps 5-7
  (:meth:`SagaFluxo.concluir`). Metered on the org's LLM budget (``chat_completion`` with the org id).

Both are lookup-first and idempotent: a re-run after a crash resumes from the recorded state.
"""
from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.approvals import ApprovalService
from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.llm import LLMBudgetExceeded, LLMNotConfigured

from app.modules.media_creation.prompts.headline_do_roteiro import build_headline_do_roteiro
from app.modules.media_creation.saida_ia import validar_headline as validar_headline_saida
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.fluxo_continuacao import JOB_FINALIZAR, JOB_HEADLINE, SagaFluxo
from app.modules.media_creation.services.legenda_service import (
    LegendaError,
    LegendaService,
    check_ia_configurada as legenda_ia_check,
    get_legenda_llm,
)
from app.modules.media_creation.services.roteiro_aprovacao import NOTA_GERADO, SUBJECT_KIND, make_approvals
from app.modules.media_creation.services.roteiro_service import make_chat_roteiro_llm

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ESTRUTURAS = "cs_estruturas"
MARCA_PERFIL = "cs_marca_perfil"
BRAINS = "cs_brains"
SALVAR_HEADLINE_RPC = "cs_chat_proposta_salvar_headline"

#: The finalizer's deadline after the job was enqueued (contract: 90 ticks x 10 s ~ 15 min).
PRAZO_FINALIZADOR = timedelta(minutes=15)
TICK_S = 10.0
TICK_JITTER_S = 3.0
PENDENTES = ("criando", "perguntas", "processando")
TENTATIVAS_HEADLINE = 2  # the call + ONE retry on an invalid output
MAX_CEREBROS = 5

Llm = Callable[[str, str, Optional[str]], Awaitable[str]]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def validar_headline(texto: Any) -> Optional[str]:
    """The single-headline validator (``saida_ia.validar_headline``: one derivation with the chat proposals' guard)."""
    return validar_headline_saida(texto)


def _ultima_tentativa(job: Job) -> bool:
    return int(job.retry_count) >= int(job.max_retries)


def _saga_do_job(
    job: Job, db: Any, jobs: Optional[JobRepository], approvals: Optional[ApprovalService] = None,
) -> tuple[SagaFluxo, dict[str, Any]]:
    payload = job.payload or {}
    pid, org_id = str(payload.get("proposta_id") or ""), str(payload.get("org_id") or "")
    if not pid or not org_id:
        raise DeadLetterError(f"{job.type}: payload sem proposta_id/org_id")
    proposta = SagaFluxo(db, org_id, "", jobs=jobs).proposta(pid)
    if proposta is None:
        raise DeadLetterError(f"{job.type}: proposta {pid} não existe")
    user = str(proposta.get("escolhida_por") or "")
    if not user:
        raise DeadLetterError(f"{job.type}: proposta {pid} sem escolhida_por")
    return SagaFluxo(db, org_id, user, jobs=jobs, approvals=approvals), proposta


# ── fluxo.finalizar_card ───────────────────────────────────────────────────────────────────────────────


def _submeter(approvals: ApprovalService, org_id: str, roteiro: dict[str, Any]) -> None:
    """S3 A1: the completo roteiro is pending approval (idempotent submit). Never decides approval; a lost submit is
    healed by the idempotent submit every approval call performs, so it is logged at error, never fatal."""
    try:
        approvals.submit(org_id, SUBJECT_KIND, str(roteiro["id"]), int(roteiro.get("versao") or 1), actor_id=None,
                         note=NOTA_GERADO)
    except Exception:  # noqa: BLE001 - healed by the next approval call (see docstring)
        logger.exception("fluxo: falha ao submeter o roteiro %s para aprovação", roteiro.get("id"))


async def executar_finalizar(
    job: Job, *, db: Any, llm: Llm, cfg: Any = None,
    ia_check: Callable[[Optional[str]], None] = legenda_ia_check,
    orcamento: Callable[[Optional[str]], Awaitable[None]] = geracao_jobs.assert_orcamento_ia,
    approvals: Optional[ApprovalService] = None, agora: Callable[[], datetime] = _agora,
) -> None:
    if cfg is None:
        from app.config import settings as cfg
    saga, proposta = _saga_do_job(job, db, None, approvals)
    pid = str(proposta["id"])
    if proposta.get("fluxo_etapa") == "concluido":
        return
    roteiro = saga.roteiro_do_fluxo(proposta)
    post_id = saga.post_do_roteiro(str(roteiro["id"])) if roteiro else None
    if roteiro is None or post_id is None:
        raise DeadLetterError(f"fluxo.finalizar_card: proposta {pid} sem roteiro/card")
    status = roteiro.get("status")
    if status in PENDENTES:
        if agora() - job.created_at > PRAZO_FINALIZADOR:
            saga.registrar(pid, "roteiro_falhou", etapa="falhou", erro="demorou", roteiro=str(roteiro["id"]), codigo="demorou")
            return
        raise RescheduleLater(TICK_S + random.uniform(0, TICK_JITTER_S), "roteiro ainda em geração")
    if status != "completo":
        saga.registrar(pid, "roteiro_falhou", etapa="falhou", erro="roteiro_falhou", roteiro=str(roteiro["id"]), codigo="falha")
        saga.registrar(pid, "fluxo_concluido", codigo="roteiro_falhou")
        return

    _submeter(approvals or make_approvals(db), saga.org_id, roteiro)
    saga.registrar(pid, "roteiro_gerado", roteiro=str(roteiro["id"]), post=post_id)
    card = db.table(POSTS).select("id,legenda").eq("id", post_id).eq("org_id", saga.org_id).execute().data or []
    if card and not (card[0].get("legenda") or "").strip():
        servico = LegendaService(db, saga.org_id, saga.user_id, cfg=cfg, llm=llm, ia_check=ia_check, orcamento=orcamento)
        try:
            legenda = (await servico.gerar(post_id))["legenda"]
        except LegendaError as exc:
            codigo = str(exc.detail.get("code")) if isinstance(exc.detail, dict) and exc.detail.get("code") else f"legenda_{exc.status}"
            logger.warning("fluxo %s: legenda falhou (%s)", pid, codigo)
            saga.registrar(pid, "legenda_falhou", post=post_id, codigo=codigo)
        else:
            salvos = (
                db.table(POSTS).update({"legenda": legenda}).eq("id", post_id).eq("org_id", saga.org_id)
                .is_("legenda", "null").execute().data
            )
            if salvos:
                saga.registrar(pid, "legenda_gerada", post=post_id, codigo=_sha256(legenda))
            else:
                logger.info("fluxo %s: legenda escrita pelo usuário enquanto gerávamos; mantida", pid)
    saga.registrar(pid, "fluxo_concluido", etapa="concluido", roteiro=str(roteiro["id"]), post=post_id)


# ── fluxo.headline_do_roteiro ──────────────────────────────────────────────────────────────────────────


def _material(db: Any, saga: SagaFluxo, proposta: dict[str, Any]) -> tuple[Optional[str], Optional[str], list[str]]:
    """The principal Estrutura's ``formula_headline``, the brand profile and its cérebros (all fenced by the prompt)."""
    formula = None
    citadas = saga.estruturas_citadas(str(proposta["id"]))
    if citadas:
        rows = db.table(ESTRUTURAS).select("formula_headline").eq("id", citadas[0]).execute().data or []
        formula = rows[0].get("formula_headline") if rows else None
    marca = str(proposta["marca_id"])
    perfil_rows = db.table(MARCA_PERFIL).select("bio").eq("marca_id", marca).eq("org_id", saga.org_id).execute().data or []
    perfil = perfil_rows[0].get("bio") if perfil_rows else None
    cerebros = [
        r.get("content") or ""
        for r in db.table(BRAINS).select("content").eq("org_id", saga.org_id).eq("marca_id", marca)
        .order("updated_at", desc=True).limit(MAX_CEREBROS).execute().data or []
    ]
    return formula, perfil, cerebros


async def executar_headline(
    job: Job, *, db: Any, llm: Llm, jobs: Optional[JobRepository], approvals: Optional[ApprovalService] = None,
) -> None:
    saga, proposta = _saga_do_job(job, db, jobs, approvals)
    pid = str(proposta["id"])
    if proposta.get("fluxo_etapa") == "concluido":
        return
    roteiro = saga.roteiro_do_fluxo(proposta)
    if roteiro is None:
        raise DeadLetterError(f"fluxo.headline_do_roteiro: proposta {pid} sem roteiro salvo")
    if not proposta.get("headline_id"):
        formula, perfil, cerebros = _material(db, saga, proposta)
        system, user = build_headline_do_roteiro(roteiro.get("conteudo") or "", formula, perfil, cerebros)
        texto: Optional[str] = None
        for tentativa in range(TENTATIVAS_HEADLINE):
            try:
                reply = await llm(system, user, saga.org_id)
            except LLMNotConfigured:
                saga.registrar(pid, "headline_falhou", etapa="falhou", erro="ia_nao_configurada", codigo="ia_nao_configurada")
                return
            except LLMBudgetExceeded:
                saga.registrar(pid, "headline_falhou", etapa="falhou", erro="orcamento_ia_excedido", codigo="orcamento_ia_excedido")
                return
            except Exception as exc:  # noqa: BLE001 - provider failure: the job retries; on its last attempt it settles
                logger.error("fluxo %s: headline do roteiro falhou (%s: %s)", pid, type(exc).__name__, exc)
                if _ultima_tentativa(job):
                    saga.registrar(pid, "headline_falhou", etapa="falhou", erro="ia_falhou", codigo="ia_falhou")
                    return
                raise
            texto = validar_headline(reply)
            if texto is not None:
                break
            logger.warning("fluxo %s: headline inválida (tentativa %d)", pid, tentativa + 1)
        if texto is None:
            saga.registrar(pid, "headline_falhou", etapa="falhou", erro="headline_invalida", codigo="headline_invalida")
            return
        db.rpc(SALVAR_HEADLINE_RPC, {"p_proposta": pid, "p_org": saga.org_id, "p_user": saga.user_id, "p_texto": texto}).execute()
        proposta = saga.proposta(pid)
        if proposta is None or not proposta.get("headline_id"):
            raise RuntimeError(f"fluxo {pid}: headline salva não encontrada")
    await saga.concluir(proposta, roteiro)


# ── registration ───────────────────────────────────────────────────────────────────────────────────────


def _admin_db():
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client()


async def _handle_finalizar(job: Job) -> None:
    await executar_finalizar(job, db=_admin_db(), llm=get_legenda_llm())


async def _handle_headline(job: Job) -> None:
    db = _admin_db()
    await executar_headline(job, db=db, llm=make_chat_roteiro_llm(max_tokens=256), jobs=geracao_jobs.make_jobs_repository(db))


def register() -> None:
    """Both handlers on the ``geracao`` worker (through the module startup hook). Idempotent."""
    geracao_jobs.register_handler(JOB_FINALIZAR, _handle_finalizar)
    geracao_jobs.register_handler(JOB_HEADLINE, _handle_headline)


__all__ = [
    "PRAZO_FINALIZADOR", "executar_finalizar", "executar_headline", "register", "validar_headline",
]

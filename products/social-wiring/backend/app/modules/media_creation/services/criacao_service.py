"""Criação entry points (criacao-pipeline-contract.md sections 1, 3, 5): enqueue a post's media job graph, re-run a failed /
rejected step, and read a graph's progress.

* :func:`enfileirar` is THE one place that queues a post's media (S5's "enter Criação" route, the manual
  ``POST /esteira/posts/{id}/criacao`` and the post-rejection re-run all come through it): it moves the card into Criação
  and queues it through S5's :class:`CriacaoMover` (gate, history, sub-state + event, live stream), then registers the
  graph in the ledger and enqueues the seed jobs. Idempotent: a post whose graph is already running returns it, never a
  second graph. It never produces anything itself: the separate ``worker criacao`` process (:mod:`criacao_worker`) does.
* A graph's inputs and quota estimates are persisted in its job payloads (seed runner), so a restarted worker resumes.
* Re-running a step also re-runs its downstream steps in a NEW rodada (a re-rendered video must be re-measured and
  re-registered); upstream outputs are read from the ledger's latest concluded rows, nothing upstream is paid twice.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal
from typing import Any, Optional

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.domain.media_production import GraphSpec, MediaGraphRunner, PassoRow, StepSpec
from noctusai_lib.domain.media_production.types import CANCELADO, CONCLUIDO, EXECUTANDO, FALHOU, PENDENTE
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.tts import TtsError
from noctusai_lib.realtime import JobProgress, RealtimeBus, get_shared_realtime_bus

from app.modules.media_creation import criacao_estado as est
from app.modules.media_creation.criacao_handlers import CriacaoDeps, build_handlers, montar_entradas
from app.modules.media_creation.criacao_passos import (
    PASSO_TTS,
    PASSOS,
    ROTA_NAO_IMPLEMENTADA,
    SEM_ROTA,
    implementada,
    specs_da_rota,
)
from app.modules.media_creation.criacao_ports import (
    CRIACAO_USD_POR_CREDITO_TETO,
    ProgressoComposto,
    SistemaMover,
    SupabaseLedger,
    SupabaseQuota,
    VozConsentimento,
)
from app.modules.media_creation.criacao_rotas import Rota, resolver_rota, rota_da_chave
from app.modules.media_creation.services.criacao_mover import CriacaoMover
from app.modules.media_creation.services.geracao_jobs import make_jobs_repository

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ROTEIROS = "cs_roteiros"
PASSO_PADRAO_REPROVA = "render_motion"


class CriacaoError(Exception):
    """A coded refusal (``{"code", "detail"}`` body)."""

    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


def progress_bus() -> RealtimeBus:
    from app.config import settings

    return get_shared_realtime_bus(settings.redis_url, label="Criação job-progress")


def make_runner(db: Any, jobs: JobRepository, bus: RealtimeBus, deps: CriacaoDeps, *, max_retries: int = 2,
                mover_factory: Optional[Any] = None) -> MediaGraphRunner:
    """The seed runner wired to the SW ports. The API builds one with throwaway deps (it only enqueues); the worker
    process builds one with real handlers."""
    mover_factory = mover_factory or (lambda org: CriacaoMover(db, org, bus=bus))
    mover = SistemaMover(db, bus, mover_factory)
    return MediaGraphRunner(
        jobs=jobs, ledger=SupabaseLedger(db, on_inicio=mover.iniciar), progress=ProgressoComposto(bus, mover_factory),
        quota=SupabaseQuota(db), mover=mover, registry=build_handlers(deps), max_retries=max_retries,
    )


def default_deps(db: Any, *, storage: Optional[StorageBackend] = None) -> CriacaoDeps:
    """Production wiring: org TTS key via the credential chain, the real renderer, the post-media bucket."""
    from pathlib import Path

    from noctusai_lib.integrations.motion_render import make_motion_renderer
    from noctusai_lib.integrations.tts import make_tts_client

    from app.config import settings
    from app.modules.certidoes.deps import storage_for

    consent = VozConsentimento(db)
    workdir = Path(settings.criacao_workdir)

    def make_tts(org_id: str, marca_id: str, out_dir: Path):
        return make_tts_client(out_dir=out_dir, org_id=org_id, consent=consent.checker(marca_id))

    return CriacaoDeps(
        db=db, storage=storage or storage_for(db), consent=consent, make_tts=make_tts,
        renderer=make_motion_renderer(), workdir=workdir,
    )


@dataclass
class _Alvo:
    post: dict
    rota: Rota
    conteudo: str


class CriacaoService:
    def __init__(
        self, db: Any, runner: MediaGraphRunner, deps: CriacaoDeps, bus: RealtimeBus,
        *, usd_por_credito: Optional[Decimal] = None, mover_factory: Optional[Any] = None,
    ) -> None:
        self._db, self._runner, self._deps, self._bus = db, runner, deps, bus
        self._mover_factory = mover_factory or (lambda org: CriacaoMover(db, org, bus=bus))
        self._ledger = SupabaseLedger(db)
        self._usd_por_credito = usd_por_credito

    # ── enqueue ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def _alvo(self, post_id: str, org_id: Optional[str]) -> _Alvo:
        q = self._db.table(POSTS).select(
            "id,org_id,marca_id,formato,criacao_rota,roteiro_id,criacao_estado,etapa_id"
        ).eq("id", post_id)
        if org_id:
            q = q.eq("org_id", org_id)
        rows = q.execute().data
        if not rows:
            raise CriacaoError(404, "post_nao_encontrado", "Post não encontrado")
        post = rows[0]
        rota = rota_da_chave(post.get("criacao_rota")) or resolver_rota(post.get("formato"))
        if rota is None:
            raise CriacaoError(422, SEM_ROTA, "Este formato não tem rota automática de criação.")
        if not implementada(rota):
            raise CriacaoError(
                409, ROTA_NAO_IMPLEMENTADA,
                f"A rota {rota.chave} ainda não está disponível — por enquanto só o reel narrado é produzido automaticamente.",
            )
        return _Alvo(post, rota, "")

    def _conteudo(self, post: dict) -> str:
        """The roteiro's text. Read AFTER the Criação gate (approved headline + roteiro) has answered."""
        if not post.get("roteiro_id"):
            raise CriacaoError(409, "roteiro_ausente", "O post não tem roteiro para produzir.")
        rt = (
            self._db.table(ROTEIROS).select("conteudo,status").eq("id", post["roteiro_id"])
            .eq("org_id", post["org_id"]).execute().data
        )
        if not rt or rt[0].get("status") != "completo" or not (rt[0].get("conteudo") or "").strip():
            raise CriacaoError(409, "roteiro_incompleto", "O roteiro do post ainda não está completo.")
        return rt[0]["conteudo"]

    def _estimar_tts(self, org_id: str, marca_id: str, texto: str, modelo: str) -> Decimal:
        """Pre-flight USD of the TTS leg (zero spend). The vendor's own max-credits estimate x the org's price per
        credit, or the conservative ceiling when no price is configured."""
        from pathlib import Path

        try:
            client = self._deps.make_tts(org_id, marca_id, Path(self._deps.workdir))
            creditos = client.estimate(texto, modelo)
        except TtsError as exc:
            raise CriacaoError(503, exc.codigo, "A síntese de voz não está disponível para esta organização.") from exc
        creditos = Decimal(str(creditos if creditos is not None else len(texto)))
        preco = self._usd_por_credito or CRIACAO_USD_POR_CREDITO_TETO
        return (creditos * preco).quantize(Decimal("0.0001"), rounding=ROUND_UP)

    async def _entrar_em_criacao(self, alvo: _Alvo, org: str) -> None:
        """Card -> Criação + sub-state ``na_fila`` through the system mover (gate: approved headline AND roteiro)."""
        if alvo.post.get("criacao_estado") == est.NA_FILA:
            return
        await asyncio.to_thread(self._mover_factory(org).entrar_em_criacao, str(alvo.post["id"]))

    async def enfileirar(
        self, post_id: str, *, org_id: Optional[str] = None, ator_id: Optional[str] = None, passo: Optional[str] = None,
    ) -> dict:
        """Queue the whole route of ``post_id`` as the next rodada (``passo`` given: only that step + its downstream).

        Idempotent: while a graph of the post is running it is returned (``ja_em_andamento``), never doubled."""
        alvo = await asyncio.to_thread(self._alvo, post_id, org_id)
        org = str(alvo.post["org_id"])
        rows = await self._ledger.carregar(org, post_id)
        ativa = self._rodada_ativa(rows)
        if ativa is not None:
            return {**self._resposta(alvo.rota, post_id, ativa, [r.passo for r in rows if r.rodada == ativa]), "ja_em_andamento": True}
        ultima = max((r.rodada for r in rows), default=0)
        if passo is not None:
            if passo not in alvo.rota.passos:
                raise CriacaoError(422, "passo_desconhecido", f"A rota {alvo.rota.chave} não tem o passo {passo}.")
            falhou = any(r.status == FALHOU and r.rodada == ultima for r in rows)
            if not (falhou or alvo.post.get("criacao_estado") in (est.FALHOU, est.NA_FILA)):
                raise CriacaoError(409, "reexecucao_indevida", "Só é possível refazer um passo que falhou ou foi reprovado.")
        await self._entrar_em_criacao(alvo, org)  # the Criação gate (approved headline + roteiro) answers FIRST
        alvo.conteudo = await asyncio.to_thread(self._conteudo, alvo.post)
        entradas, estimativas = await self._preparar(alvo, org)
        specs = list(specs_da_rota(alvo.rota, entradas, estimativas))
        if passo is not None:
            specs = self._parcial(specs, passo, rows)
        graph = GraphSpec(org, post_id, tuple(specs), ultima + 1)
        await self._runner.enqueue_graph(graph)
        await ProgressoComposto(self._bus).publicar(org, post_id, graph.rodada, "na_fila", 0.0, "Na fila de criação", False)
        return self._resposta(alvo.rota, post_id, graph.rodada, [s.passo for s in specs])

    async def reexecutar(self, post_id: str, passo: str, *, org_id: Optional[str] = None, ator_id: Optional[str] = None) -> dict:
        """Re-run ``passo`` and everything downstream of it as a new rodada (only a failed / rejected post)."""
        return await self.enfileirar(post_id, org_id=org_id, ator_id=ator_id, passo=passo)

    @staticmethod
    def _parcial(specs: list[StepSpec], passo: str, rows: list[PassoRow]) -> list[StepSpec]:
        """The target + everything downstream; the outputs of the steps left out are inlined from the ledger."""
        ordem = [s.passo for s in specs]
        refazer = set(ordem[ordem.index(passo):])
        ultimo: dict[str, Any] = {}
        for r in sorted(rows, key=lambda r: r.rodada):
            if r.status == CONCLUIDO:
                ultimo[r.passo] = r.resultado
        out: list[StepSpec] = []
        for s in specs:
            if s.passo not in refazer:
                continue
            ent = dict(s.entradas)
            for d in s.depende_de:
                if d not in refazer:
                    ent[d] = ultimo.get(d)  # not part of this partial graph: its latest output is the input
            out.append(StepSpec(s.passo, s.rotulo, tuple(d for d in s.depende_de if d in refazer), s.peso, s.estimativa_usd, ent))
        return out

    @staticmethod
    def _rodada_ativa(rows: list[PassoRow]) -> Optional[int]:
        if not rows:
            return None
        ultima = max(r.rodada for r in rows)
        if any(r.rodada == ultima and r.status in (PENDENTE, EXECUTANDO) for r in rows):
            return ultima
        return None

    async def _preparar(self, alvo: _Alvo, org: str) -> tuple[dict, dict]:
        entradas = await asyncio.to_thread(
            lambda: montar_entradas(
                marca_id=str(alvo.post["marca_id"]), conteudo=alvo.conteudo, usd_por_credito=self._usd_por_credito
            )
        )
        e = entradas[PASSO_TTS]
        est_usd = await asyncio.to_thread(self._estimar_tts, org, str(alvo.post["marca_id"]), e["texto"], e["modelo"])
        return entradas, {PASSO_TTS: est_usd}

    @staticmethod
    def _resposta(rota: Rota, post_id: str, rodada: int, passos: list[str]) -> dict:
        return {
            "post_id": post_id, "rota": rota.chave, "rodada": rodada, "passos": passos,
            "progresso_id": f"{post_id}:{rodada}",
        }

    # ── progress snapshot (the SSE stream's first frame; the ledger is the truth) ──────────────────────────────────

    async def snapshot(self, org_id: str, post_id: str, rodada: Optional[int]) -> Optional[JobProgress]:
        """``rodada=None`` = the latest one (the per-post stream)."""
        todas = await self._ledger.carregar(org_id, post_id)
        if rodada is None and todas:
            rodada = max(r.rodada for r in todas)
        rows = [r for r in todas if r.rodada == rodada]
        if not rows:
            return None
        return progresso_das_linhas(rows, pesos=None)


def progresso_das_linhas(rows: list[PassoRow], *, pesos: Optional[dict[str, float]]) -> JobProgress:
    """The wire shape of one rodada. Weighted by the step's expected duration when known, else equal."""
    if pesos is None:
        pesos = {r.passo: PASSOS[r.passo].peso if r.passo in PASSOS else 1.0 for r in rows}
    total = sum(pesos.get(r.passo, 1.0) for r in rows) or 1.0
    feito = sum(pesos.get(r.passo, 1.0) for r in rows if r.status == CONCLUIDO)
    falhou = next((r for r in rows if r.status == FALHOU), None)
    if falhou is not None:
        return JobProgress("falhou", feito / total, falhou.passo, f"Falhou: {falhou.passo} ({falhou.erro_codigo})", True)
    if all(r.status == CONCLUIDO for r in rows):
        return JobProgress("concluido", 1.0, "concluido", "Criação concluída", True)
    if all(r.status in (CANCELADO, CONCLUIDO) for r in rows):
        return JobProgress("cancelado", feito / total, None, "Criação cancelada", True)
    atual = next((r for r in rows if r.status == EXECUTANDO), None)
    return JobProgress(
        "executando" if atual else "na_fila", feito / total, atual.passo if atual else "na_fila",
        None if atual else "Na fila de criação", False,
    )


# ── module-level convenience (S5 trigger / routes) ──────────────────────────────────────────────────────────────────────


def build_service(db: Any, *, jobs: Optional[JobRepository] = None, bus: Optional[RealtimeBus] = None,
                  deps: Optional[CriacaoDeps] = None) -> CriacaoService:
    from app.config import settings

    jobs = jobs or make_jobs_repository(db)
    bus = bus or progress_bus()
    deps = deps or default_deps(db)
    preco = settings.criacao_usd_por_credito_elevenlabs
    runner = make_runner(db, jobs, bus, deps)
    return CriacaoService(db, runner, deps, bus, usd_por_credito=None if preco is None else Decimal(str(preco)))


async def enfileirar(post_id: str, *, org_id: Optional[str] = None, ator_id: Optional[str] = None, db: Any = None,
                     service: Optional[CriacaoService] = None) -> dict:
    """INTERNAL entry: queue the post's media job graph (the S5 route and the manual POST call this)."""
    if service is None:
        from app.dependencies import get_admin_client

        service = build_service(db or get_admin_client())
    return await service.enfileirar(post_id, org_id=org_id, ator_id=ator_id)


__all__ = [
    "CriacaoError", "CriacaoService", "build_service", "default_deps", "enfileirar", "make_runner",
    "progress_bus", "progresso_das_linhas",
]

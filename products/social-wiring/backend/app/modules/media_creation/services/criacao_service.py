"""Criação entry points (criacao-pipeline-contract.md sections 1, 3, 5): enqueue a post's media job graph, re-run a failed /
rejected step, and read a graph's progress.

* :func:`enfileirar` is the INTERNAL function the S5 trigger calls when the card enters Criação (and what the manual
  ``POST /esteira/posts/{id}/criacao`` calls). It never produces anything itself: it validates, registers the graph in the
  ledger, writes the ``na_fila`` projection + ``criacao_enfileirada`` event in one transaction, and enqueues the seed jobs.
  The separate ``worker criacao`` process (:mod:`criacao_worker`) executes them.
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
from noctusai_lib.domain.media_production import (
    BusProgress,
    GraphSpec,
    MediaGraphRunner,
    PassoRow,
    StepSpec,
)
from noctusai_lib.domain.media_production.types import CANCELADO, CONCLUIDO, EXECUTANDO, FALHOU, PENDENTE
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.tts import TtsError
from noctusai_lib.realtime import JobProgress, RealtimeBus, get_shared_realtime_bus

from app.modules.media_creation.criacao_handlers import CriacaoDeps, build_handlers, montar_entradas
from app.modules.media_creation.criacao_ports import (
    CRIACAO_USD_POR_CREDITO_TETO,
    ESTADO_NA_FILA,
    SupabaseLedger,
    SupabaseMover,
    SupabaseQuota,
    VozConsentimento,
)
from app.modules.media_creation.criacao_rotas import PASSO_TTS, Rota, RotaError, resolver_rota
from app.modules.media_creation.services.geracao_jobs import make_jobs_repository

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ROTEIROS = "cs_roteiros"

EVENTO_ENFILEIRADA = "criacao_enfileirada"


class CriacaoError(Exception):
    """A coded refusal (``{"code", "detail"}`` body)."""

    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


def _rota_error(exc: RotaError) -> CriacaoError:
    return CriacaoError(exc.status, exc.codigo, exc.detail)


def progress_bus() -> RealtimeBus:
    from app.config import settings

    return get_shared_realtime_bus(settings.redis_url, label="Criação job-progress")


def make_runner(db: Any, jobs: JobRepository, bus: RealtimeBus, deps: CriacaoDeps, *, max_retries: int = 2) -> MediaGraphRunner:
    """The seed runner wired to the SW ports. The API builds one with throwaway deps (it only enqueues); the worker
    process builds one with real handlers."""
    return MediaGraphRunner(
        jobs=jobs, ledger=SupabaseLedger(db), progress=BusProgress(bus), quota=SupabaseQuota(db),
        mover=SupabaseMover(db), registry=build_handlers(deps), max_retries=max_retries,
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
        *, usd_por_credito: Optional[Decimal] = None,
    ) -> None:
        self._db, self._runner, self._deps, self._bus = db, runner, deps, bus
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
        try:
            rota = resolver_rota(post.get("formato") or "reel", post.get("criacao_rota"))
        except RotaError as exc:
            raise _rota_error(exc) from exc
        if not post.get("roteiro_id"):
            raise CriacaoError(409, "roteiro_ausente", "O post não tem roteiro para produzir.")
        rt = (
            self._db.table(ROTEIROS).select("conteudo,status").eq("id", post["roteiro_id"])
            .eq("org_id", post["org_id"]).execute().data
        )
        if not rt or rt[0].get("status") != "completo" or not (rt[0].get("conteudo") or "").strip():
            raise CriacaoError(409, "roteiro_incompleto", "O roteiro do post ainda não está completo.")
        return _Alvo(post, rota, rt[0]["conteudo"])

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

    async def _rodadas(self, org_id: str, post_id: str) -> list[PassoRow]:
        return await self._ledger.carregar(org_id, post_id)

    async def enfileirar(self, post_id: str, *, org_id: Optional[str] = None, ator_id: Optional[str] = None) -> dict:
        """Queue the whole route of ``post_id`` as the next rodada. 409 while a graph of the post is still running."""
        alvo = await asyncio.to_thread(self._alvo, post_id, org_id)
        org = str(alvo.post["org_id"])
        rows = await self._rodadas(org, post_id)
        self._recusar_se_ativo(rows)
        rodada = max((r.rodada for r in rows), default=0) + 1
        entradas, estimativas = await self._preparar(alvo, org)
        graph = GraphSpec(org, post_id, alvo.rota.specs(entradas, estimativas), rodada)
        await self._projetar_fila(org, post_id, alvo.rota, rodada, None, ator_id)
        await self._runner.enqueue_graph(graph)
        await self._publicar_fila(org, post_id, rodada)
        return self._resposta(alvo.rota, post_id, rodada, [p.passo for p in graph.passos])

    async def reexecutar(self, post_id: str, passo: str, *, org_id: Optional[str] = None, ator_id: Optional[str] = None) -> dict:
        """Re-run ``passo`` and everything downstream of it as a new rodada (only a failed / rejected post)."""
        alvo = await asyncio.to_thread(self._alvo, post_id, org_id)
        org = str(alvo.post["org_id"])
        defs = {p.passo: p for p in alvo.rota.passos}
        if passo not in defs:
            raise CriacaoError(422, "passo_desconhecido", f"A rota {alvo.rota.chave} não tem o passo {passo}.")
        rows = await self._rodadas(org, post_id)
        self._recusar_se_ativo(rows)
        ultima = max((r.rodada for r in rows), default=0)
        falhou = any(r.status == FALHOU and r.rodada == ultima for r in rows)
        if not (falhou or alvo.post.get("criacao_estado") in ("falhou", "midia_reprovada")):
            raise CriacaoError(409, "reexecucao_indevida", "Só é possível refazer um passo que falhou ou foi reprovado.")
        # the steps to run: the target + everything downstream; every other dependency's latest output is inlined
        refazer = {passo}
        mudou = True
        while mudou:
            mudou = False
            for p in alvo.rota.passos:
                if p.passo not in refazer and set(p.depende_de) & refazer:
                    refazer.add(p.passo)
                    mudou = True
        entradas, estimativas = await self._preparar(alvo, org)
        ultimo_resultado: dict[str, Any] = {}
        for r in sorted(rows, key=lambda r: r.rodada):
            if r.status == CONCLUIDO:
                ultimo_resultado[r.passo] = r.resultado
        specs = []
        for p in alvo.rota.passos:
            if p.passo not in refazer:
                continue
            ent = dict(entradas.get(p.passo) or {})
            for d in p.depende_de:
                if d not in refazer:
                    ent[d] = ultimo_resultado.get(d)  # inlined: the dependency is not part of this partial graph
            est = estimativas.get(p.passo)
            specs.append(StepSpec(p.passo, p.rotulo, tuple(d for d in p.depende_de if d in refazer), p.peso, est, ent))
        rodada = ultima + 1
        graph = GraphSpec(org, post_id, tuple(specs), rodada)
        await self._projetar_fila(org, post_id, alvo.rota, rodada, passo, ator_id)
        await self._runner.enqueue_graph(graph)
        await self._publicar_fila(org, post_id, rodada)
        return self._resposta(alvo.rota, post_id, rodada, [s.passo for s in specs])

    @staticmethod
    def _recusar_se_ativo(rows: list[PassoRow]) -> None:
        if not rows:
            return
        ultima = max(r.rodada for r in rows)
        if any(r.rodada == ultima and r.status in (PENDENTE, EXECUTANDO) for r in rows):
            raise CriacaoError(409, "criacao_em_andamento", "Este post já está em produção.")

    async def _preparar(self, alvo: _Alvo, org: str) -> tuple[dict, dict]:
        preco = None if self._usd_por_credito is None else self._usd_por_credito
        entradas = await asyncio.to_thread(
            lambda: montar_entradas(
                marca_id=str(alvo.post["marca_id"]), conteudo=alvo.conteudo, usd_por_credito=preco
            )
        )
        e = entradas[PASSO_TTS]
        est = await asyncio.to_thread(self._estimar_tts, org, str(alvo.post["marca_id"]), e["texto"], e["modelo"])
        return entradas, {PASSO_TTS: est}

    async def _projetar_fila(self, org: str, post_id: str, rota: Rota, rodada: int, passo: Optional[str], ator_id: Optional[str]) -> None:
        dados = {"rota": rota.chave, "rodada": rodada, **({"refazer": passo} if passo else {})}
        ev = {"tipo": EVENTO_ENFILEIRADA, "dados": dados, **({"ator_id": ator_id} if ator_id else {})}
        await asyncio.to_thread(
            lambda: self._db.rpc(
                "cs_post_criacao_projetar",
                {"p_org": org, "p_post": post_id, "p_estado": ESTADO_NA_FILA, "p_falha": None, "p_eventos": [ev],
                 "p_somente_de": None},
            ).execute()
        )

    async def _publicar_fila(self, org: str, post_id: str, rodada: int) -> None:
        await BusProgress(self._bus).publicar(org, post_id, rodada, "na_fila", 0.0, "Na fila de criação", False)

    @staticmethod
    def _resposta(rota: Rota, post_id: str, rodada: int, passos: list[str]) -> dict:
        return {
            "post_id": post_id, "rota": rota.chave, "rodada": rodada, "passos": passos,
            "progresso_id": f"{post_id}:{rodada}",
        }

    # ── progress snapshot (the SSE stream's first frame; the ledger is the truth) ──────────────────────────────────

    async def snapshot(self, org_id: str, post_id: str, rodada: int) -> Optional[JobProgress]:
        rows = [r for r in await self._ledger.carregar(org_id, post_id) if r.rodada == rodada]
        if not rows:
            return None
        return progresso_das_linhas(rows, pesos=None)


def progresso_das_linhas(rows: list[PassoRow], *, pesos: Optional[dict[str, float]]) -> JobProgress:
    """The wire shape of one rodada. Weighted by the route's expected step durations when known, else equal."""
    from app.modules.media_creation.criacao_rotas import ROTAS

    if pesos is None:
        todos = {p.passo: p.peso for r in ROTAS for p in r.passos}
        pesos = {r.passo: todos.get(r.passo, 1.0) for r in rows}
    total = sum(pesos.get(r.passo, 1.0) for r in rows) or 1.0
    feito = sum(pesos.get(r.passo, 1.0) for r in rows if r.status == CONCLUIDO)
    falhou = next((r for r in rows if r.status == FALHOU), None)
    if falhou is not None:
        return JobProgress("falhou", feito / total, falhou.passo, f"Falhou: {falhou.passo} ({falhou.erro_codigo})", True)
    if all(r.status == CONCLUIDO for r in rows):
        return JobProgress("concluido", 1.0, "concluido", "Criação concluída", True)
    if all(r.status == CANCELADO or r.status == CONCLUIDO for r in rows):
        return JobProgress("cancelado", feito / total, None, "Criação cancelada", True)
    atual = next((r for r in rows if r.status == EXECUTANDO), None)
    return JobProgress(
        "executando" if atual else "na_fila", feito / total, atual.passo if atual else "na_fila",
        None if atual else "Na fila de criação", False,
    )


# ── module-level convenience for the S5 trigger ─────────────────────────────────────────────────────────────────────


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
    """INTERNAL entry (S5 calls it when the card enters Criação): queue the post's media job graph.

    ``service`` is the test / DI seam; by default one is built over the admin client."""
    if service is None:
        from app.dependencies import get_admin_client

        service = build_service(db or get_admin_client())
    return await service.enfileirar(post_id, org_id=org_id, ator_id=ator_id)


__all__ = [
    "CriacaoError", "CriacaoService", "build_service", "default_deps", "enfileirar", "make_runner",
    "progress_bus", "progresso_das_linhas",
]

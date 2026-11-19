"""Job-graph runner over seed ``domain.jobs``.

Every step is one job of type ``media.step`` (lease/heartbeat/retry come from
the seed Worker). The LEDGER is the graph state: ``enqueue_graph`` writes all
steps ``pendente`` and enqueues the roots; a step's completion releases the
dependents whose dependencies are all ``concluido``; a failure marks the step
``falhou(codigo)``, cancels the still-pending rest and publishes a terminal
message -- never silent. ``rerun_step`` re-executes ONE step as rodada+1.
"""

from __future__ import annotations

import logging
import time

from noctusai_lib.domain.jobs import Job, JobRepository
from noctusai_lib.domain.media_production.ports import (
    LedgerPort,
    MoverPort,
    ProgressPort,
    QuotaPort,
)
from noctusai_lib.domain.media_production.registry import StepRegistry, default_registry
from noctusai_lib.domain.media_production.types import (
    CANCELADO,
    CODIGO_ERRO_INTERNO,
    CODIGO_SEM_HANDLER,
    CONCLUIDO,
    EXECUTANDO,
    FALHOU,
    PENDENTE,
    CancelToken,
    GraphSpec,
    PassoRow,
    StepContext,
    StepError,
    StepSpec,
)

logger = logging.getLogger(__name__)

JOB_TYPE = "media.step"

EVENTO_CONCLUIDA = "criacao_concluida"
EVENTO_PASSO_FALHOU = "passo_falhou"


def _key(org: str, post: str, rodada: int, passo: str) -> str:
    return f"media:{org}:{post}:{rodada}:{passo}"


class MediaGraphRunner:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        ledger: LedgerPort,
        progress: ProgressPort,
        quota: QuotaPort,
        mover: MoverPort,
        registry: StepRegistry | None = None,
        max_retries: int = 2,
    ) -> None:
        self._jobs, self._ledger, self._progress = jobs, ledger, progress
        self._quota, self._mover = quota, mover
        self._registry = registry or default_registry()
        self._max_retries = max_retries
        self._specs: dict[tuple[str, str, int], dict[str, StepSpec]] = {}
        self._tokens: dict[tuple[str, str], CancelToken] = {}

    # -- public API ---------------------------------------------------
    @property
    def handlers(self) -> dict:
        """``Worker(handlers=runner.handlers)``."""
        return {JOB_TYPE: self.handle}

    async def enqueue_graph(self, graph: GraphSpec) -> None:
        self._specs[(graph.org_id, graph.post_id, graph.rodada)] = {p.passo: p for p in graph.passos}
        self._tokens[(graph.org_id, graph.post_id)] = CancelToken()
        for p in graph.passos:
            await self._ledger.registrar(
                PassoRow(graph.org_id, graph.post_id, graph.rodada, p.passo, p.depende_de)
            )
        for p in graph.passos:
            if not p.depende_de:
                await self._enqueue(graph.org_id, graph.post_id, graph.rodada, p)

    async def rerun_step(self, org_id: str, post_id: str, rodada: int, passo: str) -> int:
        """Re-run ONE step as rodada+1 (its dependencies' latest outputs are the
        inputs; nothing downstream is touched). Returns the new rodada."""
        rows = await self._ledger.carregar(org_id, post_id)
        atual = [r for r in rows if r.passo == passo and r.rodada == rodada]
        if not atual:
            raise LookupError(f"step {passo!r} rodada {rodada} not found")
        nova = max(r.rodada for r in rows if r.passo == passo) + 1
        spec = self._specs.get((org_id, post_id, rodada), {}).get(passo) or StepSpec(
            passo, passo, atual[0].depende_de
        )
        self._tokens[(org_id, post_id)] = CancelToken()
        self._specs.setdefault((org_id, post_id, nova), {})[passo] = spec
        await self._ledger.registrar(PassoRow(org_id, post_id, nova, passo, spec.depende_de))
        await self._enqueue(org_id, post_id, nova, spec)
        return nova

    def cancel(self, org_id: str, post_id: str) -> None:
        tok = self._tokens.get((org_id, post_id))
        if tok:
            tok.cancel()

    # -- worker handler -----------------------------------------------
    async def handle(self, job: Job) -> None:
        p = job.payload
        org, post, rodada, passo = p["org_id"], p["post_id"], p["rodada"], p["passo"]
        spec = self._specs.get((org, post, rodada), {}).get(passo) or StepSpec(
            passo, p.get("rotulo", passo), tuple(p.get("depende_de", ())), p.get("peso", 1.0)
        )
        rows = await self._ledger.carregar(org, post)
        row = self._row(rows, rodada, passo)
        entradas = dict(spec.entradas)
        for d in spec.depende_de:
            dep = self._latest_done(rows, d)
            entradas[d] = dep.resultado if dep else None
        token = self._tokens.setdefault((org, post), CancelToken())

        n, total = self._position(rows, rodada)
        await self._progress.publicar(
            org, post, rodada, passo, self._fraction(rows, rodada, org, post),
            f"{spec.rotulo} ({n}/{total})", False,
        )
        row = row.with_(status=EXECUTANDO, job_id=job.id, iniciado_em=time.time())
        await self._ledger.registrar(row)

        t0, c0 = time.monotonic(), time.process_time()
        try:
            handler = self._registry.get(passo)
            if handler is None:
                raise StepError(CODIGO_SEM_HANDLER, f"no handler for {passo!r}")
            token.raise_if_cancelled()
            if spec.estimativa_usd is not None:
                await self._quota.verificar(org, spec.estimativa_usd)
            res = await handler(StepContext(org, post, rodada, passo, entradas, token))
        except StepError as exc:
            if exc.retryable and job.retry_count < self._max_retries:
                raise
            await self._fail(row, exc.codigo, t0, c0, rows, spec)
            return
        except Exception:  # noqa: BLE001 - mapped to a visible coded failure
            if job.retry_count < self._max_retries:
                raise  # seed Worker retries with backoff
            logger.exception("media_production.step_error passo=%s", passo)
            await self._fail(row, CODIGO_ERRO_INTERNO, t0, c0, rows, spec)
            return

        # Unmeasured vendor figures are named, never estimated.
        nao_medido = tuple(
            f for f in ("custo_usd", "unidades")
            if res.vendor and getattr(res, f) is None
        )
        await self._ledger.registrar(row.with_(
            status=CONCLUIDO,
            terminado_em=time.time(),
            duracao_s=time.monotonic() - t0,
            cpu_s=time.process_time() - c0,
            vendor=res.vendor,
            modelo=res.modelo,
            request_id=res.request_id,
            unidades=res.unidades,
            custo_usd=res.custo_usd,
            medicoes=res.medicoes,
            resultado=res.saida,
            nao_medido=nao_medido,
        ))
        await self._release(org, post, rodada, await self._ledger.carregar(org, post))

    # -- internals ----------------------------------------------------
    async def _enqueue(self, org: str, post: str, rodada: int, spec: StepSpec) -> None:
        await self._jobs.enqueue(
            type=JOB_TYPE,
            payload={
                "org_id": org, "post_id": post, "rodada": rodada, "passo": spec.passo,
                "rotulo": spec.rotulo, "depende_de": list(spec.depende_de), "peso": spec.peso,
            },
            max_retries=self._max_retries,
            dedupe_key=_key(org, post, rodada, spec.passo),
        )

    async def _release(self, org: str, post: str, rodada: int, rows: list[PassoRow]) -> None:
        specs = self._specs.get((org, post, rodada), {})
        concluidos = {r.passo for r in rows if r.status == CONCLUIDO and r.rodada <= rodada}
        mine = [r for r in rows if r.rodada == rodada]
        for r in mine:
            if r.status == PENDENTE and r.depende_de and set(r.depende_de) <= concluidos:
                await self._enqueue(
                    org, post, rodada, specs.get(r.passo) or StepSpec(r.passo, r.passo, r.depende_de)
                )
        if mine and all(r.status == CONCLUIDO for r in mine):
            await self._progress.publicar(org, post, rodada, "concluido", 1.0, "Criação concluída", True)
            await self._mover.mover(post, EVENTO_CONCLUIDA)

    async def _fail(self, row: PassoRow, codigo: str, t0: float, c0: float, rows, spec: StepSpec) -> None:
        await self._ledger.registrar(row.with_(
            status=FALHOU, erro_codigo=codigo, terminado_em=time.time(),
            duracao_s=time.monotonic() - t0, cpu_s=time.process_time() - c0,
        ))
        for r in await self._ledger.carregar(row.org_id, row.post_id):
            if r.rodada == row.rodada and r.status == PENDENTE:
                await self._ledger.registrar(r.with_(status=CANCELADO))
        await self._progress.publicar(
            row.org_id, row.post_id, row.rodada, row.passo,
            self._fraction(rows, row.rodada, row.org_id, row.post_id),
            f"Falhou: {spec.rotulo} ({codigo})", True,
        )
        await self._mover.mover(row.post_id, EVENTO_PASSO_FALHOU)

    @staticmethod
    def _row(rows: list[PassoRow], rodada: int, passo: str) -> PassoRow:
        for r in rows:
            if r.rodada == rodada and r.passo == passo:
                return r
        raise LookupError(f"ledger row missing: {passo} rodada {rodada}")

    @staticmethod
    def _latest_done(rows: list[PassoRow], passo: str) -> PassoRow | None:
        feitos = [r for r in rows if r.passo == passo and r.status == CONCLUIDO]
        return max(feitos, key=lambda r: r.rodada) if feitos else None

    def _fraction(self, rows: list[PassoRow], rodada: int, org: str, post: str) -> float:
        """Weighted by expected duration (``StepSpec.peso``)."""
        specs = self._specs.get((org, post, rodada), {})
        mine = [r for r in rows if r.rodada == rodada]
        peso = lambda r: specs[r.passo].peso if r.passo in specs else 1.0  # noqa: E731
        total = sum(peso(r) for r in mine) or 1.0
        return sum(peso(r) for r in mine if r.status == CONCLUIDO) / total

    @staticmethod
    def _position(rows: list[PassoRow], rodada: int) -> tuple[int, int]:
        mine = [r for r in rows if r.rodada == rodada]
        n = sum(1 for r in mine if r.status in (CONCLUIDO, FALHOU)) + 1
        return min(n, len(mine)), len(mine)

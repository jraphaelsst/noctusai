"""The eval-loop DRIVER: an automatic loop runs its own rounds until a stop condition (owner 2026-11-17: "Iniciar loop must
actually run rounds automatically in the background ... until target reached, 2 rounds without improvement, budget, max rounds,
error, or a manual stop").

There is no queue to invent: a round is already a background task (``EvalRunner``) and its close hook already decides the stop
(``EvalLoopService.fechar_por_run`` -> G3/G4/G7/erro). The driver only closes the loop of cause and effect:

* a loop is opened in ``automatico`` mode  -> the driver books round 1;
* a round closes without stopping the loop -> the close hook calls :meth:`LoopDriver.agendar` -> the driver books the next one;
* the process restarts                      -> :meth:`LoopDriver.retomar_todos` reads the DB state (every ACTIVE automatic loop),
  reconciles a round whose run ended / was orphaned by the restart, and books the next round. Nothing lives only in memory.

Where the gate refuses a round the driver does not guess: ``hash_inalterado`` (the content did not change since the last round,
and re-running it would only repeat the result) leaves the loop active and IDLE with the reason in ``aviso`` -- the loop waits for a
draft edit and the owner's "Retomar"; the budget / rounds codes stop the loop with that reason; anything else (the turn cannot
start, no cases, compile blocked ...) stops it with motivo ``erro`` + the code and text. There is no refine step between rounds in
the product (refining the draft is the owner's / a content-writing agent's job, ``noctus.agents.content``); the UI says so.

The booking itself (``iniciar``) is injected: the production one calls the SAME functions the HTTP routes call
(``reservar_run`` / ``iniciar_run_mecanismo``) with the loop owner's context, so every guard (one run per user, G6/G7 admission,
preflight, spend ceiling) applies unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import anyio.to_thread
from fastapi import HTTPException

from app.stores.studio_eval_loops import LoopRecord
from app.studio.eval_loop_service import EvalLoopService, RunResumo

logger = logging.getLogger(__name__)

__all__ = ["LoopDriver", "get_driver", "install_driver", "agendar_ao_fechar", "ERRO_DO_DRIVER"]

ERRO_DO_DRIVER = "driver_falhou"
#: gate refusals that END the loop (with their own reason) rather than idle it or error it.
_PARADAS = {
    "orcamento_do_loop_atingido": ("orcamento_atingido", "parado"),
    "rodadas_esgotadas": ("rodadas_esgotadas", "concluido"),
}
#: refusals that leave an automatic loop idle with an ``aviso`` (it can be resumed once the cause is gone).
_AGUARDA = ("hash_inalterado", "execucao_em_andamento", "loop_ativo_do_usuario", "todos_consolidados")

Iniciar = Callable[[LoopRecord], Awaitable[UUID]]
LerResumo = Callable[[LoopRecord, UUID], RunResumo | None]


class LoopDriver:
    def __init__(
        self, *, servico: Callable[[], EvalLoopService], iniciar: Iniciar, ler_resumo: LerResumo,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._servico = servico
        self._iniciar = iniciar
        self._ler_resumo = ler_resumo
        self._event_loop = event_loop
        self._ativos: set[UUID] = set()
        self._repetir: set[UUID] = set()
        self._tasks: set[asyncio.Task[Any]] = set()

    # ── scheduling (callable from any thread) ──────────────────────────────

    def agendar(self, rec: LoopRecord) -> None:
        """Make sure a pass runs for this loop (idempotent; a close arriving while a pass is running asks for ONE more pass, so
        no wake-up is lost)."""
        if rec.modo != "automatico" or rec.status != "ativo":
            return
        try:
            asyncio.get_running_loop()
            self._agendar_no_loop(rec)
        except RuntimeError:
            loop = self._event_loop
            if loop is None or loop.is_closed():
                logger.error("agents.eval_loop.driver_sem_event_loop loop_id=%s", rec.id)
                return
            loop.call_soon_threadsafe(self._agendar_no_loop, rec)

    def _agendar_no_loop(self, rec: LoopRecord) -> None:
        if rec.id in self._ativos:
            self._repetir.add(rec.id)
            return
        self._ativos.add(rec.id)
        task = asyncio.get_running_loop().create_task(self._rodar(rec), name=f"eval-loop-{rec.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _rodar(self, rec: LoopRecord) -> None:
        try:
            while True:
                self._repetir.discard(rec.id)
                await self.avancar(rec.org_id, rec.agent_id, rec.id)
                if rec.id not in self._repetir:
                    return
        except Exception:
            logger.exception("agents.eval_loop.driver_falhou loop_id=%s", rec.id)
        finally:
            self._ativos.discard(rec.id)

    async def retomar_todos(self) -> int:
        """Startup: re-drive every ACTIVE automatic loop from the DB state. Returns how many were scheduled."""
        recs = await anyio.to_thread.run_sync(lambda: self._servico().store.loops_automaticos_ativos())
        for r in recs:
            await anyio.to_thread.run_sync(lambda r=r: self._servico().store.registrar_evento(
                r.org_id, r.id, "driver_retomado", detalhe={"motivo": "reinicio"}))
            self.agendar(r)
        return len(recs)

    # ── one pass ───────────────────────────────────────────────────────────

    async def avancar(self, org_id: UUID, agent_id: UUID, loop_id: UUID) -> str:
        """Reconcile, then book the next round when none is open. Returns what happened (tests / logs)."""
        svc = self._servico()
        store = svc.store
        rec = await anyio.to_thread.run_sync(lambda: store.get_loop(org_id, agent_id, loop_id))
        if rec.status != "ativo" or rec.modo != "automatico":
            return "inativo"
        rodadas = await anyio.to_thread.run_sync(lambda: store.list_rodadas(org_id, loop_id))
        abertas = [r for r in rodadas if r.aberta]
        if abertas:
            resumo = await anyio.to_thread.run_sync(lambda: self._ler_resumo(rec, abertas[0].run_id))
            if resumo is None:
                return "rodando"  # the close hook calls us back when it ends
            await anyio.to_thread.run_sync(lambda: svc.fechar_por_run(org_id, resumo))
            rec = await anyio.to_thread.run_sync(lambda: store.get_loop(org_id, agent_id, loop_id))
            if rec.status != "ativo" or rec.modo != "automatico":
                return "inativo"
        try:
            await self._iniciar(rec)
        except HTTPException as exc:
            return await self._recusada(svc, rec, exc)
        except Exception as exc:  # noqa: BLE001 -- a driver crash stops the loop WITH the reason, never leaves it silently idle
            logger.exception("agents.eval_loop.iniciar_falhou loop_id=%s", loop_id)
            await self._parar_com_erro(svc, rec, ERRO_DO_DRIVER, f"{type(exc).__name__}: o driver não conseguiu abrir a rodada.")
            return "erro"
        if rec.aviso is not None:
            await anyio.to_thread.run_sync(lambda: store.definir_aviso(org_id, loop_id, None))
        return "rodada_aberta"

    async def _recusada(self, svc: EvalLoopService, rec: LoopRecord, exc: HTTPException) -> str:
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail), "code": "http_%s" % exc.status_code}
        code = str(detail.get("code") or "recusada")
        texto = str(detail.get("detail") or code)
        store = svc.store
        if code in ("rodada_em_andamento", "loop_encerrado"):
            return code  # something else is driving / the loop ended: nothing to say
        if code in _PARADAS:
            motivo, status = _PARADAS[code]
            await anyio.to_thread.run_sync(lambda: svc.store.parar_loop(
                rec.org_id, rec.agent_id, rec.id, motivo=motivo, status=status, detalhe={"codigo": code, "mensagem": texto}))
            await anyio.to_thread.run_sync(lambda: store.registrar_evento(
                rec.org_id, rec.id, "loop_parado", detalhe={"motivo": motivo, "codigo": code}))
            return motivo
        if code in _AGUARDA:
            aviso = {"codigo": code, "mensagem": texto}
            await anyio.to_thread.run_sync(lambda: store.definir_aviso(rec.org_id, rec.id, aviso))
            await anyio.to_thread.run_sync(lambda: store.registrar_evento(rec.org_id, rec.id, "driver_aguardando", detalhe=aviso))
            return "aguardando"
        await self._parar_com_erro(svc, rec, code, texto)
        return "erro"

    async def _parar_com_erro(self, svc: EvalLoopService, rec: LoopRecord, codigo: str, mensagem: str) -> None:
        detalhe = {"codigo": codigo, "mensagem": mensagem, "fase": "abrir_rodada"}
        parou = await anyio.to_thread.run_sync(lambda: svc.store.parar_loop(
            rec.org_id, rec.agent_id, rec.id, motivo="erro", status="parado", detalhe=detalhe))
        if parou:
            await anyio.to_thread.run_sync(lambda: svc.store.registrar_evento(
                rec.org_id, rec.id, "loop_parado", detalhe={"motivo": "erro", **detalhe}))


# ── process-wide registry (the close hook has no request to carry the driver) ─────────────────────────────

_DRIVER: LoopDriver | None = None


def install_driver(driver: LoopDriver | None) -> None:
    global _DRIVER
    _DRIVER = driver


def get_driver() -> LoopDriver | None:
    return _DRIVER


def agendar_ao_fechar(rec: LoopRecord) -> None:
    """``EvalLoopService(ao_fechar=...)``: a round closed without stopping the loop. No driver installed (tests) = nothing."""
    d = _DRIVER
    if d is not None:
        d.agendar(rec)

"""``WorkerHandle`` -- start/stop/is_running over a seed ``Worker``.

Replaces the hand-rolled ``_task`` / ``_stop`` module globals plus
``start_worker`` / ``stop_worker`` / ``is_running`` that every product copied
next to each ``Worker`` (N>=3: edicao_fotos, pesquisa_extracao, transcricoes).

    handle = WorkerHandle(worker, name="transcricao-worker")
    handle.start()            # idempotent; needs a running event loop
    handle.is_running()
    await handle.stop()       # signals the stop event; cancels after stop_timeout

``stop`` never raises on a worker that ignores the stop event: after
``stop_timeout`` the task is cancelled (and awaited, so no orphan task leaks).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional

from noctusai_lib.domain.jobs.worker import Worker

logger = logging.getLogger(__name__)

DEFAULT_STOP_TIMEOUT_SECONDS = 10.0


class WorkerHandle:
    def __init__(
        self,
        worker: Worker,
        *,
        name: str = "jobs-worker",
        stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    ) -> None:
        if stop_timeout <= 0:
            raise ValueError("stop_timeout must be > 0")
        self._worker = worker
        self._name = name
        self._stop_timeout = stop_timeout
        self._task: Optional[asyncio.Task] = None
        self._stop: Optional[asyncio.Event] = None

    @property
    def name(self) -> str:
        return self._name

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> bool:
        """Schedule ``run_forever`` as a task. Returns True (running); a second
        call while running is a no-op. Must be called inside a running loop."""
        if self.is_running():
            return True
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self._worker.run_forever(stop_event=self._stop), name=self._name
        )
        logger.info("worker_handle.start name=%s", self._name)
        return True

    async def stop(self) -> None:
        """Signal stop, wait up to ``stop_timeout``, cancel on timeout. Safe to
        call when never started or already stopped."""
        task, stop = self._task, self._stop
        self._task = self._stop = None
        if task is None or stop is None:
            return
        stop.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self._stop_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "worker_handle.stop_timeout name=%s after=%.1fs -- cancelling",
                self._name, self._stop_timeout,
            )
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        except asyncio.CancelledError:
            raise
        except Exception:
            # The worker crashed on its own; it is stopped either way, but not silently.
            logger.exception("worker_handle.worker_crashed name=%s", self._name)


__all__ = ["DEFAULT_STOP_TIMEOUT_SECONDS", "WorkerHandle"]

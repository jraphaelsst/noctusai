"""Bounded, per-key-serial dispatch of Julia (lead) turns.

Why this exists: the seed `ConversationWorker` drains due conversations on ONE thread,
and a lead turn is an HTTP call to agents (up to ~60 s). Run inline, it blocked every
operator (One Chat) batch queued behind it and serialized unrelated lead chats.

The worker thread now only *hands the batch over* (`submit_threadsafe`, non-blocking)
and the turn runs on the main loop here:

  - one in-flight turn per `lead:<connection_id>:<chat_id>` key (a per-key lock keeps
    the order; the turn re-reads the buffer under the lock, so an inbound that landed
    while the previous turn ran is picked up by `unprocessed_run`, never lost/doubled);
  - at most `max_concurrent` turns across all keys (a semaphore, taken AFTER the key
    lock so a waiting same-chat turn never holds a slot a different chat could use);
  - `shutdown()` lets in-flight turns finish for a grace period, then cancels them.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

LeadRunner = Callable[[str, list[dict[str, Any]]], Awaitable[None]]
MemoryReader = Callable[[str], list[dict[str, Any]]]


class LeadTurnDispatcher:
    def __init__(
        self,
        run: LeadRunner,
        *,
        max_concurrent: int = 4,
        timeout_s: float = 180.0,
        reload_memory: MemoryReader | None = None,
    ) -> None:
        self._run = run
        self._max_concurrent = max(1, int(max_concurrent))
        self._timeout_s = timeout_s
        self._reload = reload_memory
        self._sem: asyncio.Semaphore | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, int] = {}
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    def submit(self, key: str, memory: list[dict[str, Any]]) -> asyncio.Task | None:
        """Schedule one batch. MUST be called on the loop that runs the turns."""
        if self._closed:
            logger.warning("lead dispatcher closed; batch for %s not run", key)
            return None
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max_concurrent)
        self._pending[key] = self._pending.get(key, 0) + 1
        task = asyncio.ensure_future(self._turn(key, memory))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def submit_threadsafe(self, loop: asyncio.AbstractEventLoop, key: str, memory: list[dict[str, Any]]) -> None:
        """Non-blocking hand-over from the worker thread."""
        loop.call_soon_threadsafe(self.submit, key, memory)

    async def _turn(self, key: str, memory: list[dict[str, Any]]) -> None:
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                assert self._sem is not None
                async with self._sem:
                    current = memory
                    if self._reload is not None:
                        try:
                            current = self._reload(key) or memory
                        except Exception as exc:
                            logger.error("lead dispatcher: memory reload failed for %s (%s)", key, type(exc).__name__)
                    await asyncio.wait_for(self._run(key, current), timeout=self._timeout_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("conv=%s: lead dispatch failed (%s)", key, type(exc).__name__)
        finally:
            self._pending[key] -= 1
            if self._pending[key] <= 0:
                self._pending.pop(key, None)
                self._locks.pop(key, None)

    async def shutdown(self, grace_s: float = 5.0) -> None:
        """Refuse new batches, let in-flight turns finish for `grace_s`, cancel the rest."""
        self._closed = True
        tasks = list(self._tasks)
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=grace_s)
        for t in pending:
            t.cancel()
        if pending:
            logger.warning("lead dispatcher: cancelled %d turn(s) at shutdown", len(pending))
            await asyncio.gather(*pending, return_exceptions=True)

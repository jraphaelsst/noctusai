"""``spawn_background`` — start a background task or thread with an EXPLICIT Supabase-breaker source.

A bare ``asyncio.create_task`` inherits whatever context spawned it (a request, the boot), and a bare
``threading.Thread`` starts with an EMPTY context (``unattributed``): either way the work is invisible to the breaker
(it only alerts for such sources, but an alert saying "unattributed" tells nobody which loop). This names it:

    spawn_background("conversation-worker", worker.run_forever(stop_event=ev))     # a coroutine -> a task
    spawn_background("pos-aceite-send", send_fn, arg1, kw=1)                       # a callable  -> a thread

The source is ``bg:<name>`` — ALERT-ONLY by design (a registered Worker / scheduler job is what can be held).
``run_in_thread`` is the context-carrying thread helper for work detached from a request: the thread runs in a COPY of the
caller's context under ``bg:<name>``, so request-scoped state (correlation id, org) is not lost.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
import threading
from typing import Any, Callable, Optional

from noctusai_lib.primitives.supabase_breaker import detach_context, source_scope
from noctusai_lib.primitives.tasks import schedule_coro

__all__ = ["run_in_thread", "spawn_background"]

_default_logger = logging.getLogger(__name__)


def run_in_thread(name: str, fn: Callable[..., Any], *args: Any, daemon: bool = True,
                  logger: Optional[logging.Logger] = None, **kwargs: Any) -> threading.Thread:
    """Start ``fn(*args, **kwargs)`` on a thread that carries a copy of the caller's context, attributed to
    ``bg:<name>``. An exception is logged at ERROR (never swallowed)."""
    log = logger or _default_logger
    ctx = contextvars.copy_context()

    def _run() -> None:
        try:
            detach_context()  # the spawner's per-job budget / call tally are not this thread's
            with source_scope(f"bg:{name}"):
                fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 -- logged loudly; a detached thread has no caller to raise to
            log.exception("background thread %r failed", name)

    thread = threading.Thread(target=lambda: ctx.run(_run), name=f"bg-{name}", daemon=daemon)
    thread.start()
    return thread


def spawn_background(name: str, target: Any, *args: Any, logger: Optional[logging.Logger] = None,
                     **kwargs: Any) -> "asyncio.Task[Any] | threading.Thread":
    """A coroutine (object or function) becomes a task on the running loop; any other callable becomes a thread.
    Either way the work runs under the explicit source ``bg:<name>``."""
    if inspect.iscoroutine(target) or inspect.iscoroutinefunction(target):
        coro = target if inspect.iscoroutine(target) else target(*args, **kwargs)

        async def _scoped() -> Any:
            detach_context()
            with source_scope(f"bg:{name}"):
                return await coro

        return schedule_coro(_scoped(), logger=logger or _default_logger, name=name)
    return run_in_thread(name, target, *args, logger=logger, **kwargs)

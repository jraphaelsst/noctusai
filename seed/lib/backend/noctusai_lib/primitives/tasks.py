"""Fire-and-forget task scheduling primitive.

**Why a primitive.** Three product backends each hand-rolled the same
"schedule a coroutine on the running loop, log if it fails, optionally
track the task" shape:

- `products/core/backend/app/routers/billing.py` — webhook dispatch via
  `loop.create_task(...)` inside a `try/except RuntimeError`.
- `products/erp-imobiliario/backend/app/services/certidoes_service.py` —
  `task = asyncio.create_task(...)` with task tracked in a per-org dict.
- `products/erp-imobiliario/backend/app/services/job_service.py` —
  `asyncio.ensure_future(...)`.

At N=3 the recurrence rule fires. None of the three callsites attach a
`done_callback` — every exception was either silently retrieved by the
loop's "exception was never retrieved" warning OR (in billing.py) caught
at the outer try/except and logged at WARN without traceback. This module
fixes both gaps: every scheduled coroutine logs exceptions via
`logger.exception(...)` (full traceback) when it raises.

**Layer.** `primitives/` — pure asyncio shaping; no FastAPI, no IO, no
domain knowledge. Per the seed-lib-layout decision tree, step 6 fires
("stateless pure helper any layer might call → primitives/").

**Public surface.**

    from noctusai_lib.primitives.tasks import schedule_coro, NoRunningLoopError

    # Fire-and-forget without caring about the task:
    schedule_coro(some_coro(), logger=logger, name="webhook_dispatch")

    # Track the task (for idempotency / cancellation):
    task = schedule_coro(some_coro(), logger=logger, name="tjsp_org_X")
    self._tasks[org_id] = task

**Cancellation semantics.** A `CancelledError` from the wrapped coroutine
is logged at `debug` level (not `exception`) so shutdown-time cancels
don't pollute prod logs with stack traces.

**No silent errors.** This module never swallows exceptions silently.
The done-callback ALWAYS calls `logger.exception(...)` for non-cancel
exceptions, even when the caller didn't supply a logger (the module
falls back to its own logger).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional

_module_logger = logging.getLogger(__name__)


class NoRunningLoopError(RuntimeError):
    """Raised when `schedule_coro` is called outside a running event loop.

    Wraps the bare `RuntimeError("no running event loop")` from
    `asyncio.get_running_loop()` into a typed exception so callers can
    `except NoRunningLoopError` precisely.
    """


def schedule_coro(
    coro: Coroutine[Any, Any, Any],
    *,
    logger: Optional[logging.Logger] = None,
    name: Optional[str] = None,
) -> "asyncio.Task[Any]":
    """Schedule `coro` on the running event loop, fire-and-forget.

    Returns the `Task` so callers that need it (idempotency dicts,
    cancellation, await-elsewhere) can hold a reference. Callers that
    don't care about the task can ignore the return value — the loop
    holds its own reference until the task completes.

    Args:
        coro: A coroutine object (the result of calling `async def f(...)`).
            Must NOT be already-scheduled — pass the bare coroutine.
        logger: Optional logger for exception reporting. Defaults to the
            module logger (`noctusai_lib.primitives.tasks`).
        name: Optional task name. Surfaces in `Task.get_name()` and in
            the exception log line, useful for distinguishing tasks in
            crowded loop dumps.

    Returns:
        The `asyncio.Task` wrapping `coro`. The task starts running on
        the next event-loop tick.

    Raises:
        NoRunningLoopError: If called from a context with no running
            event loop. This is almost always a bug — fire-and-forget
            is meaningful only inside an async context. Restructure
            (use `asyncio.run` or `asyncio.run_coroutine_threadsafe`
            with an explicit loop) instead of catching this exception.
    """
    log = logger if logger is not None else _module_logger

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        # Close the bare-coroutine to avoid "coroutine was never
        # awaited" RuntimeWarning noise on top of the real error.
        coro.close()
        raise NoRunningLoopError(
            f"schedule_coro requires a running event loop "
            f"(name={name!r}); call from an async context."
        ) from exc

    task = loop.create_task(coro, name=name) if name is not None else loop.create_task(coro)

    def _done_callback(t: "asyncio.Task[Any]") -> None:
        # Cancellation — common at shutdown; keep logs clean.
        if t.cancelled():
            log.debug("schedule_coro: task cancelled name=%s", t.get_name())
            return
        # Anything else surfaced from the task — log with full traceback.
        # `task.exception()` returns the exception (and silences the
        # loop's "exception was never retrieved" warning) or None on
        # success.
        exc = t.exception()
        if exc is not None:
            # logger.exception requires sys.exc_info to work properly,
            # so we use logger.error with exc_info=exc to attach the
            # traceback explicitly inside the done-callback (where
            # sys.exc_info is unset).
            log.error(
                "schedule_coro: task raised name=%s",
                t.get_name(),
                exc_info=exc,
            )

    task.add_done_callback(_done_callback)
    return task


__all__ = ["schedule_coro", "NoRunningLoopError"]

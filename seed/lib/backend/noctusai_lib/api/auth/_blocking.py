"""Run blocking (sync supabase / network) work off the event loop.

The seed's auth dependencies are ``async def`` (they are awaited by sibling
dependencies and call ``await`` themselves) but everything they reach for —
Supabase Auth ``get_user``, the ``noctus_users`` / licence lookups — is the
SYNC supabase-py client. Called directly, each such call parks the single
uvicorn event loop for its whole network round-trip, so concurrent requests
serialize (3 parallel orbity requests finished as a 985 / 1,524 / 2,081 ms
staircase). ``anyio.to_thread.run_sync`` moves the call to a worker thread and
lets the loop serve the others.

Why ``to_thread.run_sync`` and not turning the dependencies into plain ``def``:
FastAPI would threadpool a ``def`` dependency, but these deps ``await`` other
deps and are called IMPERATIVELY (``await deps.get_current_user(authorization)``)
by every seed router — they must stay coroutines. ``anyio``'s default limiter
(40 threads) is the same one Starlette uses for sync endpoints.

``contextvars`` are copied into the worker, so request-scoped context set by
middleware still applies. Exceptions (``HTTPException`` included) propagate
unchanged.
"""
from __future__ import annotations

import contextvars
import functools
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

import anyio
import anyio.to_thread

from ..request_timing import record_blocking, record_parallel

T = TypeVar("T")


# Injection seam for tests / capacity experiments: ``None`` = anyio's default limiter (40).
_limiter: anyio.CapacityLimiter | None = None


def set_blocking_limiter(limiter: anyio.CapacityLimiter | None) -> None:
    """Use ``limiter`` for ``run_blocking`` (``None`` restores the default)."""
    global _limiter
    _limiter = limiter


async def run_blocking(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Await ``fn(*args, **kwargs)`` in a worker thread.

    Per request (see ``api/request_timing.py``) it records the hop's queue wait (submit -> fn
    starts: the limiter / thread hand-off) and its run time, so "waiting" and "working" separate."""
    call = functools.partial(fn, *args, **kwargs)
    submitted = time.perf_counter()

    def _timed() -> T:
        started = time.perf_counter()
        try:
            return call()
        finally:
            record_blocking(started - submitted, time.perf_counter() - started)

    return await anyio.to_thread.run_sync(_timed, limiter=_limiter)


# Dedicated pool for fan-out INSIDE an already-threaded call. Deliberately not anyio's
# limiter: a worker that waits on children from the same bounded limiter can starve it.
_PARALLEL_POOL = ThreadPoolExecutor(max_workers=24, thread_name_prefix="seed-par")


def run_parallel(*thunks: Callable[[], Any]) -> list[Any]:
    """Run independent zero-arg SYNC callables concurrently; results in argument order.

    For sequential PostgREST round trips that do not depend on each other (the effective-org
    resolver's memberships / blocks / live-selection reads): wall time becomes the slowest
    one instead of the sum (~25 ms warm each, VPS -> Supabase). Call it from sync code that
    already runs in a worker thread (``run_blocking``), never on the event loop.

    Every thunk runs to completion before returning; if any raised, the FIRST (by argument
    order) exception is re-raised unchanged -- nothing is swallowed, no thunk is left running.
    ``contextvars`` are copied into each worker.
    """
    if len(thunks) == 1:
        return [thunks[0]()]
    def _timed(t: Callable[[], Any], submitted: float) -> Any:
        record_parallel(time.perf_counter() - submitted)
        return t()

    futures = [
        _PARALLEL_POOL.submit(contextvars.copy_context().run, _timed, t, time.perf_counter())
        for t in thunks
    ]
    outcomes: list[tuple[bool, Any]] = []
    for fut in futures:
        exc = fut.exception()
        outcomes.append((exc is None, exc if exc is not None else fut.result()))
    for ok, val in outcomes:
        if not ok:
            raise val
    return [val for _ok, val in outcomes]

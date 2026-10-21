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

import functools
from typing import Any, Callable, TypeVar

import anyio.to_thread

T = TypeVar("T")


async def run_blocking(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Await ``fn(*args, **kwargs)`` in a worker thread."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))

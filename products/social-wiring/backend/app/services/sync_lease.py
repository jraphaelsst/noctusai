"""Cross-process run lock for scheduled jobs (migration 069).

`asyncio.Lock` serialises coroutines inside ONE process. It cannot see a
second process, which is the case that actually bites: two containers
after a replica bump, a container plus an authorised one-off, or — as on
2026-08-22 — a stray backend on a laptop.

`noctusai_lib.api.scheduler` now refuses to start outside a deployed
container, which closes the laptop case at the source. This is the layer
underneath: it holds even when two processes are BOTH legitimately
authorised, which is precisely the multi-replica future the scheduler
guard does nothing about.

Not a Postgres advisory lock — see the migration header for why (they are
session-scoped, and PostgREST pools connections, so the lock is released
the moment the HTTP request ends).
"""
from __future__ import annotations

import contextlib
import logging
import os
import socket
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"

#: Comfortably longer than the work it guards. The imóveis full pull
#: measures ~403s; 30 minutes leaves room for a slow Vista day without
#: leaving a crashed holder's lease wedged for hours.
DEFAULT_TTL_SECONDS = 1800


def holder_id() -> str:
    """Identify this process: host + pid.

    "Which box is running this" is the first question anyone asks when a
    lease looks stuck, and the answer has to be in the row itself — by the
    time you are asking, the process may be gone.
    """
    return f"{socket.gethostname()}:{os.getpid()}"


def try_acquire(
    admin: Any,
    name: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    holder: Optional[str] = None,
) -> Optional[str]:
    """Take the lease, or return None if someone else holds it.

    Returns the holder id on success so the caller can release exactly what
    it took. Returns None when another live lease exists.

    Raises nothing on a TRANSPORT failure — it returns None, i.e. "assume
    someone else has it, do not run". That is the deliberately conservative
    direction: skipping one nightly sync costs a day of staleness, while
    running two concurrent full pulls against the same catalog is the
    condition this exists to prevent. Note this is the OPPOSITE of the OLX
    drains' fail-open pre-flight, and for the opposite reason — there, not
    running risks dropping a real lead; here, running twice is the harm.
    """
    who = holder or holder_id()
    try:
        resp = admin.schema(_SCHEMA).rpc(
            "try_acquire_sync_lease",
            {"p_name": name, "p_holder": who, "p_ttl_seconds": ttl_seconds},
        ).execute()
    except Exception as exc:
        logger.warning(
            "sync lease %r: acquire failed (%s) — treating as NOT acquired "
            "so nothing runs twice", name, exc,
        )
        return None

    if bool(resp.data):
        return who

    logger.info(
        "sync lease %r: held by another process — skipping this run", name,
    )
    return None


def release(admin: Any, name: str, holder: str) -> None:
    """Give the lease back. Never raises.

    A failed release is not an error worth propagating: the TTL is the real
    recovery path, and letting a release failure escape would mask whatever
    the job itself just reported.
    """
    try:
        admin.schema(_SCHEMA).rpc(
            "release_sync_lease", {"p_name": name, "p_holder": holder}
        ).execute()
    except Exception as exc:
        logger.warning(
            "sync lease %r: release failed (%s) — the lease will expire on "
            "its own", name, exc,
        )


@contextlib.contextmanager
def lease(
    admin: Any,
    name: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Iterator[bool]:
    """`with lease(admin, "job") as got:` — True iff this process may run.

    Releases on the way out, including on exception, so a crashing job does
    not hold the lease for the full TTL.
    """
    who = try_acquire(admin, name, ttl_seconds=ttl_seconds)
    try:
        yield who is not None
    finally:
        if who is not None:
            release(admin, name, who)


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "holder_id",
    "lease",
    "release",
    "try_acquire",
]

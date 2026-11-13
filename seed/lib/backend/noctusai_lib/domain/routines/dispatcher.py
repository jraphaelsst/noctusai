"""Reconcile DB-defined routines onto the code-registered APScheduler.

APScheduler jobs are registered in code; routines live in the DB and change at runtime
(created, retimed, disabled, killed, master-flipped). ``RoutineDispatcher.reconcile`` makes
the scheduler match the DB: it ADDS jobs for runnable routines, UPDATES a job whose cron
changed, REMOVES jobs whose routine is gone / disabled / killed / master-off. A reconcile
job (``register_reconciler``) runs it every minute, so a kill takes effect within one tick.

Defence in depth: the job body ALSO asks ``RoutineService.run`` which re-checks the gate at
fire time, so a routine killed between two reconciles still never fires (the run is recorded
as ``skipped`` in the scheduler ledger via ``SkipRun``).

``SchedulerPort`` is the seam: ``ApSchedulerPort`` drives ``noctusai_lib.api.scheduler``
(its ``register`` -- run ledger + breaker included), ``FakeSchedulerPort`` is for tests.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from noctusai_lib.domain.routines.service import RoutineService
from noctusai_lib.domain.routines.store import RoutineStore
from noctusai_lib.domain.routines.types import Routine, RoutineBlocked

logger = logging.getLogger(__name__)

JOB_PREFIX = "routine:"
RECONCILER_JOB = "routines-reconcile"
JobFn = Callable[[], Awaitable[None]]


def job_name(routine: Routine) -> str:
    return f"{JOB_PREFIX}{routine.org_id}:{routine.id}"


class SchedulerPort(Protocol):
    def add(self, name: str, cron: str, fn: JobFn) -> None: ...

    def remove(self, name: str) -> None: ...

    def jobs(self) -> dict[str, str]:
        """name -> cron of every job this port holds under ``JOB_PREFIX``."""
        ...


class FakeSchedulerPort:
    def __init__(self) -> None:
        self.registered: dict[str, tuple[str, JobFn]] = {}

    def add(self, name: str, cron: str, fn: JobFn) -> None:
        self.registered[name] = (cron, fn)

    def remove(self, name: str) -> None:
        self.registered.pop(name, None)

    def jobs(self) -> dict[str, str]:
        return {n: c for n, (c, _) in self.registered.items() if n.startswith(JOB_PREFIX)}


class ApSchedulerPort:
    """Drives the seed scheduler. ``add`` = ``scheduler.register`` (idempotent per name: a changed
    cron replaces the job; run ledger + breaker apply). ``remove`` drops the APScheduler job and its spec."""

    def add(self, name: str, cron: str, fn: JobFn) -> None:
        from noctusai_lib.api import scheduler as sched

        sched.register(name, fn, cron=cron)

    def remove(self, name: str) -> None:
        from noctusai_lib.api import scheduler as sched

        sched._drop_existing(name)
        sched._job_specs.pop(name, None)

    def jobs(self) -> dict[str, str]:
        from noctusai_lib.api import scheduler as sched

        return {s.job: s.cron or "" for s in sched.job_specs() if s.job.startswith(JOB_PREFIX)}


@dataclass(frozen=True)
class ReconcileResult:
    added: tuple[str, ...] = field(default_factory=tuple)
    updated: tuple[str, ...] = field(default_factory=tuple)
    removed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


class RoutineDispatcher:
    def __init__(self, store: RoutineStore, service: RoutineService, port: SchedulerPort) -> None:
        self.store = store
        self.service = service
        self.port = port

    def _make_job(self, org_id: UUID, routine_id: UUID) -> JobFn:
        async def _job() -> None:
            from noctusai_lib.api.scheduler import SkipRun

            try:
                await self.service.run(org_id, routine_id, scheduled=True)
            except RoutineBlocked as exc:
                raise SkipRun(str(exc)) from exc

        return _job

    def reconcile(self) -> ReconcileResult:
        desired = {job_name(r): r for r in self.store.list_runnable()}
        current = self.port.jobs()
        added, updated, removed = [], [], []
        for name, r in sorted(desired.items()):
            if name not in current:
                self.port.add(name, r.cron, self._make_job(r.org_id, r.id))
                added.append(name)
            elif current[name] != r.cron:
                self.port.add(name, r.cron, self._make_job(r.org_id, r.id))
                updated.append(name)
        for name in sorted(set(current) - set(desired)):
            self.port.remove(name)
            removed.append(name)
        res = ReconcileResult(tuple(added), tuple(updated), tuple(removed))
        if res.changed:
            logger.info("routines reconciled added=%d updated=%d removed=%d", len(added), len(updated), len(removed))
        return res


def register_reconciler(dispatcher: RoutineDispatcher, *, minutes: int = 1) -> None:
    """Register the periodic reconcile job on the seed scheduler (call at import / startup)."""
    from noctusai_lib.api.scheduler import register

    async def _reconcile() -> None:
        await asyncio.to_thread(dispatcher.reconcile)

    register(RECONCILER_JOB, _reconcile, minutes=minutes)


__all__ = [
    "ApSchedulerPort", "FakeSchedulerPort", "JOB_PREFIX", "RECONCILER_JOB", "ReconcileResult",
    "RoutineDispatcher", "SchedulerPort", "job_name", "register_reconciler",
]

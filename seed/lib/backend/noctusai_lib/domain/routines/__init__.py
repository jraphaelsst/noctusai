"""Routines organ -- the run-lifecycle seam: trigger -> draft -> approve/reject(reason) -> routine.

Org-scoped, DB-defined scheduled jobs (cron, mode ``trigger|routine``, ``ativo``, config JSON), a
per-product MASTER switch plus a per-routine switch / kill (every flip an event with actor + reason),
an append-only ``routine_events`` log, a dispatcher reconciling the DB onto the seed APScheduler,
trigger-now, and a daily report on ``BaseDigestService``. Approval is ``domain/editorial`` configured
with ONE review stage (``ROUTINES_WORKFLOW``).

- ``types``          value objects, enums, errors, cron/mode validation.
- ``workflow``       ``ROUTINES_WORKFLOW`` (single-step approval) + the system actor.
- ``store``          ``RoutineStore`` Protocol, ``FakeRoutineStore``, ``make_routine_store``.
- ``store_supabase`` the Real store (SECURITY DEFINER functions: row + event, one transaction).
- ``ddl``            ``routines_tables_sql(schema)`` (migration-authoring helper; tier:org tables).
- ``service``        ``RoutineService`` run lifecycle (run / approve / reject), ``RunCollector`` Protocol.
- ``dispatcher``     ``RoutineDispatcher`` + ``SchedulerPort`` (Ap + Fake) + ``register_reconciler``.
- ``report``         ``RoutinesDailyReport`` + ``aggregate_events``.
- ``router``         ``routines_router`` (org-admin only).

Editorial DDL for the same schema: ``sql_templates.editorial_tables(schema, ROUTINES_WORKFLOW)``.
"""
from noctusai_lib.domain.routines.ddl import routines_tables_sql
from noctusai_lib.domain.routines.dispatcher import (
    ApSchedulerPort,
    FakeSchedulerPort,
    ReconcileResult,
    RoutineDispatcher,
    SchedulerPort,
    register_reconciler,
)
from noctusai_lib.domain.routines.report import RoutinesDailyReport, aggregate_events
from noctusai_lib.domain.routines.router import RoutinesContext, routines_router
from noctusai_lib.domain.routines.service import RoutineService, RunCollector
from noctusai_lib.domain.routines.store import FakeRoutineStore, RoutineStore, make_routine_store
from noctusai_lib.domain.routines.types import (
    EVENT_KINDS,
    MODES,
    EventKind,
    Mode,
    Routine,
    RoutineBlocked,
    RoutineConflict,
    RoutineError,
    RoutineEvent,
    RoutineInvalid,
    RoutineNotFound,
    RunItem,
    RunResult,
)
from noctusai_lib.domain.routines.workflow import ROUTINES_WORKFLOW, SYSTEM_ACTOR

__all__ = [
    "ApSchedulerPort", "EVENT_KINDS", "EventKind", "FakeRoutineStore", "FakeSchedulerPort", "MODES", "Mode",
    "ROUTINES_WORKFLOW", "ReconcileResult", "Routine", "RoutineBlocked", "RoutineConflict", "RoutineDispatcher",
    "RoutineError", "RoutineEvent", "RoutineInvalid", "RoutineNotFound", "RoutineService", "RoutineStore",
    "RoutinesContext", "RoutinesDailyReport", "RunCollector", "RunItem", "RunResult", "SYSTEM_ACTOR",
    "SchedulerPort", "aggregate_events", "make_routine_store", "register_reconciler", "routines_router",
    "routines_tables_sql",
]

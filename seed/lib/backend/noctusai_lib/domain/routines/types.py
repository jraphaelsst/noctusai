"""Value objects, enums and errors of the routines seam.

A *routine* is an org-scoped, DB-defined scheduled job: a cron expression, a run
``mode`` and a ``config`` blob the product's collector reads (search / source
params, editable from the UI). Every state change of a routine lands in the
append-only ``routine_events`` log in the SAME transaction as the change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class Mode(str, Enum):
    """``trigger`` = every run becomes an editorial DRAFT awaiting approval;
    ``routine`` = the run publishes automatically (after the owner validated it)."""

    TRIGGER = "trigger"
    ROUTINE = "routine"


class EventKind(str, Enum):
    CREATED = "created"
    EDITED = "edited"
    MODE_CHANGED = "mode_changed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    KILLED = "killed"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    DRAFT_CREATED = "draft_created"
    APPROVED = "approved"
    REJECTED = "rejected"


EVENT_KINDS: tuple[str, ...] = tuple(k.value for k in EventKind)
MODES: tuple[str, ...] = tuple(m.value for m in Mode)

#: Kinds a caller may record through ``record_event`` (the run lifecycle). The
#: others are written ONLY by the store's own mutations, atomically with the change.
RUN_EVENT_KINDS: frozenset[str] = frozenset({
    EventKind.RUN_STARTED.value, EventKind.RUN_FINISHED.value, EventKind.DRAFT_CREATED.value,
    EventKind.APPROVED.value, EventKind.REJECTED.value,
})

#: Flips and rejections must say why (the event is the audit trail).
REASON_REQUIRED: frozenset[str] = frozenset({
    EventKind.ENABLED.value, EventKind.DISABLED.value, EventKind.KILLED.value, EventKind.REJECTED.value,
})

SCOPE_ROUTINE = "routine"
SCOPE_MASTER = "master"


class RoutineError(Exception):
    """Base of every routines error."""


class RoutineNotFound(RoutineError):
    pass


class RoutineInvalid(RoutineError):
    """Malformed input (bad cron, bad mode, missing reason...)."""


class RoutineConflict(RoutineError):
    """(org, name) already exists."""


class RoutineBlocked(RoutineError):
    """The run may not start: ``reason`` is ``killed`` / ``master_off`` / ``disabled``."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"routine blocked: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class Routine:
    id: UUID
    org_id: UUID
    name: str
    cron: str
    mode: str
    ativo: bool
    killed: bool
    config: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RoutineEvent:
    id: int
    org_id: UUID
    routine_id: UUID | None  # None = the per-product MASTER switch
    scope: str  # routine | master
    kind: str
    actor_id: UUID  # the system actor is a real id
    reason: str | None
    detail: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class RunItem:
    """One collected thing. ``ref`` is its dedup key within the routine
    (e.g. the canonical URL); ``content`` becomes the editorial draft."""

    ref: str
    content: Mapping[str, Any]


@dataclass(frozen=True)
class RunResult:
    run_id: UUID
    routine_id: UUID
    mode: str
    status: str  # ok | error
    collected: int = 0
    drafts: int = 0
    published: int = 0
    duplicates: int = 0
    item_ids: tuple[UUID, ...] = field(default_factory=tuple)
    error: str | None = None


_CRON_FIELDS = 5


def validate_cron(expr: str) -> str:
    """Return the stripped 5-field cron or raise ``RoutineInvalid`` (same parser the scheduler uses)."""
    s = (expr or "").strip()
    if len(re.split(r"\s+", s)) != _CRON_FIELDS:
        raise RoutineInvalid(f"cron must have {_CRON_FIELDS} fields: {expr!r}")
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(s)
    except ValueError as exc:
        raise RoutineInvalid(f"invalid cron {expr!r}: {exc}") from exc
    return s


def validate_mode(mode: Any) -> str:
    m = getattr(mode, "value", mode)
    if m not in MODES:
        raise RoutineInvalid(f"mode must be one of {MODES}, got {mode!r}")
    return m


def need_reason(kind: str, reason: str | None) -> str | None:
    r = (reason or "").strip() or None
    if kind in REASON_REQUIRED and r is None:
        raise RoutineInvalid(f"{kind!r} needs a reason")
    return r

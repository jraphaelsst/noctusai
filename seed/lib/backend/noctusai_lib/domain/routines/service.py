"""The run lifecycle: trigger -> draft -> approve / reject(reason) -> routine.

``RoutineService.run`` executes ONE run of a routine:

    gate (killed / master off / [scheduled] disabled)  ->  run_started
    collector.collect(routine)  ->  one editorial draft per NEW item (dedup on ``ref``)
    ``trigger`` mode  : draft is submitted and waits in ``revisao_editorial`` for the owner
    ``routine`` mode  : the system actor publishes it right away (event ``approved``, ``auto``)
    ->  run_finished  (counts, or the error -- then re-raised so the scheduler ledger sees it)

Approval is the editorial organ configured with ONE review stage (``workflow.py``): approve =
``publish``, reject = ``archive`` with a motivo; each also lands its ``approved`` / ``rejected``
event in ``routine_events``. The editorial store and the routine store are two stores: each
step is atomic in its own, ordered so a crash leaves a visible, resumable trail (never a
silent publish).

Editorial item identity: ``kind`` = ``config["editorial_kind"]`` (default ``routine_item``),
``ref`` = ``"<routine_id>:<item ref>"`` -- unique per org, so a re-run never duplicates an item.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Iterable, Protocol, Sequence
from uuid import UUID, uuid4

from noctusai_lib.domain.editorial.store import EditorialConflict, EditorialStore
from noctusai_lib.domain.editorial.workflow import Action
from noctusai_lib.domain.routines.store import RoutineStore
from noctusai_lib.domain.routines.types import (
    EventKind,
    Mode,
    Routine,
    RoutineBlocked,
    RoutineNotFound,
    RunItem,
    RunResult,
)
from noctusai_lib.domain.routines.workflow import (
    SYSTEM_ACTOR,
    SYSTEM_DRAFT_GRANTS,
    SYSTEM_PUBLISH_GRANTS,
)

logger = logging.getLogger(__name__)

DEFAULT_EDITORIAL_KIND = "routine_item"
ERROR_MAX_CHARS = 500


class RunCollector(Protocol):
    """The product's part: pull + validate one routine's items from ``routine.config``."""

    async def collect(self, routine: Routine) -> Sequence[RunItem]: ...


def editorial_kind_of(routine: Routine) -> str:
    return str(routine.config.get("editorial_kind") or DEFAULT_EDITORIAL_KIND)


def item_ref(routine_id: UUID, ref: str) -> str:
    return f"{routine_id}:{ref}"


class RoutineService:
    def __init__(self, store: RoutineStore, editorial: EditorialStore, collector: RunCollector) -> None:
        self.store = store
        self.editorial = editorial
        self.collector = collector

    # -- gate ------------------------------------------------------------
    def check_gate(self, routine: Routine, *, scheduled: bool) -> None:
        """Raise ``RoutineBlocked`` when the run may not start. A killed routine and a master-off
        product never run, scheduled or manual; a scheduled run also needs ``ativo``."""
        if routine.killed:
            raise RoutineBlocked("killed")
        if not self.store.master_enabled(routine.org_id):
            raise RoutineBlocked("master_off")
        if scheduled and not routine.ativo:
            raise RoutineBlocked("disabled")

    # -- run -------------------------------------------------------------
    async def run(
        self, org_id: UUID, routine_id: UUID, *, scheduled: bool = False, actor_id: UUID | None = None,
    ) -> RunResult:
        io = _io
        actor = SYSTEM_ACTOR if (scheduled or actor_id is None) else actor_id
        routine = await io(self.store.get_routine, org_id, routine_id)
        await io(self.check_gate, routine, scheduled=scheduled)
        run_id = uuid4()
        auto_publish = routine.mode == Mode.ROUTINE.value
        base = {"run_id": str(run_id), "mode": routine.mode, "source": "schedule" if scheduled else "manual"}
        await io(self.store.record_event, org_id=org_id, routine_id=routine_id,
                 kind=EventKind.RUN_STARTED.value, actor_id=actor, detail=base)
        collected = drafts = published = duplicates = 0
        item_ids: list[UUID] = []
        try:
            items = list(await self.collector.collect(routine))
            collected = len(items)
            for it in items:
                outcome = await io(self._materialize, routine, it, run_id, auto_publish)
                if outcome is None:
                    duplicates += 1
                    continue
                item_id, was_published = outcome
                item_ids.append(item_id)
                drafts += 1
                published += int(was_published)
        except Exception as exc:  # noqa: BLE001 -- recorded as run_finished(error), then re-raised
            err = f"{type(exc).__name__}: {exc}"[:ERROR_MAX_CHARS]
            logger.exception("routine run failed routine=%s run=%s", routine_id, run_id)
            await io(self.store.record_event, org_id=org_id, routine_id=routine_id,
                     kind=EventKind.RUN_FINISHED.value, actor_id=actor,
                     detail={**base, "status": "error", "error": err, "collected": collected,
                             "drafts": drafts, "published": published, "duplicates": duplicates})
            raise
        await io(self.store.record_event, org_id=org_id, routine_id=routine_id,
                 kind=EventKind.RUN_FINISHED.value, actor_id=actor,
                 detail={**base, "status": "ok", "collected": collected, "drafts": drafts,
                         "published": published, "duplicates": duplicates})
        return RunResult(run_id, routine_id, routine.mode, "ok", collected, drafts, published,
                         duplicates, tuple(item_ids))

    def _materialize(self, routine: Routine, it: RunItem, run_id: UUID, auto_publish: bool):
        """Create the draft, submit it, and (routine mode) publish it. ``None`` = duplicate."""
        try:
            res = self.editorial.create_item(
                org_id=routine.org_id, kind=editorial_kind_of(routine), ref=item_ref(routine.id, it.ref),
                content=it.content, actor_id=SYSTEM_ACTOR, grants=SYSTEM_DRAFT_GRANTS,
            )
        except EditorialConflict:
            return None
        item_id = res.item.id
        self.editorial.apply(org_id=routine.org_id, item_id=item_id, action=Action.SUBMIT.value,
                             actor_id=SYSTEM_ACTOR, grants=SYSTEM_DRAFT_GRANTS)
        self.store.record_event(
            org_id=routine.org_id, routine_id=routine.id, kind=EventKind.DRAFT_CREATED.value,
            actor_id=SYSTEM_ACTOR, detail={"run_id": str(run_id), "item_id": str(item_id), "ref": it.ref})
        if not auto_publish:
            return item_id, False
        self.editorial.apply(org_id=routine.org_id, item_id=item_id, action=Action.PUBLISH.value,
                             actor_id=SYSTEM_ACTOR, grants=SYSTEM_PUBLISH_GRANTS)
        self.store.record_event(
            org_id=routine.org_id, routine_id=routine.id, kind=EventKind.APPROVED.value,
            actor_id=SYSTEM_ACTOR, detail={"run_id": str(run_id), "item_id": str(item_id), "auto": True})
        return item_id, True

    # -- approval (one step) ----------------------------------------------
    def _owned_item(self, org_id: UUID, routine_id: UUID, item_id: UUID):
        item = self.editorial.get_item(org_id, item_id)
        if not item.ref.startswith(f"{routine_id}:"):
            raise RoutineNotFound(f"draft {item_id} does not belong to routine {routine_id}")
        return item

    def approve(self, org_id: UUID, routine_id: UUID, item_id: UUID, *, actor_id: UUID,
                grants: Iterable[str]) -> Any:
        """Owner approves a draft: editorial ``publish`` + the ``approved`` event."""
        self.store.get_routine(org_id, routine_id)
        self._owned_item(org_id, routine_id, item_id)
        res = self.editorial.apply(org_id=org_id, item_id=item_id, action=Action.PUBLISH.value,
                                   actor_id=actor_id, grants=list(grants))
        self.store.record_event(org_id=org_id, routine_id=routine_id, kind=EventKind.APPROVED.value,
                                actor_id=actor_id, detail={"item_id": str(item_id)})
        return res

    def reject(self, org_id: UUID, routine_id: UUID, item_id: UUID, *, actor_id: UUID,
               grants: Iterable[str], reason: str) -> Any:
        """Owner rejects a draft with a REQUIRED reason: editorial ``archive`` (motivo) + ``rejected``."""
        self.store.get_routine(org_id, routine_id)
        self._owned_item(org_id, routine_id, item_id)
        res = self.editorial.apply(org_id=org_id, item_id=item_id, action=Action.ARCHIVE.value,
                                   actor_id=actor_id, grants=list(grants), motivo=reason)
        self.store.record_event(org_id=org_id, routine_id=routine_id, kind=EventKind.REJECTED.value,
                                actor_id=actor_id, reason=reason, detail={"item_id": str(item_id)})
        return res


async def _io(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Store IO is synchronous (supabase-py): never block the loop with it."""
    return await asyncio.to_thread(fn, *args, **kwargs)


__all__ = ["DEFAULT_EDITORIAL_KIND", "RunCollector", "RoutineService", "editorial_kind_of", "item_ref"]

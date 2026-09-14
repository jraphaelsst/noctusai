"""``StoreApprovalBroker`` — the real :class:`~app.runtime.types.ApprovalBroker`
over G1's ``app.stores.approvals`` store (contract §E.9).

One instance per process (``get_approval_broker`` returns a singleton).
``instance_id`` is generated once at construction and is the SAME value
every ``TurnContext`` in this process should carry — G1b's routes read
``broker.instance_id`` when building a ``TurnContext`` so that
``expire_orphans_on_startup`` (instance-scoped) and every pending row this
process creates agree on what "this process" means.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from app.stores.approvals import ApprovalStore
from app.stores.errors import AlreadyDecided, NotFound
from app.runtime.errors import Orphaned
from app.runtime.types import ApprovalDecision, TurnContext

logger = logging.getLogger(__name__)

__all__ = ["StoreApprovalBroker"]


class StoreApprovalBroker:
    """Real :class:`~app.runtime.types.ApprovalBroker`.

    In-process futures are the ONLY thing that makes ``request`` block
    until a human decides (or the timeout fires) — the store is durable
    bookkeeping, not the wake-up mechanism. A process restart therefore
    always orphans every ``pendente`` row it created (there is no future
    left to set), which is exactly what :meth:`expire_orphans_on_startup`
    and the ``Orphaned`` branch of :meth:`resolve` exist for.
    """

    def __init__(
        self,
        store: ApprovalStore,
        *,
        timeout_seconds: int = 900,
        instance_id: str | None = None,
    ) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds
        self.instance_id = instance_id or uuid4().hex
        # approval_id -> the Future `request()` is awaiting on.
        self._pending: dict[UUID, "asyncio.Future[ApprovalDecision]"] = {}

    async def request(
        self,
        ctx: TurnContext,
        *,
        tool_name: str,
        tool_input: dict,
        resumo: str,
        diff: dict | None,
    ) -> ApprovalDecision:
        record = self._store.create_pending(
            ctx.org_id,
            ctx.conversation_id,
            tool_name,
            tool_input,
            resumo,
            ctx.instance_id,
            ctx.requested_by,
            diff=diff,
        )
        future: "asyncio.Future[ApprovalDecision]" = asyncio.get_running_loop().create_future()
        self._pending[record.id] = future
        try:
            return await asyncio.wait_for(future, timeout=self._timeout_seconds)
        except (asyncio.TimeoutError, TimeoutError):
            self._pending.pop(record.id, None)
            self._store.expire_one(record.id)
            logger.warning(
                "approval %s timed out after %ss (tool=%s, conversation=%s)",
                record.id,
                self._timeout_seconds,
                tool_name,
                ctx.conversation_id,
            )
            return ApprovalDecision(
                aprovada=False,
                approval_id=record.id,
                approved_by=None,
                via="timeout",
            )
        finally:
            # Idempotent: a normal resolution already popped this key.
            self._pending.pop(record.id, None)

    async def resolve(
        self, org_id: UUID, approval_id: UUID, *, aprovada: bool, decided_by: UUID
    ) -> dict:
        # 1. NotFound — the row doesn't exist, or belongs to another org.
        record = self._store.get(org_id, approval_id)  # raises NotFound

        # 2. AlreadyDecided — settled (by a human, a timeout, or a prior
        #    restart's sweep) before this call arrived.
        if record.decision != "pendente":
            raise AlreadyDecided(
                f"approval {approval_id} already decided ({record.decision!r})"
            )

        # 3. Orphaned — the row is genuinely still pendente, but no live
        #    `request()` call in THIS process is waiting on it (the
        #    process that created it restarted, or this is a different
        #    process instance entirely).
        future = self._pending.get(approval_id)
        if future is None or future.done():
            raise Orphaned(
                f"approval {approval_id} has no live request() waiter in this process"
            )

        # Only now does the write happen. `decide()` re-validates
        # `decision == 'pendente'` itself (a concurrent decision landing
        # between step 2 and here raises AlreadyDecided from the store,
        # which is still the correct classification — just discovered a
        # moment later).
        updated = self._store.decide(org_id, approval_id, aprovada, decided_by)

        decision = ApprovalDecision(
            aprovada=aprovada,
            approval_id=approval_id,
            approved_by=decided_by,
            via="web",
        )
        if not future.done():
            future.set_result(decision)
        self._pending.pop(approval_id, None)

        return {
            "id": updated.id,
            "org_id": updated.org_id,
            "conversation_id": updated.conversation_id,
            "tool_name": updated.tool_name,
            "tool_input": updated.tool_input,
            "classe": updated.classe,
            "resumo": updated.resumo,
            "diff": updated.diff,
            "decision": updated.decision,
            "decided_by": updated.decided_by,
            "decided_at": updated.decided_at,
            "requested_by": updated.requested_by,
            "instance_id": updated.instance_id,
            "consumed_at": updated.consumed_at,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
        }

    async def expire_orphans_on_startup(self) -> int:
        """Flip every ``pendente`` row THIS instance owns to ``expirada``.

        Called once at process boot, before any turn runs. Correctness
        depends on ``self.instance_id`` being STABLE across THIS
        deployment slot's restarts (so a crash-restart sweeps the exact
        rows its previous life orphaned) — see the sourcing note on
        :func:`app.runtime.get_approval_broker`. Given that, "every
        pendente row for this instance_id" is by definition orphaned at
        startup: nothing in a brand-new process can hold a live
        ``request()`` future for a row created before this boot. Never
        touches another instance's rows (contract §E.2 / security
        finding 5) — ``expire_for_instance`` is scoped by construction.
        """
        return self._store.expire_for_instance(self.instance_id)

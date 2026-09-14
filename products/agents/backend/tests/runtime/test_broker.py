"""``StoreApprovalBroker`` — timeout, resolve ordering, instance-scoped
startup expiry (contract §E.9)."""
import asyncio
from uuid import uuid4

import pytest

from app.runtime.broker import StoreApprovalBroker
from app.runtime.errors import Orphaned
from app.runtime.types import TurnContext
from app.stores.approvals import FakeApprovalStore
from app.stores.errors import AlreadyDecided, NotFound


def _ctx(*, instance_id: str = "inst-1") -> TurnContext:
    return TurnContext(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id=instance_id,
        sdk_session_id=None,
    )


class TestRequestTimeout:
    @pytest.mark.asyncio
    async def test_unanswered_request_times_out_denied(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=0.05, instance_id="inst-1")
        ctx = _ctx()

        decision = await broker.request(
            ctx,
            tool_name="mcp__academia__kb_escrever",
            tool_input={"titulo": "t"},
            resumo="r",
            diff=None,
        )

        assert decision.aprovada is False
        assert decision.via == "timeout"
        assert decision.approved_by is None

    @pytest.mark.asyncio
    async def test_timeout_expires_the_store_row(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=0.05, instance_id="inst-1")
        ctx = _ctx()

        decision = await broker.request(
            ctx, tool_name="mcp__academia__kb_escrever", tool_input={}, resumo="r", diff=None
        )
        row = store.get(ctx.org_id, decision.approval_id)
        assert row.decision == "expirada"

    @pytest.mark.asyncio
    async def test_request_creates_a_pending_row_with_instance_and_diff(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=5, instance_id="inst-1")
        ctx = _ctx(instance_id="inst-1")

        async def approve_soon():
            await asyncio.sleep(0.01)
            pending = store.list_pending(ctx.org_id)
            row = pending[0]
            assert row.instance_id == "inst-1"
            assert row.diff == {"antes": "a", "depois": "b"}
            await broker.resolve(ctx.org_id, row.id, aprovada=True, decided_by=uuid4())

        task = asyncio.create_task(approve_soon())
        decision = await broker.request(
            ctx,
            tool_name="mcp__academia__kb_escrever",
            tool_input={"titulo": "t"},
            resumo="r",
            diff={"antes": "a", "depois": "b"},
        )
        await task
        assert decision.aprovada is True
        assert decision.via == "web"


class TestResolveOrdering:
    @pytest.mark.asyncio
    async def test_unknown_id_raises_not_found(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, instance_id="inst-1")
        ctx = _ctx()
        with pytest.raises(NotFound):
            await broker.resolve(ctx.org_id, uuid4(), aprovada=True, decided_by=uuid4())

    @pytest.mark.asyncio
    async def test_wrong_org_raises_not_found(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=5, instance_id="inst-1")
        ctx = _ctx()

        async def race():
            await asyncio.sleep(0.01)
            row = store.list_pending(ctx.org_id)[0]
            with pytest.raises(NotFound):
                await broker.resolve(uuid4(), row.id, aprovada=True, decided_by=uuid4())
            # Clean up so request() doesn't hang the test.
            await broker.resolve(ctx.org_id, row.id, aprovada=True, decided_by=uuid4())

        task = asyncio.create_task(race())
        await broker.request(ctx, tool_name="x", tool_input={}, resumo="r", diff=None)
        await task

    @pytest.mark.asyncio
    async def test_already_decided_takes_priority_over_orphaned(self):
        """A row that is BOTH settled AND has no live future (it was
        resolved once, its future already popped) must report
        AlreadyDecided, never Orphaned — NotFound -> AlreadyDecided ->
        Orphaned is the fixed priority order (contract §E.9)."""
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=5, instance_id="inst-1")
        ctx = _ctx()

        async def decide_twice():
            await asyncio.sleep(0.01)
            row = store.list_pending(ctx.org_id)[0]
            await broker.resolve(ctx.org_id, row.id, aprovada=True, decided_by=uuid4())
            with pytest.raises(AlreadyDecided):
                await broker.resolve(ctx.org_id, row.id, aprovada=False, decided_by=uuid4())

        task = asyncio.create_task(decide_twice())
        await broker.request(ctx, tool_name="x", tool_input={}, resumo="r", diff=None)
        await task

    @pytest.mark.asyncio
    async def test_orphaned_when_pendente_but_no_live_future(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, instance_id="inst-1")
        ctx = _ctx()
        # Created directly on the store — no broker.request() future exists.
        row = store.create_pending(
            ctx.org_id, ctx.conversation_id, "x", {}, "r", "inst-1", ctx.requested_by
        )
        with pytest.raises(Orphaned):
            await broker.resolve(ctx.org_id, row.id, aprovada=True, decided_by=uuid4())

    @pytest.mark.asyncio
    async def test_resolve_sets_the_waiting_future(self):
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=5, instance_id="inst-1")
        ctx = _ctx()
        decided_by = uuid4()

        async def approve_soon():
            await asyncio.sleep(0.01)
            row = store.list_pending(ctx.org_id)[0]
            await broker.resolve(ctx.org_id, row.id, aprovada=False, decided_by=decided_by)

        task = asyncio.create_task(approve_soon())
        decision = await broker.request(
            ctx, tool_name="x", tool_input={}, resumo="r", diff=None
        )
        await task
        assert decision.aprovada is False
        assert decision.approved_by == decided_by
        assert decision.via == "web"


class TestExpireOrphansOnStartup:
    @pytest.mark.asyncio
    async def test_expires_only_this_instance(self):
        store = FakeApprovalStore()
        org_id = uuid4()
        conv_id = uuid4()
        requester = uuid4()
        row_a = store.create_pending(org_id, conv_id, "x", {}, "r", "inst-A", requester)
        row_b = store.create_pending(org_id, conv_id, "x", {}, "r", "inst-B", requester)

        broker_a = StoreApprovalBroker(store, instance_id="inst-A")
        count = await broker_a.expire_orphans_on_startup()

        assert count == 1
        assert store.get(org_id, row_a.id).decision == "expirada"
        assert store.get(org_id, row_b.id).decision == "pendente"

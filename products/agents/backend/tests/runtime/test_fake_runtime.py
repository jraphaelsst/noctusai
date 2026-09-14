"""``FakeAgentRuntime`` — event guarantees (contract §E.9), including the
approve and deny escrita paths."""
import asyncio
from uuid import uuid4

import pytest

from app.runtime.broker import StoreApprovalBroker
from app.runtime.fake_runtime import FakeAgentRuntime
from app.runtime.types import TurnContext
from app.stores.approvals import FakeApprovalStore


def _ctx() -> TurnContext:
    return TurnContext(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id="inst-1",
        sdk_session_id=None,
    )


async def _drive_and_decide(runtime, ctx, broker, *, aprovada: bool):
    events = []

    async def approve_soon():
        # Let request() create the pending row first.
        for _ in range(50):
            pending = broker._store.list_pending(ctx.org_id)  # test-only introspection
            if pending:
                break
            await asyncio.sleep(0)
        row = pending[0]
        await broker.resolve(ctx.org_id, row.id, aprovada=aprovada, decided_by=uuid4())

    task = asyncio.create_task(approve_soon())
    async for event in runtime.run_turn(spec=None, ctx=ctx, prompt="oi", broker=broker):
        events.append(event)
    await task
    return events


class TestPlainEvents:
    @pytest.mark.asyncio
    async def test_plain_events_are_yielded_verbatim_then_session_status(self):
        script = [
            {"event": "message.new", "payload": {"role": "assistant", "texto": "oi", "blocks": []}},
        ]
        runtime = FakeAgentRuntime(script)
        ctx = _ctx()
        broker = StoreApprovalBroker(FakeApprovalStore(), instance_id="inst-1")

        events = [e async for e in runtime.run_turn(spec=None, ctx=ctx, prompt="oi", broker=broker)]

        assert events[0] == script[0]
        assert events[-1]["event"] == "session.status"
        assert events[-1]["payload"]["status"] == "ociosa"

    @pytest.mark.asyncio
    async def test_last_event_is_always_session_status(self):
        runtime = FakeAgentRuntime([])
        ctx = _ctx()
        broker = StoreApprovalBroker(FakeApprovalStore(), instance_id="inst-1")
        events = [e async for e in runtime.run_turn(spec=None, ctx=ctx, prompt="oi", broker=broker)]
        assert len(events) == 1
        assert events[-1]["event"] == "session.status"


class TestEscritaApproved:
    @pytest.mark.asyncio
    async def test_approved_escrita_sequence_and_pairing(self):
        script = [("escrita", "mcp__academia__kb_escrever", {"titulo": "t"})]
        runtime = FakeAgentRuntime(script)
        ctx = _ctx()
        broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=5, instance_id="inst-1")

        events = await _drive_and_decide(runtime, ctx, broker, aprovada=True)
        names = [e["event"] for e in events]
        assert names == [
            "tool.started",
            "approval.requested",
            "approval.resolved",
            "tool.finished",
            "session.status",
        ]
        started, finished = events[0], events[3]
        assert started["payload"]["tool_use_id"] == finished["payload"]["tool_use_id"]
        assert finished["payload"]["resultado"] == "ok"
        assert events[2]["payload"]["decision"] == "aprovada"


class TestEscritaDenied:
    @pytest.mark.asyncio
    async def test_denied_escrita_tool_finished_is_negada(self):
        script = [("escrita", "mcp__academia__kb_escrever", {"titulo": "t"})]
        runtime = FakeAgentRuntime(script)
        ctx = _ctx()
        broker = StoreApprovalBroker(FakeApprovalStore(), timeout_seconds=5, instance_id="inst-1")

        events = await _drive_and_decide(runtime, ctx, broker, aprovada=False)
        names = [e["event"] for e in events]
        assert names == [
            "tool.started",
            "approval.requested",
            "approval.resolved",
            "tool.finished",
            "session.status",
        ]
        assert events[3]["payload"]["resultado"] == "negada"
        assert events[2]["payload"]["decision"] == "negada"


class TestMultipleEscritaCalls:
    @pytest.mark.asyncio
    async def test_two_escrita_calls_each_pair_independently(self):
        script = [
            ("escrita", "mcp__academia__kb_escrever", {"titulo": "a"}),
            ("escrita", "mcp__academia__decisao_registrar", {"titulo": "b"}),
        ]
        runtime = FakeAgentRuntime(script)
        ctx = _ctx()
        store = FakeApprovalStore()
        broker = StoreApprovalBroker(store, timeout_seconds=5, instance_id="inst-1")

        async def approve_each():
            approved = set()
            while len(approved) < 2:
                pending = [
                    r for r in store.list_pending(ctx.org_id) if r.id not in approved
                ]
                if not pending:
                    await asyncio.sleep(0)
                    continue
                row = pending[0]
                await broker.resolve(ctx.org_id, row.id, aprovada=True, decided_by=uuid4())
                approved.add(row.id)

        task = asyncio.create_task(approve_each())
        events = [
            e async for e in runtime.run_turn(spec=None, ctx=ctx, prompt="oi", broker=broker)
        ]
        await task

        starts = [e for e in events if e["event"] == "tool.started"]
        finishes = [e for e in events if e["event"] == "tool.finished"]
        assert len(starts) == 2
        assert len(finishes) == 2
        assert {s["payload"]["tool_use_id"] for s in starts} == {
            f["payload"]["tool_use_id"] for f in finishes
        }

    @pytest.mark.asyncio
    async def test_unknown_script_marker_raises(self):
        runtime = FakeAgentRuntime([("bogus", "x", {})])
        ctx = _ctx()
        broker = StoreApprovalBroker(FakeApprovalStore(), instance_id="inst-1")
        with pytest.raises(ValueError):
            async for _ in runtime.run_turn(spec=None, ctx=ctx, prompt="oi", broker=broker):
                pass

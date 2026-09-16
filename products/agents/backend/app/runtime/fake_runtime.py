"""``FakeAgentRuntime`` — the dev/test :class:`~app.runtime.types.AgentRuntime`
(contract §E.9). Scriptable: a plain :class:`AgentEvent` dict is yielded
verbatim; a ``("escrita", tool_name, tool_input)`` tuple drives the REAL
broker exactly as ``can_use_tool`` would (calls
:meth:`~app.runtime.types.ApprovalBroker.request`, waits for the
decision), so G1b's route tests exercise the real approval flow without
an LLM.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from app.runtime import gate
from app.runtime.slots import DEFAULT_SLOT_COUNT, FakeSlotPool, TurnSlot
from app.runtime.types import (
    AgentEvent,
    AgentSpec,
    ApprovalBroker,
    TurnContext,
    approval_event_payload,
)
from app.stores.approvals import ApprovalRecord

__all__ = ["FakeAgentRuntime"]

# A scripted entry is either a ready-made event, or a 3-/4-tuple describing
# an escrita tool call the fake should route through the real broker. The
# optional 4th element is the `diff` the approval card would show (contract
# §E.4) — defaults to `None` when omitted, matching every pre-existing
# 3-tuple script.
ScriptItem = (
    AgentEvent
    | tuple[str, str, dict[str, Any]]
    | tuple[str, str, dict[str, Any], "dict[str, Any] | None"]
)


class FakeAgentRuntime:
    """``AgentRuntime`` for dev/test. Never spawns a subprocess, never
    calls any LLM.

    Contract §E.11: ``try_reserve()`` leases from an internal
    :class:`~app.runtime.slots.FakeSlotPool` sized by ``capacity``
    (default :data:`~app.runtime.slots.DEFAULT_SLOT_COUNT`, matching the
    real deploy's 3 slots) — dependency-inversion mirror of how the real
    runtime will hold its own :class:`~app.runtime.slots.RealSlotPool`
    (B3). ``run_turn``'s ``slot`` parameter is accepted for signature
    parity with the real runtime; this fake never spawns a subprocess, so
    it has nothing to do with the slot beyond accepting it.
    """

    def __init__(self, script: list[ScriptItem], *, capacity: int = DEFAULT_SLOT_COUNT) -> None:
        self._script = list(script)
        self._pool = FakeSlotPool(capacity)

    def try_reserve(self) -> TurnSlot | None:
        return self._pool.try_reserve()

    async def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
        slot: TurnSlot | None = None,
    ) -> AsyncIterator[AgentEvent]:
        for item in self._script:
            if isinstance(item, tuple):
                async for event in self._drive_escrita(item, ctx, broker):
                    yield event
            else:
                yield item

        yield {
            "event": "session.status",
            "payload": {
                "status": "ociosa",
                "sdk_session_id": ctx.sdk_session_id or f"fake-session-{uuid4().hex[:8]}",
            },
        }

    async def _drive_escrita(
        self,
        item: tuple[str, str, dict[str, Any]] | tuple[str, str, dict[str, Any], dict[str, Any] | None],
        ctx: TurnContext,
        broker: ApprovalBroker,
    ) -> AsyncIterator[AgentEvent]:
        diff: dict[str, Any] | None = None
        if len(item) == 4:
            _marker, tool_name, tool_input, diff = item
        else:
            _marker, tool_name, tool_input = item
        if _marker != "escrita":
            raise ValueError(f"unknown FakeAgentRuntime script tuple marker: {_marker!r}")

        tool_use_id = f"fake-{uuid4().hex[:8]}"
        resumo_text = gate.resumo(tool_name, tool_input)

        # Same ordering the real runtime guarantees (contract §E.9 /
        # verified against §G's E2E check: tool.started, then
        # approval.requested, then approval.resolved, then tool.finished).
        yield {
            "event": "tool.started",
            "payload": {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "classe": "escrita",
                "resumo": resumo_text,
            },
        }

        # `on_created` runs synchronously inside `broker.request()`, before
        # it starts waiting — by the time `request()` returns below, the
        # created record is already captured. Yielding "approval.requested"
        # here (rather than from inside the callback, which isn't a
        # generator) preserves the exact §E.9 event ORDER without needing
        # the real runtime's queue machinery, since this fake never
        # publishes concurrently with another task the way the SDK's
        # message pump does.
        created: dict[str, ApprovalRecord] = {}

        async def on_created(record: ApprovalRecord) -> None:
            created["record"] = record

        decision = await broker.request(
            ctx,
            tool_name=tool_name,
            tool_input=tool_input,
            resumo=resumo_text,
            diff=diff,
            on_created=on_created,
        )

        yield {
            "event": "approval.requested",
            "payload": approval_event_payload(created["record"]),
        }
        yield {
            "event": "approval.resolved",
            "payload": {
                "approval_id": str(decision.approval_id),
                "decision": "aprovada" if decision.aprovada else "negada",
                "decided_by": str(decision.approved_by) if decision.approved_by else None,
            },
        }
        yield {
            "event": "tool.finished",
            "payload": {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "resultado": "ok" if decision.aprovada else "negada",
            },
        }

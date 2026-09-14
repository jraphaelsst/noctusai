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
from app.runtime.types import AgentEvent, AgentSpec, ApprovalBroker, TurnContext

__all__ = ["FakeAgentRuntime"]

# A scripted entry is either a ready-made event, or a 3-tuple describing an
# escrita tool call the fake should route through the real broker.
ScriptItem = AgentEvent | tuple[str, str, dict[str, Any]]


class FakeAgentRuntime:
    """``AgentRuntime`` for dev/test. Never spawns a subprocess, never
    calls any LLM."""

    def __init__(self, script: list[ScriptItem]) -> None:
        self._script = list(script)

    async def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
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
        item: tuple[str, str, dict[str, Any]],
        ctx: TurnContext,
        broker: ApprovalBroker,
    ) -> AsyncIterator[AgentEvent]:
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
        yield {
            "event": "approval.requested",
            "payload": {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "resumo": resumo_text,
                "diff": None,
            },
        }

        decision = await broker.request(
            ctx,
            tool_name=tool_name,
            tool_input=tool_input,
            resumo=resumo_text,
            diff=None,
        )

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

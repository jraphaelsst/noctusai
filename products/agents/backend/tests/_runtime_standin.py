"""TEST-ONLY stand-in for the contract §E.9 runtime seam
(``projects/julia-agents-academia-CONTRACT.md``, ``products/agents/backend/
app/runtime/`` — G2's slice, absent on this branch's base).

Implements the §E.9 Protocols **verbatim** (same method signatures, same
event/payload shapes) over the REAL G1 stores (``ApprovalStore`` /
``ConversationStore``) rather than a bare dict — router tests exercise the
actual persistence + turn-lock semantics with zero LLM / zero real
``app.runtime`` dependency.

Injected via FastAPI dependency overrides
(``app.dependency_overrides[get_agent_runtime_dep] = lambda: fake_runtime``
etc.) — a dependency seam, never monkeypatching our own code. The
tech-lead swaps this module out for G2's real Fakes at integration; nothing
here is imported by production code.

Usage
-----

>>> runtime = FakeAgentRuntime([
...     {"event": "message.new", "payload": {"texto": "Oi! Como posso ajudar?"}},
...     ("escrita", "mcp__academia__kb_escrever", {"slug": "x", "corpo_md": "y"}),
...     {"event": "session.status", "payload": {"status": "ociosa", "sdk_session_id": "sdk-1"}},
... ])
>>> broker = InProcessApprovalBroker(approval_store, conversation_store, instance_id="test")
>>> app.dependency_overrides[get_agent_runtime_dep] = lambda: runtime
>>> app.dependency_overrides[get_approval_broker_dep] = lambda: broker
>>> app.dependency_overrides[get_build_julia_spec_dep] = lambda: (lambda persona: FakeAgentSpec(persona))
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal
from uuid import UUID

# ── Duck-typed AgentEvent / ApprovalDecision / AgentSpec — field-identical
# to contract §E.9's ``runtime/types.py``, owned here (never imported from
# ``app.runtime``, which does not exist on this branch's base). ──────────


@dataclass(frozen=True)
class ApprovalDecision:
    aprovada: bool
    approval_id: UUID
    approved_by: UUID | None
    via: Literal["web", "timeout", "restart"] = "web"


@dataclass(frozen=True)
class FakeAgentSpec:
    """Stand-in ``AgentSpec`` — carries just enough of the persona row for
    a test assertion to inspect, never a real prompt/tool composition
    (that's G2's ``build_julia_spec``, contract §E.9)."""

    key: str = "julia"
    model: str = "claude-sonnet-5"
    effort: str = "medium"
    prompt_append: str = ""
    skills: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    max_turns: int = 40
    persona: Any = None


def fake_build_julia_spec(persona_row: Any) -> FakeAgentSpec:
    """Stand-in for ``app.runtime.build_julia_spec`` — same one-arg
    signature, returns a :class:`FakeAgentSpec` instead of a real
    ``AgentSpec``. Pass this via
    ``app.dependency_overrides[get_build_julia_spec_dep] = lambda: fake_build_julia_spec``."""
    return FakeAgentSpec(
        model=getattr(persona_row, "model", "claude-sonnet-5"),
        effort=getattr(persona_row, "effort", "medium"),
        persona=persona_row,
    )


ScriptEntry = dict | tuple


class FakeAgentRuntime:
    """Scriptable stand-in for the contract §E.9 ``AgentRuntime`` Protocol.

    ``script`` is a list of either:
      - a plain ``{"event": <E.3 name>, "payload": {...}}`` dict, yielded
        as-is; or
      - a ``("escrita", tool_name, tool_input)`` tuple — calls
        ``broker.request(ctx, tool_name=..., tool_input=..., resumo=...,
        diff=None)`` and emits the fixed escrita sequence the real runtime
        must guarantee (contract §E.9 "What the runtime must guarantee"):
        ``tool.started`` -> ``approval.requested`` -> (await the broker's
        decision) -> ``approval.resolved`` -> ``tool.finished`` with
        ``resultado`` "ok" when approved, "negada" otherwise.

    A trailing ``session.status`` entry is REQUIRED in ``script`` (contract:
    "The last event is always session.status") — not auto-appended, so a
    test that forgets it gets a loud assertion failure instead of a
    silently-passing gap.
    """

    def __init__(self, script: list[ScriptEntry]) -> None:
        self._script = list(script)

    async def run_turn(
        self, spec: Any, ctx: Any, prompt: str, broker: Any
    ) -> AsyncIterator[dict[str, Any]]:
        for entry in self._script:
            if isinstance(entry, tuple):
                _classe, tool_name, tool_input = entry
                tool_use_id = f"tool-{uuid.uuid4().hex[:8]}"
                yield {
                    "event": "tool.started",
                    "payload": {
                        "tool_use_id": tool_use_id,
                        "tool_name": tool_name,
                        "classe": "escrita",
                        "resumo": f"Executar {tool_name}",
                    },
                }
                resumo = f"Executar {tool_name}"
                decision: ApprovalDecision = await broker.request(
                    ctx, tool_name=tool_name, tool_input=tool_input, resumo=resumo, diff=None
                )
                yield {
                    "event": "approval.requested",
                    "payload": {
                        "id": str(decision.approval_id),
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "resumo": resumo,
                        "diff": None,
                    },
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
            else:
                yield entry


class InProcessApprovalBroker:
    """TEST-ONLY stand-in for the contract §E.9 ``ApprovalBroker``
    Protocol, implemented over the REAL ``ApprovalStore`` /
    ``ConversationStore`` (G1) — not a bare dict.

    ``auto_decide``:
      - ``True``/``False`` (default ``True``): ``request(...)`` decides
        the approval IMMEDIATELY (attributed to ``ctx.requested_by``) and
        returns without blocking — the deterministic mode most turn-loop
        tests want.
      - ``None``: ``request(...)`` creates the pending row and blocks
        (``asyncio.Event``) until a concurrent ``resolve(...)`` call
        settles it — the mode approvals-router tests use to exercise the
        real ``POST /api/approvals/{id}/decision`` -> unblock-the-turn
        path end-to-end.
    """

    def __init__(
        self,
        approval_store: Any,
        conversation_store: Any,
        *,
        instance_id: str,
        auto_decide: bool | None = True,
    ) -> None:
        self._approvals = approval_store
        self._conversations = conversation_store
        self._instance_id = instance_id
        self.auto_decide = auto_decide
        self._waiters: dict[UUID, asyncio.Event] = {}
        self._decisions: dict[UUID, ApprovalDecision] = {}

    async def request(
        self, ctx: Any, *, tool_name: str, tool_input: dict, resumo: str, diff: dict | None = None
    ) -> ApprovalDecision:
        record = self._approvals.create_pending(
            ctx.org_id,
            ctx.conversation_id,
            tool_name,
            tool_input,
            resumo,
            self._instance_id,
            ctx.requested_by,
            diff=diff,
        )
        if self.auto_decide is not None:
            decided = self._approvals.decide(
                ctx.org_id, record.id, self.auto_decide, ctx.requested_by
            )
            return ApprovalDecision(
                aprovada=self.auto_decide,
                approval_id=decided.id,
                approved_by=ctx.requested_by,
                via="web",
            )

        event = asyncio.Event()
        self._waiters[record.id] = event
        await event.wait()
        decision = self._decisions.pop(record.id)
        self._waiters.pop(record.id, None)
        return decision

    async def resolve(
        self, org_id: UUID, approval_id: UUID, *, aprovada: bool, decided_by: UUID
    ) -> dict:
        record = self._approvals.decide(org_id, approval_id, aprovada, decided_by)
        self._decisions[approval_id] = ApprovalDecision(
            aprovada=aprovada, approval_id=approval_id, approved_by=decided_by, via="web"
        )
        event = self._waiters.get(approval_id)
        if event is not None:
            event.set()
        return {
            "id": record.id,
            "conversation_id": record.conversation_id,
            "tool_name": record.tool_name,
            "tool_input": record.tool_input,
            "classe": record.classe,
            "resumo": record.resumo,
            "diff": record.diff,
            "decision": record.decision,
            "decided_by": record.decided_by,
            "decided_at": record.decided_at,
            "requested_by": record.requested_by,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    async def expire_orphans_on_startup(self) -> int:
        return self._approvals.expire_for_instance(self._instance_id)


__all__ = [
    "ApprovalDecision",
    "FakeAgentRuntime",
    "FakeAgentSpec",
    "InProcessApprovalBroker",
    "fake_build_julia_spec",
]

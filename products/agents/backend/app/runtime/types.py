"""The runtime seam between the agents routes (G1b) and the runtime + gate
(G2) — contract §E.9, ported verbatim from the contract's code block.

Every dataclass/TypedDict/Protocol below is the seam G1b's routes and G2's
runtime + broker implementation both build to. Neither side guesses the
other's shape — this module is read by both.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict
from uuid import UUID

from app.runtime.slots import SlotPool, TurnSlot
from app.stores.approvals import ApprovalRecord

__all__ = [
    "TurnContext",
    "AgentSpec",
    "AgentEvent",
    "ApprovalDecision",
    "ApprovalBroker",
    "TurnSlot",
    "SlotPool",
    "AgentRuntime",
    "approval_event_payload",
]


@dataclass(frozen=True)
class TurnContext:
    """Everything a single conversation turn needs, resolved once by the
    route before ``run_turn`` starts (contract §E.9)."""

    org_id: UUID
    conversation_id: UUID
    requested_by: UUID  # the conversation owner (E.2)
    instance_id: str  # this process; stored on approvals + turn lock
    sdk_session_id: str | None  # conversations.sdk_session_id, for resume


@dataclass(frozen=True)
class AgentSpec:
    """The fully-resolved shape ``build_julia_spec(persona_row)`` returns —
    everything ``ClaudeAgentSdkRuntime`` needs to launch a turn, already
    merged from the active persona row plus Julia's static spec (contract
    §E.5/§E.9)."""

    key: Literal["julia"]
    model: str  # from the active persona, already allowlist-checked
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    prompt_append: str  # JULIA.md + persona fields, composed by build_julia_spec()
    skills: tuple[str, ...]  # explicit ar-* list (E.5)
    tools: tuple[str, ...]  # exactly the E.4 leitura + escrita names
    max_turns: int  # default 40


# `event` is exactly one of the E.3 names. `payload` has exactly the E.3 shape.
AgentEvent = TypedDict("AgentEvent", {"event": str, "payload": dict})


@dataclass(frozen=True)
class ApprovalDecision:
    aprovada: bool
    approval_id: UUID
    approved_by: UUID | None  # None when not decided by a human
    via: Literal["web", "timeout", "restart"]


class ApprovalBroker(Protocol):
    # runtime side, called by G2's can_use_tool for every `escrita` tool.
    # Revision 2026-09-14 (contract §E.9): `on_created` is awaited AFTER the
    # pendente row is persisted and the wake-up future is registered, but
    # BEFORE `request` starts waiting on it — so a decision that lands
    # while `on_created` is still running (e.g. an instant human click)
    # always finds a live future and never raises `Orphaned`. The real
    # runtime uses `on_created` to emit `approval.requested` with the row's
    # real id; `FakeAgentRuntime` uses it to capture the record for the
    # same event.
    async def request(
        self,
        ctx: TurnContext,
        *,
        tool_name: str,
        tool_input: dict,
        resumo: str,
        diff: dict | None,
        on_created: Callable[[ApprovalRecord], Awaitable[None]],
    ) -> ApprovalDecision: ...

    # route side, called by G1b's POST /api/approvals/{id}/decision
    async def resolve(
        self, org_id: UUID, approval_id: UUID, *, aprovada: bool, decided_by: UUID
    ) -> dict:  # the updated approvals row
        """
        raises stores.errors.AlreadyDecided -> 409 already_decided
        raises runtime.errors.Orphaned      -> 409 orphaned
        raises stores.errors.NotFound       -> 404
        """
        ...

    async def expire_orphans_on_startup(self) -> int:  # only rows with this instance_id
        ...


class AgentRuntime(Protocol):
    """Contract §E.9, extended by §E.11 (per-conversation isolation)."""

    def try_reserve(self) -> TurnSlot | None:
        """Lease a free slot from this runtime's internal
        :class:`SlotPool`, or ``None`` when every slot is busy (the
        route's 429 ``julia_capacidade``). Synchronous — see
        ``SlotPool.try_reserve``'s own docstring for why."""
        ...

    def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
        slot: TurnSlot | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """``slot`` defaults to ``None`` for backward compatibility with
        callers that predate contract §E.11 (the route wiring that
        reserves a slot and threads it through lands in a later slice,
        B4) — every REAL turn is expected to pass the slot
        ``try_reserve()`` returned. Reported as a deliberate,
        forward-compatible deviation from the contract's bare
        ``run_turn(spec, ctx, prompt, broker, slot)`` signature; see B1's
        delivery note."""
        ...


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def approval_event_payload(record: ApprovalRecord) -> dict[str, Any]:
    """The full ``Approval`` JSON for ``approval.requested`` (contract
    §E.3/§E.9: "emitted from inside on_created, with the full Approval").

    Same field set as ``app.schemas.agents.ApprovalOut`` — deliberately
    NOT including ``message_id`` (contract §E.9 point 3: "the runtime's
    own event payloads do not carry it" — the ROUTE adds it) nor
    ``org_id``/``instance_id``/``consumed_at`` (store-internal, never
    published). Shared by the real runtime and ``FakeAgentRuntime`` so
    both emit byte-identical shapes for the same record.
    """
    return {
        "id": str(record.id),
        "conversation_id": str(record.conversation_id),
        "tool_name": record.tool_name,
        "tool_input": dict(record.tool_input),
        "classe": record.classe,
        "resumo": record.resumo,
        "diff": record.diff,
        "decision": record.decision,
        "decided_by": str(record.decided_by) if record.decided_by else None,
        "decided_at": _iso(record.decided_at),
        "requested_by": str(record.requested_by),
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }

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
    #: Agent Studio §E6: an eval case's turn runs under a context that is
    #: NOT a user conversation — ``conversation_id`` is a throwaway id with
    #: no ``agents.conversations`` row, so the real runtime must neither
    #: resume nor mirror a durable transcript for it (the transcript table
    #: FKs the conversation). ``False`` for every route-driven turn.
    ephemeral: bool = False


@dataclass(frozen=True)
class AgentSpec:
    """Everything ``ClaudeAgentSdkRuntime`` needs to launch a turn.

    Two producers (Agent Studio contract §E1 — generic, backward
    compatible): ``build_julia_spec(persona_row)`` (Julia, the legacy
    path: ``prompt_mode="preset_append"``, ``toolset="academia"`` — every
    field below that has a default keeps Julia's launch byte-identical)
    and ``app.studio.spec.build_studio_spec`` (a studio agent:
    ``prompt_mode="custom"``, ``toolset="studio"``, the pinned version's
    compiled prompt in ``prompt_append``)."""

    key: str
    model: str  # allowlist-checked by the producer (persona / studio version)
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    prompt_append: str  # the text written to the slot's append.md handoff
    skills: tuple[str, ...]  # SDK plugin skills (Julia's ar-* list); () for studio
    tools: tuple[str, ...]  # the tool names this spec may call
    max_turns: int  # default 40
    prompt_mode: Literal["preset_append", "custom"] = "preset_append"
    toolset: Literal["academia", "studio"] = "academia"
    agent_id: UUID | None = None
    version_id: UUID | None = None
    #: ``"sha256:<hex>"`` of EXACTLY ``prompt_append`` (studio) — the value
    #: stamped on the assistant message (§A7 proof of use).
    compiled_hash: str | None = None
    web_search: bool = True
    #: Studio ``tool_policy.knowledge`` — when ``False`` the ``kb_*`` tools
    #: are not registered at all (additive to §E1).
    knowledge: bool = True
    #: The conversation's client brain, when one is bound (studio only).
    client_id: UUID | None = None


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

"""The runtime seam between the agents routes (G1b) and the runtime + gate
(G2) — contract §E.9, ported verbatim from the contract's code block.

Every dataclass/TypedDict/Protocol below is the seam G1b's routes and G2's
runtime + broker implementation both build to. Neither side guesses the
other's shape — this module is read by both.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict
from uuid import UUID

__all__ = [
    "TurnContext",
    "AgentSpec",
    "AgentEvent",
    "ApprovalDecision",
    "ApprovalBroker",
    "AgentRuntime",
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
    # runtime side, called by G2's can_use_tool for every `escrita` tool
    async def request(
        self,
        ctx: TurnContext,
        *,
        tool_name: str,
        tool_input: dict,
        resumo: str,
        diff: dict | None,
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
    def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
    ) -> AsyncIterator[AgentEvent]: ...

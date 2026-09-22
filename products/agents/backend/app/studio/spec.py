"""``build_studio_spec`` — the studio half of the runtime seam (Agent Studio
contract §E2, §A4, §A7).

Loads the conversation's PINNED version bundle (+ its bound client brain),
compiles it with THE compiler (via the same ``compile_version`` helper the
inspector and publish routes use — one composition path, §A4), stores the
exact text once per hash in ``compiled_prompts`` (proof of use, §A7) and
returns the :class:`~app.runtime.types.AgentSpec` the runtime launches.

``spec.prompt_append`` IS the string written to the slot's ``append.md`` and
``spec.compiled_hash`` is ``sha256`` of exactly that string — the value the
turn loop stamps on the assistant message.

Refusals are typed (:class:`StudioSpecError` with the §D 409 ``code``) so the
conversation route can answer BEFORE it accepts the turn (202):
``prompt_too_large`` (never truncated), ``invalid_client`` /
``client_inactive``, ``version_mismatch``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.runtime.types import AgentSpec
from app.stores.errors import NotFound
from app.studio.tools import studio_allowed_tools

__all__ = [
    "MAX_COMPILED_PROMPT_CHARS",
    "StudioSpecError",
    "StudioTurnTarget",
    "build_studio_spec",
]

#: Security review of wave 1: a compiled prompt above this size refuses the
#: turn (409 ``prompt_too_large``) — it is never truncated.
MAX_COMPILED_PROMPT_CHARS = 60_000


class StudioSpecError(Exception):
    """A studio turn that must not start. ``code`` is the §D error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class StudioTurnTarget:
    """What :func:`build_studio_spec` reads off a conversation — a
    ``ConversationRecord`` satisfies it structurally; the eval runner (which
    has no conversation row) passes one of these."""

    org_id: UUID
    version_id: UUID | None
    client_id: UUID | None = None


def _policy_flag(policy: dict[str, Any], key: str) -> bool:
    return bool((policy or {}).get(key, True))


def build_studio_spec(
    agent: Any,
    conversation: Any,
    *,
    definitions: Any,
    catalog: Any,
    persist: bool = True,
) -> AgentSpec:
    """The :class:`AgentSpec` for one studio turn (contract §E2).

    ``agent`` is a ``StudioAgentRecord``; ``conversation`` anything with
    ``org_id`` / ``version_id`` / ``client_id``. ``persist=False`` skips the
    ``compiled_prompts`` upsert — the eval runner's ephemeral turns judge a
    DRAFT, and a stored prompt referencing the draft would make it
    undiscardable (``draft_referenced``) for no proof-of-use benefit (the run
    itself records the judged ``compiled_hash``)."""
    # Lazy: the compile helpers live beside BE-DEF's inspector/publish routes
    # (the ONE composition path, §A4); importing them at module scope would
    # pull the router into every runtime import.
    from app.routers.studio_agents_router import client_bundle, compile_version

    org_id = conversation.org_id
    if conversation.version_id is None:
        raise StudioSpecError("no_active_version", "O agente não tem versão publicada.")
    version = definitions.get_version(org_id, conversation.version_id)
    if version.agent_id != agent.id:
        raise StudioSpecError("version_mismatch", "A versão não pertence a este agente.")

    client = None
    client_id = getattr(conversation, "client_id", None)
    if client_id is not None:
        try:
            record = definitions.get_client(org_id, client_id)
        except NotFound as exc:
            raise StudioSpecError("invalid_client", "Cliente inválido para este agente.") from exc
        if record.agent_id != agent.id:
            raise StudioSpecError("invalid_client", "Cliente inválido para este agente.")
        if not record.ativo:
            raise StudioSpecError("client_inactive", "O cliente desta conversa está desativado.")
        client = client_bundle(definitions, org_id, record)

    compiled = compile_version(definitions, catalog, org_id, agent, version, client)
    if len(compiled.texto) > MAX_COMPILED_PROMPT_CHARS:
        raise StudioSpecError(
            "prompt_too_large",
            f"O prompt compilado tem {len(compiled.texto)} caracteres; o máximo por turno é "
            f"{MAX_COMPILED_PROMPT_CHARS}.",
        )

    if persist:
        # Write-once per (org, hash); an existing row is returned untouched.
        definitions.save_compiled_prompt(
            org_id,
            hash=compiled.hash,
            version_id=version.id,
            client_id=client_id,
            texto=compiled.texto,
            manifest=compiled.manifest_json(),
        )

    policy = dict(version.tool_policy or {})
    web_search = _policy_flag(policy, "web_search")
    knowledge = _policy_flag(policy, "knowledge")
    return AgentSpec(
        key=agent.key,
        model=version.model,
        effort=version.effort,
        prompt_append=compiled.texto,
        skills=(),
        tools=studio_allowed_tools(knowledge=knowledge, web_search=web_search),
        max_turns=version.max_turns,
        prompt_mode="custom",
        toolset="studio",
        agent_id=agent.id,
        version_id=version.id,
        compiled_hash=compiled.hash,
        web_search=web_search,
        knowledge=knowledge,
        client_id=client_id,
    )

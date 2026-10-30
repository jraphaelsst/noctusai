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
from app.studio.bundles import client_bundle, compile_version
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
    org_specs: dict[str, str] | None = None,
) -> AgentSpec:
    """The :class:`AgentSpec` for one studio turn (contract §E2).

    ``agent`` is the row that OWNS the version: a ``StudioAgentRecord`` of the conversation's org, or -- for an org
    INSTANCE of a platform-defined agent (agents-unified Renata cutover) -- the platform DEFINITION, with
    ``org_specs`` = the instance org's spec values (the definition compiled FOR that org, like
    ``app.studio.resolucao.compile_for_org``). Every version read, the compile and the proof-of-use row use the
    owner's org (``agent.org_id``). ``conversation`` anything with
    ``org_id`` / ``version_id`` / ``client_id``. ``persist=False`` skips the
    ``compiled_prompts`` upsert — the eval runner's ephemeral turns judge a
    DRAFT, and a stored prompt referencing the draft would make it
    undiscardable (``draft_referenced``) for no proof-of-use benefit (the run
    itself records the judged ``compiled_hash``)."""
    # The org that owns the version's rows: the conversation's org for an org agent, the platform org for an
    # instance's definition.
    org_id = agent.org_id
    instancia = agent.org_id != conversation.org_id
    if conversation.version_id is None:
        raise StudioSpecError("no_active_version", "O agente não tem versão publicada.")
    version = definitions.get_version(org_id, conversation.version_id)
    if version.agent_id != agent.id:
        raise StudioSpecError("version_mismatch", "A versão não pertence a este agente.")
    if version.provider != "anthropic" and agent.runtime != "llm":
        # Only the provider-neutral runtime can serve a non-Anthropic version;
        # the Claude Agent SDK runtime would silently run it on Anthropic.
        raise StudioSpecError(
            "provider_runtime_mismatch",
            f"A versão usa o provedor {version.provider}, mas este agente não roda no executor neutro.",
        )

    client = None
    client_id = getattr(conversation, "client_id", None)
    if client_id is not None and instancia:
        # Client brains belong to an org's OWN Studio agent; an instance has none.
        raise StudioSpecError("invalid_client", "Cliente inválido para este agente.")
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

    compiled = compile_version(definitions, catalog, org_id, agent, version, client, org_specs=org_specs)
    if len(compiled.texto) > MAX_COMPILED_PROMPT_CHARS:
        raise StudioSpecError(
            "prompt_too_large",
            f"O prompt compilado tem {len(compiled.texto)} caracteres; o máximo por turno é "
            f"{MAX_COMPILED_PROMPT_CHARS}.",
        )

    ferramentas_grupo = _ferramentas_grupo(compiled)
    exigir_executor_do_grupo(ferramentas_grupo, agent.runtime)

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
        provider=version.provider,
        runtime="llm" if agent.runtime == "llm" else "claude_sdk",
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
        ferramentas_grupo=ferramentas_grupo,
        definicao_org_id=org_id,
    )


def exigir_executor_do_grupo(ferramentas_grupo: tuple[tuple[str, str], ...], runtime: str) -> None:
    """Tool groups run ONLY on the claude_sdk runtime, whose approval broker gates every write tool; the
    provider-neutral runtime (``llm``) has no approval flow, so it is never handed one -- refused before anything
    is persisted."""
    if ferramentas_grupo and runtime != "claude_sdk":
        raise StudioSpecError(
            "ferramentas_exigem_claude_sdk",
            "As ferramentas de grupo (ex.: academia) só rodam no executor claude_sdk, que pede aprovação humana "
            "para toda escrita.",
        )


def _ferramentas_grupo(compiled: Any) -> tuple[tuple[str, str], ...]:
    """The tool-group tools the version's ACTIVE ``ferramentas`` rows switch on, ``(name, description)`` in name
    order. A legacy-content version (no rows) has none; a row without a description is not offered (same rule as
    the channel toolset: there is no default description)."""
    from app.studio.ferramentas_registry import grupo_de

    conteudo = getattr(compiled, "conteudo", None)
    if conteudo is None:
        return ()
    return tuple(sorted(
        (f.ferramenta, f.descricao.strip()) for f in conteudo.ferramentas
        if f.ativo and (f.descricao or "").strip() and grupo_de(f.ferramenta) is not None
    ))

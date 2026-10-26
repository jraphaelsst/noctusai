"""Platform-defined agents (Julia v2, CONTRACT §2.6, owner answer Q2) -- DATA-DRIVEN (049).

A platform definition is ANY ``definition_scope='plataforma'`` row of the platform org: ONE definition for every
org, edited there by platform admins, plus an INSTANCE row per org (``definition_scope='instancia'``: activation /
mode, LLM key, budget, tokens). There is NO code registry: no agent key is known to the code. What a registry used
to carry per key is DATA on the definition row, set through the Studio API (UI or the ``noctus.agents.content``
tool) and read by every mechanism (runtime, compile, qualification, org-instance creation, publish):

* ``runtime`` / ``owner_product`` -- how the agent runs and which product owns its transport;
* ``escopo_qualificacao`` -- the qualification SCOPE the agent works (``None`` = every scope);
* ``padrao_qualificacao`` -- the qualification standard key the agent works (``None`` = none);
* ``rascunho_padrao`` -- the settings its first draft starts with (provider / model / effort / ...);
* ``instanciavel`` -- whether a PUBLISHED definition is instantiated in every org (closed by default; a closed one
  reaches only orgs granted via ``definition_org_grants``).

Not one word of prompt text lives here either: the content is written as rows (Studio API / MCP tool).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord, StudioConflict

logger = logging.getLogger(__name__)

__all__ = [
    "escopo_de",
    "padrao_de",
    "ensure_definicao",
    "ensure_instancia",
    "ensure_instancias",
]


def escopo_de(agent: Any) -> str | None:
    """The qualification scope the platform-defined agent works (``None`` = every scope). ``agent`` is the
    DEFINITION record (``AgenteResolvido.definicao``); any other row carries none."""
    return getattr(agent, "escopo_qualificacao", None)


def padrao_de(agent: Any) -> str | None:
    """The qualification standard key the platform-defined agent works (``None`` = none)."""
    return getattr(agent, "padrao_qualificacao", None)


def ensure_definicao(
    org_id: UUID, key: str, *, studio_store: Any, created_by: UUID | None = None, nome: str | None = None,
    descricao: str | None = None, runtime: str = "llm", owner_product: str | None = None,
    escopo_qualificacao: str | None = None, padrao_qualificacao: str | None = None,
    rascunho_padrao: dict[str, Any] | None = None, instanciavel: bool = False, papel: str | None = None,
) -> StudioAgentRecord:
    """Idempotently create the platform DEFINITION of ``key`` in ``org_id`` (which must be the platform org -- the
    DB trigger / the Fake refuse anywhere else: ``definition_not_platform``) with an empty draft carrying only the
    given first-draft settings. Never touches an existing definition (its data is changed through the definition
    update route). ``nome`` is required for a NEW key (``ValueError`` otherwise)."""
    existing = studio_store.get_platform_definition(key)
    if existing is not None:
        return existing
    if not nome:
        raise ValueError("nome is required to create a new platform definition")
    if papel == "gerador" and any(d.papel == "gerador" for d in studio_store.list_platform_definitions()):
        raise StudioConflict("gerador_ja_existe", "another platform definition already is the generator")
    agent = studio_store.create_studio_agent(
        org_id, key, nome, descricao, runtime=runtime, owner_product=owner_product,
        definition_scope="plataforma", escopo_qualificacao=escopo_qualificacao,
        padrao_qualificacao=padrao_qualificacao, rascunho_padrao=rascunho_padrao, instanciavel=instanciavel, papel=papel,
    )
    draft = studio_store.create_draft(org_id, agent.id, None, created_by or agent.id)
    if rascunho_padrao:
        studio_store.update_draft(org_id, draft.id, dict(rascunho_padrao))
    studio_store.append_audit(
        org_id, agent.id, created_by, "agente_criado", None,
        {"key": key, "nome": agent.nome, "definition_scope": "plataforma"},
    )
    logger.info("agents.plataforma.definition_created key=%s org_id=%s agent_id=%s", key, org_id, agent.id)
    return agent


def _instanciar(org_id: UUID, definition: StudioAgentRecord, *, studio_store: Any) -> StudioAgentRecord:
    try:
        agent = studio_store.create_studio_agent(
            org_id, definition.key, definition.nome, definition.descricao, runtime=definition.runtime,
            owner_product=definition.owner_product, definition_scope="instancia", definition_agent_id=definition.id,
        )
    except StudioConflict:
        # A concurrent first use created it between the read and the insert.
        return studio_store.get_agent(org_id, definition.key)
    logger.info("agents.plataforma.instance_created key=%s org_id=%s agent_id=%s", definition.key, org_id, agent.id)
    return agent


def _pode_instanciar(definition: StudioAgentRecord, org_id: UUID, studio_store: Any) -> bool:
    """Open definitions (``instanciavel``) reach every org; a closed one -- every product-owned definition -- reaches
    ONLY the orgs explicitly granted it (``definition_org_grants``). Org/app configuration never leaks by default."""
    return definition.instanciavel or studio_store.is_definition_granted(definition.id, org_id)


def ensure_instancia(org_id: UUID, key: str, *, studio_store: Any) -> StudioAgentRecord | None:
    """The org's row for platform-defined ``key``: the existing one, else a new INSTANCE of the platform
    definition. ``None`` when no instantiable platform definition exists (nothing to instantiate -- no stranded
    content-less row is created)."""
    try:
        return studio_store.get_agent(org_id, key)
    except NotFound:
        pass
    definition = studio_store.get_platform_definition(key)
    if definition is None or not _pode_instanciar(definition, org_id, studio_store):
        return None
    return _instanciar(org_id, definition, studio_store=studio_store)


def ensure_instancias(org_id: UUID, *, studio_store: Any) -> list[StudioAgentRecord]:
    """Give ``org_id`` an instance of EVERY published, instantiable platform definition it does not have yet
    (returns the created ones). The generic replacement of the per-key ``ensure_julia``."""
    have = {a.key for a in studio_store.list_agents(org_id)}
    created: list[StudioAgentRecord] = []
    for definition in studio_store.list_platform_definitions():
        if definition.key in have or definition.org_id == org_id or not _pode_instanciar(definition, org_id, studio_store):
            continue
        if studio_store.get_active_version(definition.org_id, definition.id) is None:
            continue
        created.append(_instanciar(org_id, definition, studio_store=studio_store))
    return created

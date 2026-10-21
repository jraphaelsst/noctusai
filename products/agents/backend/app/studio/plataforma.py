"""Platform-defined agents (Julia v2, CONTRACT §2.6, owner answer Q2).

Opt-in per agent key: a key registered here has ONE definition for every org (the
``definition_scope='plataforma'`` row, living in the platform org, edited there by platform
admins) and an INSTANCE row per org (``definition_scope='instancia'``: activation / mode, LLM key,
budget, tokens). Every other studio agent (dev-advisors, one-chat, bia, ...) stays
``definition_scope='org'`` and is untouched.

What a registered key carries here is STRUCTURE only — the runtime kind and the version settings a
fresh definition draft starts with (provider / model / effort / turn cap / tool policy). Not one
word of prompt text: the definition's content is written as data (Studio API / MCP tool).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord, StudioConflict

logger = logging.getLogger(__name__)

__all__ = [
    "DefinicaoPlataforma",
    "definicao_registrada",
    "escopo_de",
    "padrao_de",
    "chaves_de_plataforma",
    "ensure_definicao",
    "ensure_instancia",
]


@dataclass(frozen=True)
class DefinicaoPlataforma:
    key: str
    nome: str
    descricao: str
    runtime: str
    owner_product: str | None
    #: The settings the definition's first draft starts with.
    rascunho: dict[str, Any] = field(default_factory=dict)
    #: The qualification SCOPE the agent works (a criterion's ``escopo`` is empty or equal to it; Julia
    #: only works ``sdr``, later agents work theirs over the same lead state). ``None`` = every scope.
    escopo_qualificacao: str | None = None
    #: The qualification standard (``qualificacao_padroes.chave``) the agent works. An agent version that
    #: pins a standard version uses that one; otherwise the newest PUBLISHED version of this standard.
    padrao_qualificacao: str | None = None


def _registro() -> dict[str, DefinicaoPlataforma]:
    # Lazy: the per-agent modules import this one for the generic mechanics.
    from app.studio.julia import JULIA_DEFINICAO

    return {JULIA_DEFINICAO.key: JULIA_DEFINICAO}


def definicao_registrada(key: str) -> DefinicaoPlataforma | None:
    return _registro().get(key)


def escopo_de(key: str) -> str | None:
    """The qualification scope the platform-defined agent ``key`` works (``None`` = every scope)."""
    spec = definicao_registrada(key)
    return spec.escopo_qualificacao if spec is not None else None


def padrao_de(key: str) -> str | None:
    """The qualification standard key the platform-defined agent ``key`` works (``None`` = none)."""
    spec = definicao_registrada(key)
    return spec.padrao_qualificacao if spec is not None else None


def chaves_de_plataforma() -> frozenset[str]:
    return frozenset(_registro())


def ensure_definicao(
    org_id: UUID, key: str, *, studio_store: Any, created_by: UUID | None = None,
) -> StudioAgentRecord:
    """Idempotently create the platform DEFINITION of ``key`` in ``org_id`` (which must be the
    platform org — the DB trigger / the Fake refuse anywhere else: ``definition_not_platform``)
    with an empty draft carrying only the registered settings. Never touches an existing one."""
    spec = definicao_registrada(key)
    if spec is None:
        raise ValueError(f"{key!r} is not a platform-defined agent key")
    existing = studio_store.get_platform_definition(key)
    if existing is not None:
        return existing
    agent = studio_store.create_studio_agent(
        org_id, key, spec.nome, spec.descricao, runtime=spec.runtime, owner_product=spec.owner_product,
        definition_scope="plataforma",
    )
    draft = studio_store.create_draft(org_id, agent.id, None, created_by or agent.id)
    studio_store.update_draft(org_id, draft.id, dict(spec.rascunho))
    studio_store.append_audit(
        org_id, agent.id, created_by, "agente_criado", None,
        {"key": key, "nome": agent.nome, "definition_scope": "plataforma"},
    )
    logger.info("agents.plataforma.definition_created key=%s org_id=%s agent_id=%s", key, org_id, agent.id)
    return agent


def ensure_instancia(org_id: UUID, key: str, *, studio_store: Any) -> StudioAgentRecord | None:
    """The org's row for platform-defined ``key``: the existing one, else a new INSTANCE of the
    platform definition. ``None`` when no platform definition exists yet (nothing to instantiate —
    no stranded content-less row is created)."""
    try:
        return studio_store.get_agent(org_id, key)
    except NotFound:
        pass
    spec = definicao_registrada(key)
    definition = studio_store.get_platform_definition(key)
    if spec is None or definition is None:
        return None
    try:
        agent = studio_store.create_studio_agent(
            org_id, key, definition.nome, definition.descricao, runtime=spec.runtime,
            owner_product=spec.owner_product, definition_scope="instancia", definition_agent_id=definition.id,
        )
    except StudioConflict:
        # A concurrent first use created it between the read and the insert.
        return studio_store.get_agent(org_id, key)
    logger.info("agents.plataforma.instance_created key=%s org_id=%s agent_id=%s", key, org_id, agent.id)
    return agent

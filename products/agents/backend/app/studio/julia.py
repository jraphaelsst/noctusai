"""The ``julia`` agent — Julia, the lead-facing real-estate assistant.

Julia is a PLATFORM-DEFINED studio agent (Julia v2, owner answer Q2): ONE definition for every
org — the ``definition_scope='plataforma'`` row of the platform org — and one INSTANCE row per org
(``definition_scope='instancia'``: activation / mode, LLM key, budget, tokens, conversations).
What differs per org is the org's SPEC VALUES (``agent_org_specs``), referenced from the definition
by visible ``{{org.chave}}`` placeholders. See ``app.studio.plataforma`` / ``app.studio.resolucao``
and CONTRACT §2.6.

This module is STRUCTURE only: the key, the runtime kind (``runtime='llm'``,
``owner_product='social-wiring'``), the settings the definition's first draft starts with and the
legacy-key alias. NO prompt text lives in code (D2/D3, keeper ``check_agent_prompt_text_in_code``):
sections, skills, system texts, tool descriptions and decisions are rows, written as data through the
Studio API / the ``noctus.agents.content`` MCP tool. The v1 constants that used to live here are a
test-only fixture now (``tests/channels/julia_v1.py``).

Seed model: ``gpt-5.6-terra`` — the OpenAI cost tier meant for high-volume use (US$ 2 / 12 per 1M
tokens). ``luna`` (the economy tier) is cheaper but is the likelier to fumble tool calls and to hold a
persona over a long chat; ``sol`` costs twice as much for accuracy a qualification chat does not
need. The owner changes it in the studio (a compiled setting of the version).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.stores.studio_definitions import StudioAgentRecord
from app.studio.plataforma import DefinicaoPlataforma, ensure_instancia

logger = logging.getLogger(__name__)

__all__ = [
    "JULIA_DEFINICAO",
    "JULIA_KEY",
    "JULIA_MODEL",
    "JULIA_PROVIDER",
    "canonical_channel_agent_key",
    "ensure_julia",
]

JULIA_KEY = "julia"
#: NOC-REMEDIATE[drop-lead-imob-alias]: the SDR agent was keyed ``lead-imob`` before
#: 2026-10-19. social-wiring (and any token minted before the rename) still sends the old key
#: for one release; every channel/token entry point maps it onto ``julia`` through
#: :func:`canonical_channel_agent_key`. Remove together with the social-wiring side.
_LEGACY_KEY_ALIASES = {"lead-imob": JULIA_KEY}


def canonical_channel_agent_key(agent_key: str) -> str:
    """The current key for ``agent_key`` (``lead-imob`` is an alias of ``julia``)."""
    return _LEGACY_KEY_ALIASES.get(agent_key, agent_key)


JULIA_NAME = "Julia"
JULIA_DESCRIPTION = "Assistente virtual que atende leads de imóveis no WhatsApp."
JULIA_PROVIDER = "openai"
JULIA_MODEL = "gpt-5.6-terra"
_EFFORT = "medium"
_MAX_TURNS = 8
_TOOL_POLICY = {"web_search": False, "knowledge": False}

JULIA_DEFINICAO = DefinicaoPlataforma(
    key=JULIA_KEY, nome=JULIA_NAME, descricao=JULIA_DESCRIPTION, runtime="llm", owner_product="social-wiring",
    rascunho={
        "provider": JULIA_PROVIDER, "model": JULIA_MODEL, "effort": _EFFORT,
        "max_turns": _MAX_TURNS, "tool_policy": dict(_TOOL_POLICY),
    },
)


def ensure_julia(org_id: UUID, *, studio_store: Any, created_by: UUID | None = None) -> StudioAgentRecord | None:
    """Idempotently give ``org_id`` its Julia: the existing row, else a new INSTANCE of the
    platform definition (no versions, no text — the org uses the definition's active version and
    fills its org specs). ``None`` when the platform definition does not exist yet: nothing is
    created, so no content-less per-org row is ever stranded. ``created_by`` is kept for the
    callers' signature (an instance has no draft to attribute)."""
    return ensure_instancia(org_id, JULIA_KEY, studio_store=studio_store)

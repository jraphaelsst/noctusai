"""The studio in-process SDK MCP server (Agent Studio contract §E3, §A6, §H2).

Progressive disclosure for studio agents: skill bodies, skill reference files
and the knowledge library load just-in-time through READ-ONLY tools that read
the DB via the stores — never through filesystem ``Read`` (which stays
disallowed, Julia's hardened posture).

Security invariants (security review of wave 1, binding):

* **Server-side binding.** Every handler closes over ``org_id`` / ``agent_id``
  / ``version_id`` taken from the server-built :class:`AgentSpec`. The model's
  arguments are only ever a skill ``nome``, a file ``caminho``, a search
  ``consulta``/``colecao``/``limite`` or a document ``slug``/``parte`` — never
  an id, never an org.
* **Active skills of the pinned version only**; ``caminho`` is an exact match.
* **Knowledge off ⇒ not registered.** When ``tool_policy.knowledge`` is false
  the ``kb_*`` tools do not exist on the server (and are absent from the
  allowlist) — not merely refusing.
* **Bounded inputs/outputs.** ``consulta`` ≤ 512 chars, ``limite`` clamped to
  1..20, ``parte`` clamped to ≥ 1; every tool result (the JSON text the model
  receives) is capped at 24 000 chars — an oversize text field is cut with an
  explicit ``truncado``/``aviso`` marker, never silently.
* **Errors are payloads.** A refusal is ``{"erro": "<codigo>", ...}``; an
  unexpected failure is logged and surfaces as ``{"erro": "falha_interna"}`` —
  no exception text ever reaches the model.

The handlers are built by :func:`studio_tool_specs` WITHOUT importing the SDK
(so they are unit-testable on their own); :func:`build_studio_tools` wraps
them into the ``studio`` server with ``claude_agent_sdk.create_sdk_mcp_server``.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.stores.errors import NotFound

logger = logging.getLogger(__name__)

__all__ = [
    "STUDIO_SERVER_NAME",
    "SKILL_TOOL_NAMES",
    "KNOWLEDGE_TOOL_NAMES",
    "MAX_RESULT_CHARS",
    "MAX_CONSULTA_CHARS",
    "MAX_LIMITE",
    "KB_PAGE_CHARS",
    "StudioToolSpec",
    "studio_tool_names",
    "studio_allowed_tools",
    "studio_tool_specs",
    "build_studio_tools",
]

STUDIO_SERVER_NAME = "studio"

#: Always registered (a version with zero skills still answers
#: ``skill_inexistente`` with the empty ``disponiveis`` list).
SKILL_TOOL_NAMES: tuple[str, ...] = ("abrir_skill", "ler_arquivo_skill")
#: Registered only when ``tool_policy.knowledge`` is true.
KNOWLEDGE_TOOL_NAMES: tuple[str, ...] = ("kb_buscar", "kb_ler")

#: Hard cap on the JSON text of ANY tool result (security review).
MAX_RESULT_CHARS = 24_000
MAX_CONSULTA_CHARS = 512
MAX_LIMITE = 20
DEFAULT_LIMITE = 8
#: ``kb_ler`` page size. Contract §E3 says "pages of ≤ 24 000 chars"; the
#: binding result cap is ALSO 24 000 for the whole JSON payload (metadata +
#: JSON escaping included), so pages are cut smaller to leave headroom and a
#: page is (practically) never trimmed by the result cap.
KB_PAGE_CHARS = 18_000

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class StudioToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler


def studio_tool_names(*, knowledge: bool) -> tuple[str, ...]:
    """Leaf names registered on the ``studio`` server for this policy."""
    return SKILL_TOOL_NAMES + (KNOWLEDGE_TOOL_NAMES if knowledge else ())


def studio_allowed_tools(*, knowledge: bool, web_search: bool) -> tuple[str, ...]:
    """The EXACT allowlist ``can_use_tool`` enforces for a studio turn: the
    registered ``mcp__studio__*`` names, plus ``WebSearch`` only when enabled."""
    names = tuple(f"mcp__{STUDIO_SERVER_NAME}__{n}" for n in studio_tool_names(knowledge=knowledge))
    return names + (("WebSearch",) if web_search else ())


# ── result rendering ────────────────────────────────────────────────────────


def _content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _render(payload: dict[str, Any], *, trim_field: str | None = None) -> dict[str, Any]:
    """Serialize ``payload`` under :data:`MAX_RESULT_CHARS`. When too large,
    ``trim_field`` (a string field) is cut and the payload says so
    explicitly (``truncado: true`` + ``aviso``); if it still cannot fit, the
    model gets ``{"erro": "resultado_muito_grande"}`` — never a silently
    shortened answer."""
    text = _dumps(payload)
    if len(text) <= MAX_RESULT_CHARS:
        return _content(text)
    value = payload.get(trim_field) if trim_field else None
    if isinstance(value, str):
        trimmed = dict(payload)
        trimmed["truncado"] = True
        trimmed["aviso"] = (
            f"Conteúdo cortado: o resultado excede {MAX_RESULT_CHARS} caracteres. "
            "O trecho abaixo está incompleto."
        )
        keep = len(value)
        for _ in range(8):
            trimmed[trim_field] = value[:keep]
            text = _dumps(trimmed)
            overflow = len(text) - MAX_RESULT_CHARS
            if overflow <= 0:
                return _content(text)
            keep = max(keep - overflow - 64, 0)
    return _content(_dumps({"erro": "resultado_muito_grande"}))


def _erro(codigo: str, **extra: Any) -> dict[str, Any]:
    return _content(_dumps({"erro": codigo, **extra}))


def _guarded(name: str, fn: Handler) -> Handler:
    """No exception ever leaks to the model — logged with the tool name,
    answered with a generic PT-BR-coded payload."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return await fn(args or {})
        except Exception:
            logger.exception("agents.studio_tool.failed tool=%s", name)
            return _erro("falha_interna")

    return handler


def _str_arg(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _int_arg(args: dict[str, Any], key: str, default: int) -> int | None:
    value = args.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        # Surfaced to the model as an `{"erro": ...}` payload by the caller.
        logger.debug("agents.studio_tool.bad_int_arg key=%s value=%r", key, value)
        return None


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


# ── the handlers ────────────────────────────────────────────────────────────


def studio_tool_specs(
    *,
    org_id: UUID,
    agent_id: UUID,
    version_id: UUID,
    knowledge_enabled: bool,
    definitions: Any,
    knowledge: Any,
) -> list[StudioToolSpec]:
    """Build the studio tools for ONE turn, bound to the server-side spec.

    ``definitions`` is a ``StudioDefinitionStore``, ``knowledge`` a
    ``StudioKnowledgeStore`` — the tools read ONLY through them (§E3: never
    raw SQL in the tool layer)."""

    def _active_skills() -> list[Any]:
        return [s for s in definitions.list_skills(org_id, version_id) if s.ativo]

    def _files_of(skill_id: UUID) -> list[Any]:
        return sorted(
            (f for f in definitions.list_version_skill_files(org_id, version_id) if f.skill_id == skill_id),
            key=lambda f: f.caminho,
        )

    def _find_skill(nome: str | None) -> tuple[Any | None, list[str]]:
        skills = _active_skills()
        disponiveis = [s.nome for s in skills]
        for s in skills:
            if s.nome == nome:
                return s, disponiveis
        return None, disponiveis

    async def abrir_skill(args: dict[str, Any]) -> dict[str, Any]:
        skill, disponiveis = _find_skill(_str_arg(args, "nome"))
        if skill is None:
            return _erro("skill_inexistente", disponiveis=disponiveis)
        return _render(
            {
                "nome": skill.nome,
                "descricao": skill.descricao,
                "corpo": skill.corpo,
                "arquivos": [{"caminho": f.caminho, "titulo": f.titulo} for f in _files_of(skill.id)],
            },
            trim_field="corpo",
        )

    async def ler_arquivo_skill(args: dict[str, Any]) -> dict[str, Any]:
        skill, disponiveis = _find_skill(_str_arg(args, "nome"))
        if skill is None:
            return _erro("skill_inexistente", disponiveis=disponiveis)
        caminho = _str_arg(args, "caminho")
        files = _files_of(skill.id)
        for f in files:
            if f.caminho == caminho:
                return _render(
                    {"caminho": f.caminho, "titulo": f.titulo, "conteudo": f.conteudo},
                    trim_field="conteudo",
                )
        return _erro("arquivo_inexistente", disponiveis=[f.caminho for f in files])

    async def kb_buscar(args: dict[str, Any]) -> dict[str, Any]:
        consulta = (_str_arg(args, "consulta") or "").strip()
        if not consulta:
            return _erro("consulta_vazia")
        if len(consulta) > MAX_CONSULTA_CHARS:
            return _erro("consulta_muito_longa", limite_caracteres=MAX_CONSULTA_CHARS)
        colecao = _str_arg(args, "colecao") or None
        limite = _int_arg(args, "limite", DEFAULT_LIMITE)
        if limite is None:
            return _erro("limite_invalido")
        limite = max(1, min(limite, MAX_LIMITE))
        # The SAME function `GET .../knowledge/search` calls (§D3).
        hits = knowledge.search(org_id, agent_id, consulta, colecao=colecao, limite=limite)
        resultados = [
            {"slug": h.slug, "titulo": h.titulo, "colecao": h.colecao, "tag": h.tag, "tipo": h.tipo, "trecho": h.trecho}
            for h in hits
        ]
        # Drop trailing hits (never cut one mid-way) until the result fits.
        while resultados and len(_dumps({"resultados": resultados})) > MAX_RESULT_CHARS:
            resultados.pop()
        return _content(_dumps({"resultados": resultados}))

    async def kb_ler(args: dict[str, Any]) -> dict[str, Any]:
        slug = _str_arg(args, "slug")
        if not slug:
            return _erro("documento_inexistente")
        parte = _int_arg(args, "parte", 1)
        if parte is None:
            return _erro("parte_invalida")
        parte = max(parte, 1)
        try:
            # One read on the happy path; archived documents are unreadable (M4).
            part = knowledge.read_document_part(org_id, agent_id, slug, parte=parte, max_chars=KB_PAGE_CHARS)
        except NotFound:
            # Unknown/archived slug OR out-of-range page — told apart below
            # and answered as an explicit `{"erro": ...}` payload.
            logger.debug("agents.studio_tool.kb_ler_miss slug=%s parte=%s", slug, parte)
            part = None
        if part is None:
            if parte == 1 or knowledge.find_document_by_slug(org_id, agent_id, slug) is None:
                return _erro("documento_inexistente")
            first = knowledge.read_document_part(org_id, agent_id, slug, parte=1, max_chars=KB_PAGE_CHARS)
            return _erro("parte_inexistente", total_partes=first.total_partes)
        return _render(
            {
                "slug": part.slug,
                "titulo": part.titulo,
                "colecao": part.colecao,
                "tag": part.tag,
                "tipo": part.tipo,
                "proveniencia": part.proveniencia,
                "parte": part.parte,
                "total_partes": part.total_partes,
                "conteudo": part.conteudo,
            },
            trim_field="conteudo",
        )

    specs = [
        StudioToolSpec(
            "abrir_skill",
            "Abre uma skill pelo nome e devolve as instruções completas dela e a lista de arquivos de referência.",
            _obj({"nome": {"type": "string", "maxLength": 64}}, ["nome"]),
            _guarded("abrir_skill", abrir_skill),
        ),
        StudioToolSpec(
            "ler_arquivo_skill",
            "Lê um arquivo de referência de uma skill (nome da skill + caminho exato do arquivo).",
            _obj(
                {"nome": {"type": "string", "maxLength": 64}, "caminho": {"type": "string", "maxLength": 255}},
                ["nome", "caminho"],
            ),
            _guarded("ler_arquivo_skill", ler_arquivo_skill),
        ),
    ]
    if knowledge_enabled:
        specs += [
            StudioToolSpec(
                "kb_buscar",
                "Busca na base de conhecimento. Devolve documentos (slug, título, coleção, tag, tipo, trecho).",
                _obj(
                    {
                        "consulta": {"type": "string", "maxLength": MAX_CONSULTA_CHARS},
                        "colecao": {"type": ["string", "null"]},
                        "limite": {"type": "integer", "minimum": 1, "maximum": MAX_LIMITE},
                    },
                    ["consulta"],
                ),
                _guarded("kb_buscar", kb_buscar),
            ),
            StudioToolSpec(
                "kb_ler",
                "Lê um documento da base de conhecimento pelo slug, em partes (parte começa em 1).",
                _obj({"slug": {"type": "string"}, "parte": {"type": "integer", "minimum": 1}}, ["slug"]),
                _guarded("kb_ler", kb_ler),
            ),
        ]
    return specs


def build_studio_tools(
    *,
    org_id: UUID,
    agent_id: UUID,
    version_id: UUID,
    knowledge_enabled: bool,
    definitions: Any,
    knowledge: Any,
) -> Any:
    """The ``studio`` in-process SDK MCP server for one turn (contract §E3).

    Returns the ``McpSdkServerConfig`` ``ClaudeAgentOptions.mcp_servers``
    takes. The SDK prefixes each leaf name into ``mcp__studio__<name>`` —
    exactly the names :func:`studio_allowed_tools` lists."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    specs = studio_tool_specs(
        org_id=org_id,
        agent_id=agent_id,
        version_id=version_id,
        knowledge_enabled=knowledge_enabled,
        definitions=definitions,
        knowledge=knowledge,
    )
    return create_sdk_mcp_server(
        STUDIO_SERVER_NAME,
        tools=[tool(s.name, s.description, s.input_schema)(s.handler) for s in specs],
    )

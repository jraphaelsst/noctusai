"""The ``onboarding`` in-process MCP server of the interviewer agent (``onboarding-imob``).

Served by the ``claude_sdk`` runtime NEXT to the ``studio`` server when the pinned version's ``ferramentas`` rows switch
the ``onboarding`` tool group on (``app.studio.ferramentas_registry.GRUPOS_FERRAMENTAS``). The model sees
``mcp__onboarding__<nome>``. Schemas live here (strict: ``additionalProperties: false``, no org / session id anywhere);
the DESCRIPTIONS are rows (``descricoes``: short name -> the row's text) -- a tool without a row is not registered.

Every handler delegates to :class:`app.onboarding.entrevista.Entrevista`, bound server-side to the session of the turn's
conversation. A tool never raises to the model: refusals are ``{"ok": false, "erro": ..., "motivo": ...}`` payloads.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.onboarding.entrevista import ORIGENS, Entrevista
from app.studio.ferramentas_registry import ONBOARDING_FERRAMENTAS
from app.studio.tools import StudioToolSpec, _content, _dumps, _guarded, _obj

__all__ = ["ONBOARDING_SERVER_NAME", "TOOL_NAMES", "build_onboarding_tools", "onboarding_tool_specs"]

ONBOARDING_SERVER_NAME = "onboarding"
TOOL_NAMES = ONBOARDING_FERRAMENTAS


def onboarding_tool_specs(
    entrevista: Callable[[], Entrevista | None], descricoes: Mapping[str, str],
) -> list[StudioToolSpec]:
    """``entrevista`` resolves the turn's interview (``None`` = the conversation has no onboarding session: every tool
    answers ``sem_sessao`` -- the model is never handed another org's session)."""

    def _wrap(nome: str, fn: Callable[[Entrevista, dict[str, Any]], dict[str, Any]]):
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            e = entrevista()
            if e is None:
                return _content(_dumps({"ok": False, "erro": "sem_sessao", "motivo": "Esta conversa não está ligada a uma empresa."}))
            return _content(_dumps(fn(e, args)))

        return _guarded(nome, handler)

    schemas: dict[str, tuple[dict[str, Any], Callable[[Entrevista, dict[str, Any]], dict[str, Any]]]] = {
        "progresso_onboarding": (_obj({}, []), lambda e, a: e.progresso()),
        "registrar_resposta": (
            _obj({
                "item": {"type": "integer", "minimum": 1, "maximum": 99},
                "situacao": {"type": "string", "enum": ["respondido", "pendente"]},
                "valor": {"type": ["string", "number", "boolean", "array", "object", "null"]},
                "trecho": {"type": ["string", "null"], "maxLength": 600},
                "origem": {"type": "string", "enum": list(ORIGENS)},
                "motivo": {"type": ["string", "null"], "enum": ["nao_sabe", "depois", None]},
            }, ["item", "situacao"]),
            lambda e, a: e.registrar_resposta(
                item=a.get("item"), situacao=a.get("situacao"), valor=a.get("valor"), trecho=a.get("trecho"),
                origem=a.get("origem") or "cliente", motivo=a.get("motivo")),
        ),
        "importar_configuracao": (
            _obj({"texto": {"type": "string", "maxLength": 60000}}, ["texto"]),
            lambda e, a: e.importar_configuracao(texto=a.get("texto")),
        ),
        "revisar_e_aplicar": (
            _obj({
                "fase": {"type": "string", "enum": ["resumo", "aplicar"]},
                "confirmacao_cliente": {"type": ["string", "null"], "maxLength": 600},
            }, ["fase"]),
            lambda e, a: e.revisar_e_aplicar(fase=a.get("fase"), confirmacao_cliente=a.get("confirmacao_cliente")),
        ),
    }
    return [
        StudioToolSpec(nome, descricoes[nome].strip(), schema, _wrap(nome, fn))
        for nome, (schema, fn) in schemas.items() if (descricoes.get(nome) or "").strip()
    ]


def build_onboarding_tools(entrevista: Callable[[], Entrevista | None], descricoes: Mapping[str, str]) -> Any:
    """The ``onboarding`` server (``McpSdkServerConfig``) for one turn."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    specs = onboarding_tool_specs(entrevista, descricoes)
    return create_sdk_mcp_server(
        ONBOARDING_SERVER_NAME, tools=[tool(s.name, s.description, s.input_schema)(s.handler) for s in specs],
    )

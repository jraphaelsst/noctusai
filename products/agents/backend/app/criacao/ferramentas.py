"""The Diretor de Criacao's read tools (agents -> SW ``POST /api/criacao/ferramentas/{nome}``).

Same seam as Julia's (``app.clients.social_wiring``: one token per org, 8 s, every failure a coded
``indisponivel``); a sibling toolset because the registry of Julia's tools is bound to a lead turn.

Schemas live here (strict, ``extra="forbid"``); the WORDS (tool description, parameter labels) are rows of the agent
version (``ConteudoBundle.ferramentas``) -- a tool without a row is not offered. The model never names the brand:
``marca_id`` is bound to the turn server-side and injected into every call, so it appears in no schema.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noctusai_lib.integrations.llm import ToolCall, ToolResult, ToolSpec

from app.channels.tool_registry import _inline, enriquecer_schema
from app.clients.social_wiring import JULIA_TOOL_TIMEOUT_SECONDS, JULIA_TOOL_UNAVAILABLE, SocialWiringClient
from app.runtime.llm_runtime import LlmToolset
from app.studio.models import ConteudoBundle

logger = logging.getLogger(__name__)

#: A turn that keeps calling tools is cut here (a loop is capped, canon section 9).
MAX_CHAMADAS_POR_TURNO = 24


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SemArgs(_Args):
    pass


class CerebrosArgs(_Args):
    tipos: Optional[list[str]] = Field(default=None, max_length=20)


class EstruturasBuscarArgs(_Args):
    formato: Literal["reels", "carrossel", "stories", "post"]
    objetivo: Optional[Literal["alcance", "autoridade", "conexao", "venda"]] = None
    texto: Optional[str] = Field(default=None, max_length=500)
    limite: int = Field(default=10, ge=1, le=20)


class EstruturaDetalheArgs(_Args):
    codigo: int = Field(ge=1)


class PesquisasArgs(_Args):
    tema: Optional[str] = Field(default=None, max_length=200)
    limite: int = Field(default=20, ge=1, le=50)


class ViraisArgs(_Args):
    limite: int = Field(default=10, ge=1, le=20)


class DesempenhoArgs(_Args):
    janela_dias: int = Field(default=30, ge=1, le=365)


class VozAmostrasArgs(_Args):
    n: int = Field(default=5, ge=1, le=20)


#: tool name -> its argument model. Order = the order offered. ``marca_id`` is bound by the turn (never an argument).
CRIACAO_TOOLS: dict[str, type[_Args]] = {
    "contexto_marca": SemArgs,
    "cerebros": CerebrosArgs,
    "estruturas_buscar": EstruturasBuscarArgs,
    "estrutura_detalhe": EstruturaDetalheArgs,
    "pesquisas": PesquisasArgs,
    "virais": ViraisArgs,
    "desempenho": DesempenhoArgs,
    "voz_amostras": VozAmostrasArgs,
    "treinamentos": SemArgs,
}
#: ``estrutura_detalhe`` reads the platform-wide library: SW's model has no ``marca_id`` (strict), so it is not sent.
SEM_MARCA = frozenset({"estrutura_detalhe"})

CRIACAO_FERRAMENTAS: tuple[str, ...] = tuple(CRIACAO_TOOLS)


@dataclass
class CriacaoTurno:
    """The per-turn state of a Diretor de Criacao turn, built by the route (S9): who, which brand, the SW client and
    the version's content. Mutable on purpose: it is the turn's ledger (what the tools returned feeds the checks)."""

    org_id: UUID
    marca_id: UUID
    sw: SocialWiringClient
    conteudo: ConteudoBundle
    chamadas: int = 0
    chamadas_por_ferramenta: dict[str, int] = field(default_factory=dict)
    #: every tool answer of the turn, in order: (tool name, payload) -- the ONLY legitimate source of a cited source
    resultados: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


def schema_de(nome: str, parametros: Any = None) -> dict[str, Any]:
    raw = CRIACAO_TOOLS[nome].model_json_schema()
    schema = _inline(raw, raw.get("$defs", {}))
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    if parametros:
        enriquecer_schema(schema, parametros)
    return schema


def tools_ofertaveis(conteudo: ConteudoBundle) -> list[Any]:
    """The tool ROWS the turn may offer: active, with a description, known here, in registry order."""
    por_nome = {f.ferramenta: f for f in conteudo.ferramentas if f.ativo and (f.descricao or "").strip()}
    return [por_nome[n] for n in CRIACAO_TOOLS if n in por_nome]


def construir_toolset_criacao(t: CriacaoTurno) -> LlmToolset:
    linhas = tools_ofertaveis(t.conteudo)
    specs = tuple(ToolSpec(name=f.ferramenta, description=f.descricao.strip(), parameters=schema_de(f.ferramenta, f.parametros))
                  for f in linhas)
    oferecidas = {s.name for s in specs}

    def _json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    async def _handler(call: ToolCall) -> ToolResult:
        if call.name not in oferecidas:
            return ToolResult(call.call_id, _json({"ok": False, "codigo": "ferramenta_desconhecida"}), True)
        t.chamadas += 1
        t.chamadas_por_ferramenta[call.name] = t.chamadas_por_ferramenta.get(call.name, 0) + 1
        if t.chamadas > MAX_CHAMADAS_POR_TURNO:
            return ToolResult(call.call_id, _json({"ok": False, "codigo": "limite_ferramentas"}), True)
        try:
            args = CRIACAO_TOOLS[call.name].model_validate(call.arguments or {})
        except ValidationError as exc:
            campos = ", ".join(sorted({".".join(str(p) for p in e["loc"]) or "args" for e in exc.errors()}))
            return ToolResult(call.call_id, _json({"ok": False, "codigo": "argumentos_invalidos", "campos": campos}), True)
        corpo = args.model_dump(exclude_none=True)
        if call.name not in SEM_MARCA:
            corpo["marca_id"] = str(t.marca_id)  # bound by the turn: the model never names the brand
        try:
            resposta = await asyncio.wait_for(
                t.sw.criacao_ferramenta(t.org_id, call.name, corpo), JULIA_TOOL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 -- a tool never raises to the model; the cause is logged, the text is not
            logger.warning("agents.criacao_tool.failed org_id=%s tool=%s error=%s", t.org_id, call.name, type(exc).__name__)
            resposta = dict(JULIA_TOOL_UNAVAILABLE)
        erro = resposta.get("erro") is not None
        t.resultados.append((call.name, resposta))
        return ToolResult(call.call_id, _json(resposta), erro)

    return LlmToolset(
        tools=specs, handler=_handler, resumo=lambda nome, _a: nome,
        falha=t.conteudo.texto("runtime.ferramenta_falhou").strip(),
    )


__all__ = [
    "CRIACAO_FERRAMENTAS", "CRIACAO_TOOLS", "CriacaoTurno", "MAX_CHAMADAS_POR_TURNO", "construir_toolset_criacao",
    "schema_de", "tools_ofertaveis",
]

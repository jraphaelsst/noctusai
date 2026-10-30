"""The tool NAMES a content-mode agent version may configure (Julia v2, CONTRACT §2.2).

Names only — no description, no schema text. The JSON schema of each tool lives with its
handler (``app.channels.tool_registry.TOOLS``, derived from the strict argument models) and a tool's
description and parameter descriptions are rows of ``agents.agent_version_ferramentas``. This set is the
allowlist the Studio API validates a row's ``ferramenta`` against, so a typo can never become a
tool the model is told about but the runtime does not have. Additive: a slice that adds a tool
adds its name here in the same change.
"""
from __future__ import annotations

from app.runtime import gate

__all__ = [
    "FERRAMENTAS_CONHECIDAS",
    "FERRAMENTAS_DE_EXTRACAO",
    "GRUPOS_FERRAMENTAS",
    "GrupoFerramentas",
    "ferramenta_conhecida",
    "ferramenta_da_conversa",
    "grupo_de",
    "nome_no_modelo",
]


class GrupoFerramentas:
    """A content-configurable TOOL GROUP (agents-unified, Renata cutover S7): a set of tools served by one in-process
    MCP server of the in-app chat runtime (``claude_sdk``), switched on per agent VERSION by its ``ferramentas`` rows.

    A row's ``ferramenta`` is ``<grupo>_<nome>`` (the content pattern allows no separator but ``_``); the model sees
    the tool under the server's own name ``mcp__<grupo>__<nome>``. The CLASS of each tool (read vs write) is the
    group's gate table, never the row: a write tool always asks a human (the approval broker) before it runs, and a
    group is never offered on a lead-facing channel turn (the channel toolset is ``app.channels.tool_registry.TOOLS``
    only, guarded by a test)."""

    def __init__(self, nome: str, leitura: tuple[str, ...], escrita: tuple[str, ...]) -> None:
        self.nome = nome
        prefixo = f"mcp__{nome}__"
        self.leitura = tuple(n.removeprefix(prefixo) for n in leitura if n.startswith(prefixo))
        self.escrita = tuple(n.removeprefix(prefixo) for n in escrita if n.startswith(prefixo))

    @property
    def ferramentas(self) -> frozenset[str]:
        """The content names (``<grupo>_<nome>``) of every tool of the group."""
        return frozenset(f"{self.nome}_{n}" for n in (*self.leitura, *self.escrita))

    def nome_curto(self, ferramenta: str) -> str:
        return ferramenta.removeprefix(f"{self.nome}_")

    def nome_sdk(self, ferramenta: str) -> str:
        return f"mcp__{self.nome}__{self.nome_curto(ferramenta)}"

    def classe(self, ferramenta: str) -> str:
        return "escrita" if self.nome_curto(ferramenta) in self.escrita else "leitura"


#: The academia toolset (academia-de-reciclagem's HTTP API: KB, decisions, questions, timeline, roadmap, tasks,
#: training content, research sources) -- the SAME gate table and handlers the code-defined academia agent used
#: (``app.runtime.gate`` / ``app.runtime.tools``), so argument schemas, approvals and the signed assertion are one.
GRUPOS_FERRAMENTAS: dict[str, GrupoFerramentas] = {
    "academia": GrupoFerramentas("academia", gate.LEITURA, gate.ESCRITA),
}


def grupo_de(nome: str) -> GrupoFerramentas | None:
    """The tool group a content tool name belongs to, else ``None`` (a channel / knowledge / extraction tool)."""
    return next((g for g in GRUPOS_FERRAMENTAS.values() if nome in g.ferramentas), None)


def nome_no_modelo(nome: str) -> str:
    """The name the MODEL sees for a content tool: a group tool is ``mcp__<grupo>__<nome>``; any other is itself."""
    grupo = grupo_de(nome)
    return grupo.nome_sdk(nome) if grupo is not None else nome


FERRAMENTAS_CONHECIDAS: frozenset[str] = frozenset({
    # Julia v2 channel toolset (CONTRACT §3.4) -- ``app.channels.tool_registry.TOOLS``. The pre-v2 tools
    # ``salvar_slots`` / ``definir_operacao`` / ``qualificar_lead`` / ``pedido_visita`` / ``horarios_visita`` and the
    # free-form ``buscar_imoveis`` are RETIRED for Julia (qualification is computed from records; no scheduling).
    "abrir_skill", "ler_arquivo_skill",
    "avaliar_lead", "registrar_perfil", "oferecer_imoveis", "detalhes_imovel", "consultar_empreendimento",
    "registrar_reacao_imovel", "registrar_intencao_visita", "registrar_identificacao", "concluir_qualificacao",
    "handoff", "encerrar", "captacao", "consentimento_credito", "registrar_solicitacao_titular",
    # knowledge (app/studio/tools.py)
    "kb_buscar", "kb_ler",
    # extraction tools (resumo / decisão) -- ``app.channels.extracao``
    "registrar_resumo", "registrar_escolha",
}) | frozenset().union(*(g.ferramentas for g in GRUPOS_FERRAMENTAS.values()))


#: Tools of the two structured-extraction calls (``app.channels.extracao``: the episode summary and the transport
#: decision). They are model-callable ONLY inside those calls, each with its own system text; a conversation turn
#: never offers them, so the conversation prompt's ``# Ferramentas`` block must not list them either (the model
#: would be told about a tool it does not have). Their rows stay content: edited, hashed and shown in Compilado.
FERRAMENTAS_DE_EXTRACAO: frozenset[str] = frozenset({"registrar_resumo", "registrar_escolha"})


def ferramenta_conhecida(nome: str) -> bool:
    return nome in FERRAMENTAS_CONHECIDAS


def ferramenta_da_conversa(nome: str) -> bool:
    """A known tool the CONVERSATION model may be offered (everything but the extraction-only tools)."""
    return nome in FERRAMENTAS_CONHECIDAS and nome not in FERRAMENTAS_DE_EXTRACAO

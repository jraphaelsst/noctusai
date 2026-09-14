"""The gate: Julia's tool-class table (contract §E.4) — exhaustive.

``LEITURA`` and ``ESCRITA`` are the ONLY two allow-shaped classes. Every
name not in either tuple is denied — by construction, not by omission:
:func:`classify` returns ``"deny"`` for anything it doesn't recognise, so
a new tool added anywhere else in the codebase does not silently become
callable by Julia until someone adds it here.

Matching is EXACT string equality, never ``endswith``/``startswith``
(contract §E.4: "architect debt" — a prefix match would let
``mcp__academia__kb_escrever_v2`` slip through as an accidental read).
"""
from __future__ import annotations

from typing import Any, Literal

__all__ = [
    "LEITURA",
    "ESCRITA",
    "ToolClass",
    "classify",
    "resumo",
]

ToolClass = Literal["leitura", "escrita", "deny"]

#: Contract §E.4 — allowed without asking. Includes the two SDK built-ins
#: Julia's base tool set carries (``WebSearch``, ``Skill``) alongside every
#: read-only academia MCP proxy.
LEITURA: tuple[str, ...] = (
    "mcp__academia__kb_buscar",
    "mcp__academia__kb_ler",
    "mcp__academia__decisao_listar",
    "mcp__academia__pergunta_listar",
    "mcp__academia__historico_timeline",
    "mcp__academia__roadmap_ler",
    "mcp__academia__tarefa_listar",
    "mcp__academia__tarefa_preparar_sessao",
    "mcp__academia__conteudo_listar",
    "mcp__academia__conteudo_ler",
    "WebSearch",
    "Skill",
)

#: Contract §E.4 — asks for human approval via the broker before running.
ESCRITA: tuple[str, ...] = (
    "mcp__academia__kb_escrever",
    "mcp__academia__kb_mover",
    "mcp__academia__decisao_registrar",
    "mcp__academia__decisao_substituir",
    "mcp__academia__pergunta_adicionar",
    "mcp__academia__pergunta_responder",
    "mcp__academia__historico_append",
    "mcp__academia__roadmap_atualizar",
    "mcp__academia__tarefa_criar",
    "mcp__academia__tarefa_atualizar",
    "mcp__academia__conteudo_salvar",
    "mcp__academia__pesquisa_capturar_fonte",
)

_LEITURA_SET = frozenset(LEITURA)
_ESCRITA_SET = frozenset(ESCRITA)


def classify(tool_name: str) -> ToolClass:
    """Exact-match ``tool_name`` against the two allow-shaped classes.

    Anything else — including a near-miss like a versioned or prefixed
    variant of a real name — is ``"deny"``. There is no third bucket that
    means "ask a human whether to allow it forever"; ``deny`` here is
    final, matching contract §E.4's "anything else: deny. Also listed in
    disallowed_tools, so the CLI never offers them."
    """
    if tool_name in _LEITURA_SET:
        return "leitura"
    if tool_name in _ESCRITA_SET:
        return "escrita"
    return "deny"


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def resumo(tool_name: str, tool_input: dict[str, Any]) -> str:
    """A PT-BR one-liner describing an ``escrita`` call, for the approval
    card (contract §E.4: "The approval card shows resumo plus diff").

    Total over every ``ESCRITA`` name — never raises on a missing/odd
    input field, since a malformed call must still be showable to a human
    deciding whether to approve it, not crash before it gets that far.
    """
    inp = tool_input or {}

    if tool_name == "mcp__academia__kb_escrever":
        titulo = inp.get("titulo") or inp.get("slug") or "(sem título)"
        categoria = inp.get("categoria", "?")
        return f'Escrever entrada do KB "{_short(titulo)}" (categoria: {categoria}).'

    if tool_name == "mcp__academia__kb_mover":
        origem = inp.get("origem", "?")
        destino = inp.get("destino", "?")
        return f'Mover entrada do KB de "{origem}" para "{destino}".'

    if tool_name == "mcp__academia__decisao_registrar":
        titulo = inp.get("titulo", "(sem título)")
        return f'Registrar decisão "{_short(titulo)}".'

    if tool_name == "mcp__academia__decisao_substituir":
        titulo = inp.get("titulo", "(sem título)")
        substitui = inp.get("substitui", "?")
        return f'Substituir decisão {substitui} por "{_short(titulo)}".'

    if tool_name == "mcp__academia__pergunta_adicionar":
        pergunta = inp.get("pergunta", "(sem pergunta)")
        return f'Registrar pergunta em aberto: "{_short(pergunta)}".'

    if tool_name == "mcp__academia__pergunta_responder":
        codigo = inp.get("codigo", "?")
        return f"Responder pergunta {codigo}."

    if tool_name == "mcp__academia__historico_append":
        titulo = inp.get("titulo", "(sem título)")
        return f'Registrar no histórico: "{_short(titulo)}".'

    if tool_name == "mcp__academia__roadmap_atualizar":
        codigo = inp.get("codigo", "?")
        return f"Atualizar fase do roadmap {codigo}."

    if tool_name == "mcp__academia__tarefa_criar":
        titulo = inp.get("titulo", "(sem título)")
        fase = inp.get("fase", "?")
        return f'Criar tarefa "{_short(titulo)}" na fase {fase}.'

    if tool_name == "mcp__academia__tarefa_atualizar":
        codigo = inp.get("codigo", "?")
        return f"Atualizar tarefa {codigo}."

    if tool_name == "mcp__academia__conteudo_salvar":
        titulo = inp.get("titulo", "(sem título)")
        tipo = inp.get("tipo", "?")
        return f'Salvar conteúdo "{_short(titulo)}" (tipo: {tipo}).'

    if tool_name == "mcp__academia__pesquisa_capturar_fonte":
        titulo = inp.get("titulo", "(sem título)")
        kb_slug = inp.get("kb_slug", inp.get("destino", "?"))
        return f'Capturar fonte de pesquisa "{_short(titulo)}" para {kb_slug}.'

    # Not an escrita tool this gate knows about — still return something
    # showable rather than raise (no silent errors, but also no crash in
    # front of a human waiting for an approval card).
    return f"Executar {tool_name}."

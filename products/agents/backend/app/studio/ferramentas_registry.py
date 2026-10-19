"""The tool NAMES a content-mode agent version may configure (Julia v2, CONTRACT §2.2).

Names only — no description, no schema text. The JSON schema of each tool lives with its
handler (``app.channels.tool_registry.TOOLS``, derived from the strict argument models) and a tool's
description and parameter descriptions are rows of ``agents.agent_version_ferramentas``. This set is the
allowlist the Studio API validates a row's ``ferramenta`` against, so a typo can never become a
tool the model is told about but the runtime does not have. Additive: a slice that adds a tool
adds its name here in the same change.
"""
from __future__ import annotations

__all__ = ["FERRAMENTAS_CONHECIDAS", "ferramenta_conhecida"]

FERRAMENTAS_CONHECIDAS: frozenset[str] = frozenset({
    # Julia v2 channel toolset (CONTRACT §3.4) -- ``app.channels.tool_registry.TOOLS``. The pre-v2 tools
    # ``salvar_slots`` / ``definir_operacao`` / ``qualificar_lead`` / ``pedido_visita`` / ``horarios_visita`` and the
    # free-form ``buscar_imoveis`` are RETIRED for Julia (qualification is computed from records; no scheduling).
    "abrir_skill", "ler_arquivo_skill",
    "avaliar_lead", "registrar_perfil", "oferecer_imoveis", "detalhes_imovel", "consultar_empreendimento",
    "registrar_reacao_imovel", "registrar_intencao_visita", "registrar_identificacao", "concluir_qualificacao",
    "handoff", "encerrar", "captacao", "consentimento_credito",
    # knowledge (app/studio/tools.py)
    "kb_buscar", "kb_ler",
    # extraction tools (resumo / decisão) -- ``app.channels.extracao``
    "registrar_resumo", "registrar_escolha",
})


def ferramenta_conhecida(nome: str) -> bool:
    return nome in FERRAMENTAS_CONHECIDAS

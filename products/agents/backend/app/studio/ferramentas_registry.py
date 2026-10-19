"""The tool NAMES a content-mode agent version may configure (Julia v2, CONTRACT §2.2).

Names only — no description, no schema text. The JSON schema of each tool lives with its
handler (``app.channels.tools`` today, A-RT's ``tool_registry`` next) and a tool's description
and parameter descriptions are rows of ``agents.agent_version_ferramentas``. This set is the
allowlist the Studio API validates a row's ``ferramenta`` against, so a typo can never become a
tool the model is told about but the runtime does not have. Additive: a slice that adds a tool
adds its name here in the same change.
"""
from __future__ import annotations

__all__ = ["FERRAMENTAS_CONHECIDAS", "ferramenta_conhecida"]

FERRAMENTAS_CONHECIDAS: frozenset[str] = frozenset({
    # channel tools (app/channels/tools.py today)
    "handoff", "encerrar", "captacao", "consentimento_credito",
    "buscar_imoveis", "detalhes_imovel", "consultar_empreendimento", "horarios_visita",
    "salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita",
    # Julia v2 toolset (CONTRACT §3.4)
    "avaliar_lead", "registrar_perfil", "oferecer_imoveis", "registrar_reacao_imovel",
    "registrar_intencao_visita", "concluir_qualificacao",
    # skills + knowledge (app/studio/tools.py)
    "abrir_skill", "ler_arquivo_skill", "kb_buscar", "kb_ler",
    # extraction tools (resumo / decisão)
    "registrar_resumo", "registrar_escolha",
})


def ferramenta_conhecida(nome: str) -> bool:
    return nome in FERRAMENTAS_CONHECIDAS

"""Scripted pt-BR WhatsApp texts for the eval-loop gate (catalog kinds ``eval_loop_parada`` / ``eval_loop_checkpoint``).

Pure builders: no I/O, no LLM. The send itself is the seam ``EvalLoopService._avisar_dono_whatsapp``
(``NOC-REMEDIATE[eval-loop-owner-whatsapp]``); this module only turns the loop's facts into the line the owner reads.
"""
from __future__ import annotations

_LINK = "/agentes"
_MOTIVO = {
    "alvo_atingido": "chegou à nota alvo",
    "sem_melhora": "2 rodadas seguidas sem melhora",
    "orcamento_atingido": "o orçamento foi atingido",
    "rodadas_esgotadas": "as rodadas planejadas acabaram",
    "parado_manualmente": "foi parado manualmente",
}


def _pct(x: float | None) -> str:
    return "sem nota" if x is None else f"{round(x * 100)}%"


def _usd(x: float) -> str:
    return f"US$ {x:.2f}"


def texto_parada(*, agente: str, suite: str, motivo: str, melhor_nota: float | None, gasto_usd: float, orcamento_usd: float,
                 rodadas_feitas: int, link: str = _LINK) -> str:
    return (f"Loop de avaliação parado: {agente} ({suite}). Motivo: {_MOTIVO.get(motivo, motivo)}. "
            f"Melhor nota: {_pct(melhor_nota)} em {rodadas_feitas} rodada(s). Gasto {_usd(gasto_usd)} de {_usd(orcamento_usd)}. "
            f"Detalhes: {link}")


def texto_checkpoint(*, agente: str, suite: str, rodada: int, rodadas_planejadas: int, melhor_nota: float | None,
                     gasto_usd: float, orcamento_usd: float, rodadas_sem_melhora: int, link: str = _LINK) -> str:
    return (f"Loop de avaliação em andamento: {agente} ({suite}), rodada {rodada} de {rodadas_planejadas}. "
            f"Melhor nota: {_pct(melhor_nota)}. Gasto {_usd(gasto_usd)} de {_usd(orcamento_usd)}; "
            f"{rodadas_sem_melhora} rodada(s) sem melhora. Detalhes: {link}")

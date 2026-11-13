"""The eval-loop CONFIG (owner 2026-11-12): target, per-loop budget CAP and max planned rounds -- platform-level, edited by a
platform admin, read when a loop opens (migration 086; stored in ``agents.runtime_settings``, changes recorded as
``loop_config_alterada`` events). No IO here: pure defaults, bounds and the loop-creation resolution."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

__all__ = [
    "ALVO_PADRAO", "ORCAMENTO_PADRAO_USD", "RODADAS_MAX_PADRAO", "ORCAMENTO_MAX_USD", "RODADAS_LIMITE", "KEYS",
    "EvalLoopConfig", "resolver_criacao",
]

ALVO_PADRAO = 0.95
ORCAMENTO_PADRAO_USD = 5.00
RODADAS_MAX_PADRAO = 10
#: the migration CHECK bounds (086): a config value outside them cannot be stored.
ORCAMENTO_MAX_USD = 500.0
RODADAS_LIMITE = 100

#: ``agents.runtime_settings`` keys of the three values.
KEYS = {"alvo": "eval_loop_alvo", "orcamento_usd": "eval_loop_orcamento_usd", "rodadas_max": "eval_loop_rodadas_max"}


@dataclass(frozen=True)
class EvalLoopConfig:
    alvo: float = ALVO_PADRAO
    orcamento_usd: float = ORCAMENTO_PADRAO_USD
    rodadas_max: int = RODADAS_MAX_PADRAO


def resolver_criacao(cfg: EvalLoopConfig, *, rodadas_planejadas: int | None, orcamento_usd: float | None) -> tuple[int, float]:
    """The rounds and budget a new loop gets. Omitted => the config's; given => must not exceed it (422, for EVERY caller:
    the budget is a cap, not a default a platform admin can lift per loop; change the config instead)."""
    rodadas = cfg.rodadas_max if rodadas_planejadas is None else rodadas_planejadas
    if rodadas > cfg.rodadas_max:
        raise HTTPException(422, {"code": "rodadas_acima_do_maximo", "detail": (
            f"rodadas_planejadas ({rodadas}) acima do máximo configurado ({cfg.rodadas_max}). "
            "Peça o ajuste da configuração dos loops ou planeje menos rodadas.")})
    orcamento = cfg.orcamento_usd if orcamento_usd is None else orcamento_usd
    if orcamento > cfg.orcamento_usd + 1e-9:
        raise HTTPException(422, {"code": "orcamento_acima_do_teto", "detail": (
            f"orcamento_usd (US$ {orcamento:.2f}) acima do teto configurado (US$ {cfg.orcamento_usd:.2f}) por loop. "
            "Ajuste a configuração dos loops ou peça um orçamento menor.")})
    return rodadas, orcamento

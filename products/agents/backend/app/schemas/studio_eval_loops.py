"""Pydantic schemas of the eval-loop gate API (``/api/studio/agents/{key}/evals/loops``, migration 076). Request bodies are
strict (``extra="forbid"``); responses are plain models (consumers ignore unknown fields)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

__all__ = ["LoopCreateRequest", "LoopStopRequest", "LoopOut", "LoopListOut", "RodadaOut", "OvercallOut", "CheckpointOut"]

LOOP_ORCAMENTO_USD_MAX = 500.0


class LoopCreateRequest(StrictHttpModel):
    #: ``comportamento`` (judge suite, ``eval_runs``) | ``mecanismo`` (scripted suite, ``eval_mecanismo_runs``).
    suite: str = Field(pattern="^(comportamento|mecanismo)$")
    #: G2: the rounds the loop plans (checkpoints at 5, 10, 15 apply to those <= this).
    rodadas_planejadas: int = Field(ge=1, le=100)
    #: G7: omitted => ``STUDIO_EVAL_LOOP_BUDGET_USD`` (US$ 20). A token may not exceed the default.
    orcamento_usd: float | None = Field(default=None, gt=0, le=LOOP_ORCAMENTO_USD_MAX)


class LoopStopRequest(StrictHttpModel):
    motivo: str | None = Field(default=None, max_length=300)


class RodadaOut(BaseModel):
    rodada: int
    run_id: UUID
    status: str
    score: float | None
    custo_usd: float
    compiled_hash: str
    #: ``None`` = the baseline (first scored round) or an unscored round; ``False`` = did not raise the score (an overcall).
    melhorou: bool | None
    overcall: bool
    falhas: list[str]


class OvercallOut(BaseModel):
    rodada: int
    run_id: UUID
    score: float | None
    custo_usd: float


class CheckpointOut(BaseModel):
    rodada: int
    atingido: bool
    score: float | None
    gasto_usd: float | None


class LoopOut(BaseModel):
    id: UUID
    agente_chave: str
    suite: str
    #: ``ativo`` | ``parado`` | ``concluido``
    status: str
    #: ``alvo_atingido`` | ``sem_melhora`` | ``orcamento_atingido`` | ``rodadas_esgotadas`` | ``parado_manualmente`` | ``None`` while active
    motivo_parada: str | None
    detalhe_parada: dict[str, Any] | None
    rodadas_planejadas: int
    rodadas_feitas: int
    alvo: float
    piso: float
    orcamento_usd: float
    gasto_usd: float
    restante_usd: float
    melhor_score: float | None
    score_atual: float | None
    acima_do_piso: bool | None
    started_at: datetime | None
    stopped_at: datetime | None
    serie: list[RodadaOut]
    overcalls: list[OvercallOut]
    custo_overcalls_usd: float
    checkpoints: list[CheckpointOut]


class LoopListOut(BaseModel):
    items: list[LoopOut]

"""Pydantic schemas of the eval-loop gate API (``/api/studio/agents/{key}/evals/loops``, migration 076). Request bodies are
strict (``extra="forbid"``); responses are plain models (consumers ignore unknown fields)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

__all__ = ["LoopCreateRequest", "LoopStopRequest", "LoopModoRequest", "RunProgressoOut", "LoopEventoOut", "LoopEventosOut", "LoopOut", "LoopListOut", "EvalLoopConfigIn", "EvalLoopConfigOut", "RodadaOut", "OvercallOut", "CheckpointOut"]

LOOP_ORCAMENTO_USD_MAX = 500.0


class LoopCreateRequest(StrictHttpModel):
    #: ``comportamento`` (judge suite, ``eval_runs``) | ``mecanismo`` (scripted suite, ``eval_mecanismo_runs``).
    suite: str = Field(pattern="^(comportamento|mecanismo)$")
    #: G2: the rounds the loop plans (checkpoints at 5, 10, 15 apply to those <= this). Omitted => the config's ``rodadas_max``;
    #: given => must be <= it (422 ``rodadas_acima_do_maximo``).
    rodadas_planejadas: int | None = Field(default=None, ge=1, le=100)
    #: G7: omitted => the config's ``orcamento_usd``; above it => 422 ``orcamento_acima_do_teto`` (for every caller).
    orcamento_usd: float | None = Field(default=None, gt=0, le=LOOP_ORCAMENTO_USD_MAX)
    #: ``automatico`` (default) = the server runs the rounds by itself until a stop condition; ``manual`` = each round is a click.
    modo: str = Field(default="automatico", pattern="^(automatico|manual)$")


class LoopModoRequest(StrictHttpModel):
    #: ``automatico`` resumes the driver (it opens the next round now); ``manual`` pauses it after the round in flight.
    modo: str = Field(pattern="^(automatico|manual)$")


class RunProgressoOut(BaseModel):
    """Live progress of one run (either suite). Every number is the server's. ``indeterminado`` = the mechanism suite while it
    executes (it stores its executions when it ends): only status, elapsed time and cost cap are known then."""

    run_id: UUID
    suite: str
    status: str
    ativo: bool
    indeterminado: bool
    total: int | None
    concluidos: int | None
    aprovados: int | None
    reprovados: int | None
    erros: int | None
    pulados: int | None
    #: mean score of the MEASURED cases (errored ones are out of the denominator); ``None`` = nothing measured yet
    score_parcial: float | None
    custo_usd: float | None
    limite_usd: float | None
    started_at: datetime | None
    finished_at: datetime | None
    decorrido_s: float | None
    eta_s: float | None
    erro: str | None
    erro_codigo: str | None


class LoopEventoOut(BaseModel):
    evento: str
    rodada_seq: int | None
    run_id: UUID | None
    detalhe: dict[str, Any]
    created_at: datetime | None


class LoopEventosOut(BaseModel):
    items: list[LoopEventoOut]


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
    #: a round whose run ERRORED says why (code + text): shown as an error, never as failing cases
    erro_codigo: str | None = None
    erro_mensagem: str | None = None


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
    #: ``alvo_atingido`` | ``sem_melhora`` | ``orcamento_atingido`` | ``rodadas_esgotadas`` | ``parado_manualmente`` | ``erro`` | ``None`` while active
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
    #: ``automatico`` | ``manual`` (see :class:`LoopCreateRequest`)
    modo: str = "manual"
    #: why an automatic loop is idle right now, e.g. ``{"codigo": "hash_inalterado", "mensagem": "..."}``; ``None`` = nothing
    aviso: dict[str, Any] | None = None
    #: what the loop is doing right now: ``rodando`` | ``automatico`` (between rounds) | ``aguardando_edicao`` | ``manual`` | ``encerrado``
    estado_driver: str = "manual"


class LoopListOut(BaseModel):
    items: list[LoopOut]


class EvalLoopConfigIn(StrictHttpModel):
    """PUT body of ``/api/studio/plataforma/eval-loop-config`` (full replace; bounds mirror the 086 CHECKs)."""

    alvo: float = Field(gt=0, le=1)
    orcamento_usd: float = Field(gt=0, le=LOOP_ORCAMENTO_USD_MAX)
    rodadas_max: int = Field(ge=1, le=100)


class EvalLoopConfigOut(BaseModel):
    alvo: float
    orcamento_usd: float
    rodadas_max: int
    #: the platform admin who last saved it / when (``None`` while the defaults have never been edited)
    alterado_por: UUID | None = None
    alterado_em: datetime | None = None

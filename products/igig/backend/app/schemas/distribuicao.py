"""Pydantic contracts for Módulo 5 — distribuição e métricas."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "Canal",
    "AgendarPublicacao",
    "EditarPublicacao",
    "PublicacaoOut",
    "MetricaIn",
    "MetricaOut",
    "EficienciaOut",
]

#: Mirrors the DB CHECK and `publicacao_publisher.CANAIS`.
Canal = Literal["instagram", "facebook", "tiktok", "linkedin"]


class AgendarPublicacao(StrictHttpModel):
    pauta_id: str
    canal: Canal
    #: A real datetime — validated here (422 on malformed input) so a bad
    #: value never falls through to the persistence layer's broad
    #: `PersistenceError` catch, which would misreport it as "pauta já tem
    #: publicação ativa" (finding #7, 2026-09 audit).
    agendada_para: datetime


class EditarPublicacao(StrictHttpModel):
    """PATCH body — the editable subset of `AgendarPublicacao`.

    `pauta_id` is the publication's identity and is not editable (schedule a
    different pauta instead). A rescheduled time must be in the future (a naive
    datetime is read as UTC); POST does not enforce that, so it lives here.
    """

    canal: Canal | None = None
    agendada_para: datetime | None = None

    @field_validator("agendada_para")
    @classmethod
    def _futuro(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        ref = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if ref <= datetime.now(timezone.utc):
            raise ValueError("A nova data de publicação deve estar no futuro.")
        return v

    @model_validator(mode="after")
    def _algo_a_editar(self) -> "EditarPublicacao":
        if self.canal is None and self.agendada_para is None:
            raise ValueError("Informe canal e/ou agendada_para.")
        return self


class PublicacaoOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    pauta_id: str
    canal: str
    status: str
    agendada_para: str | None = None
    publicada_em: str | None = None
    external_id: str | None = None
    permalink: str | None = None
    #: Present on failure so the operator sees WHY without reading logs.
    erro: str | None = None
    tentativas: int = 0


class MetricaIn(StrictHttpModel):
    """One engagement snapshot. All counters default to 0, never null —
    a missing metric is 0 observed, not unknown."""

    curtidas: int = Field(default=0, ge=0)
    comentarios: int = Field(default=0, ge=0)
    compartilhamentos: int = Field(default=0, ge=0)
    alcance: int = Field(default=0, ge=0)
    cliques_bio: int = Field(default=0, ge=0)
    visualizacoes: int = Field(default=0, ge=0)


class MetricaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    publicacao_id: str
    coletada_em: str
    curtidas: int = 0
    comentarios: int = 0
    compartilhamentos: int = 0
    alcance: int = 0
    cliques_bio: int = 0
    visualizacoes: int = 0


class EficienciaOut(BaseModel):
    """BI rollup for one client."""

    cliente_id: str
    cliente_nome: str
    tarefas: int
    refacoes: int
    taxa_refacao: float
    horas: float
    custo_reais: float
    #: Non-empty when some hours could not be costed — the number is then
    #: UNDERSTATED, and the reader must be told rather than left guessing.
    alertas: list[str] = Field(default_factory=list)

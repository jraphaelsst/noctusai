"""Wire contracts for the two boards (Comercial funnel + Esteira).

Board and move responses use the seed `{"data": ...}` envelope because the seed
frontend `createPipelineHooks` consumes them; the column shape is the seed's
`group_into_colunas` (`etapa`, `stage`, `total`, `valorTotal`, `exibidos`,
`cards`).
"""
from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "MoverCardIn",
    "MoverNegocioIn",
    "LeadManualIn",
    "NegocioCreate",
    "NegocioUpdate",
    "PapelEtapaIn",
    "PerderNegocioIn",
    "TarefaCreate",
]


class MoverCardIn(StrictHttpModel):
    """The seed board's move body (`createPipelineHooks.useMoveCard`)."""

    #: A stage ID, never a name — stages are user-editable rows.
    para_etapa_id: str = Field(min_length=1)
    novo_indice: int | None = Field(default=None, ge=0)
    motivo: str | None = Field(default=None, max_length=2000)


class MoverNegocioIn(MoverCardIn):
    #: REQUIRED when the destination is the `fechado` stage (409
    #: `orcamento_obrigatorio` otherwise); ignored for every other move.
    orcamento_id: str | None = None


class LeadManualIn(StrictHttpModel):
    """A lead typed in by the agency (roadmap R2 "Button to create leads")."""

    nome: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    empresa: str | None = Field(default=None, max_length=200)
    instagram: str | None = Field(default=None, max_length=120)
    especificacoes: dict[str, Any] = Field(default_factory=dict)
    observacoes: str | None = Field(default=None, max_length=4000)


class NegocioCreate(StrictHttpModel):
    """Put a lead on the funnel — an existing one (`lead_id`) or a new one (`lead`)."""

    lead_id: str | None = None
    lead: LeadManualIn | None = None
    titulo: str | None = Field(default=None, max_length=200)
    valor_estimado: float | None = Field(default=None, ge=0)
    responsavel_id: str | None = None
    #: An EXISTING cliente this negócio is for (owner decision 2026-09-28,
    #: comercial achado 12 — upsell/renewal). Rides straight through to
    #: `comercial_funil.abrir_negocio`, which already supports it — this is
    #: the route wiring the FE "Novo negócio"/"Cliente existente" flows call.
    cliente_id: str | None = None

    @model_validator(mode="after")
    def _um_lead(self) -> "NegocioCreate":
        if (self.lead_id is None) == (self.lead is None):
            raise ValueError("Informe exatamente um de `lead_id` ou `lead`.")
        return self


class NegocioUpdate(StrictHttpModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    valor_estimado: float | None = Field(default=None, ge=0)
    responsavel_id: str | None = None


class PerderNegocioIn(StrictHttpModel):
    motivo: str = Field(min_length=1, max_length=2000)


class PapelEtapaIn(StrictHttpModel):
    """`PATCH /api/comercial/pipeline/stages/{id}/papel` — reassign the
    funnel's one system role (`fechado`), mirroring `esteira_router`'s
    `PapelEtapaIn` for the funnel's own stage editor (achado comercial #14 —
    the seed's generic stage editor has no control for moving a role between
    stages, only a delete-time refusal). `papel: None` clears it; see
    `comercial_funil.reatribuir_papel`."""

    papel: str | None = None


class TarefaCreate(StrictHttpModel):
    pauta_id: str
    titulo: str = Field(min_length=1, max_length=200)
    #: A `profissional.id` — the team record, same key the timer resolves.
    responsavel_id: str | None = None
    prazo: str | None = None

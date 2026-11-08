"""Request bodies + the card DTO of the funnel contract (`projects/noc-funnel/CONTRACT.md`)."""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

CardStatus = Literal["aberto", "ganho", "perdido", "arquivado"]


class Responsavel(TypedDict):
    id: str
    nome: Optional[str]


class Badge(TypedDict):
    label: str
    variant: str


class CardDTO(TypedDict):
    """The wire card. `kanban_pos` is a STRING (numeric precision survives)."""

    id: str
    etapa_id: Optional[str]
    kanban_pos: str
    status: str
    titulo: str
    subtitulo: Optional[str]
    valor: float
    responsavel: Optional[Responsavel]
    badges: list[Badge]
    motivo_perda_codigo: Optional[str]
    motivo_perda: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    hub_entity_id: Optional[str]
    campos: dict[str, Any]


class CardCreate(StrictHttpModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    etapa_id: Optional[str] = None
    valor: Optional[float] = Field(default=None, ge=0)
    responsavel_id: Optional[str] = None
    campos: dict[str, Any] = Field(default_factory=dict)


class CardUpdate(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, min_length=1, max_length=255)
    valor: Optional[float] = Field(default=None, ge=0)
    # Explicitly nullable: "sent as null" (unassign) differs from "not sent".
    responsavel_id: Optional[str] = None
    campos: Optional[dict[str, Any]] = None


class MoverEtapa(StrictHttpModel):
    # A stage ID, never a name — stages are user-editable rows.
    para_etapa_id: str
    novo_indice: Optional[int] = Field(default=None, ge=0)
    motivo: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Perder(StrictHttpModel):
    # Optional at the schema level so a missing code is the contract's
    # 422 `motivo_obrigatorio`, not a generic validation error.
    motivo_codigo: Optional[str] = None
    motivo_texto: Optional[str] = None


class ActionBody(StrictHttpModel):
    payload: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ActionBody",
    "Badge",
    "CardCreate",
    "CardDTO",
    "CardStatus",
    "CardUpdate",
    "MoverEtapa",
    "Perder",
    "Responsavel",
]

"""Request bodies of the proposta routes (CONTRACT §4.2).

A proposta stores its terms as JSON SNAPSHOTS validated with the SAME models
the live negotiation set uses (`card_hub.schemas`). The only difference is the
key space: the live models point at real row ids, a snapshot has none yet, so
the id-pointing fields are replaced by client-side refs into the snapshot:

* parcela / intermediário  `favorecido_ref`   = ``"fav:<index>"``
* parcela split share      `favorecido_ref`   = ``"fav:<index>"``
* termos                   `posse_marco_parcela_ref` /
                           `permuta_posse_marco_parcela_ref` = ``"parcela:<index>"``

Refs are resolved to real ids when Aceitar materializes the snapshot; their
existence is checked by `service.validar_snapshots` (400 `snapshot_invalido`,
field paths in `details.campos` — never a 422).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.modules.card_hub.schemas import (
    FavorecidoCreateBody,
    IntermediarioCreateBody,
    ParcelaCreateBody,
    ParcelaFavorecidoDivisaoBody,
    TermosNegocioPutBody,
)

REF_FAVORECIDO = "fav"
REF_PARCELA = "parcela"


class DivisaoSnapshot(ParcelaFavorecidoDivisaoBody):
    favorecido_id: None = None  # type: ignore[assignment]
    favorecido_ref: str = Field(min_length=1, max_length=32)


class ParcelaSnapshot(ParcelaCreateBody):
    favorecido_id: None = None  # type: ignore[assignment]
    favorecido_ref: Optional[str] = Field(default=None, max_length=32)
    favorecidos_divisao: list[DivisaoSnapshot] = Field(  # type: ignore[assignment]
        default_factory=list, max_length=20
    )


class FavorecidoSnapshot(FavorecidoCreateBody):
    pass


class IntermediarioSnapshot(IntermediarioCreateBody):
    favorecido_id: None = None  # type: ignore[assignment]
    favorecido_ref: Optional[str] = Field(default=None, max_length=32)


class TermosSnapshot(TermosNegocioPutBody):
    posse_marco_parcela_id: None = None  # type: ignore[assignment]
    permuta_posse_marco_parcela_id: None = None  # type: ignore[assignment]
    posse_marco_parcela_ref: Optional[str] = Field(default=None, max_length=32)
    permuta_posse_marco_parcela_ref: Optional[str] = Field(default=None, max_length=32)


class PropostaCreateBody(StrictHttpModel):
    """`visita_id` OR `imovel_codigo` — at least one (named 400 in the service)."""

    visita_id: Optional[UUID] = None
    imovel_codigo: Optional[str] = Field(default=None, min_length=1, max_length=64)


class PropostaPatchBody(StrictHttpModel):
    """Every field optional; absence = leave alone (`model_fields_set`).
    Explicit `null` clears the nullable scalars; the four snapshots and
    `testemunha_ids` are never null (send `[]` / `{}`)."""

    imovel_codigo: Optional[str] = Field(default=None, min_length=1, max_length=64)
    valor_proposto: Optional[Decimal] = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    pct_comissao: Optional[Decimal] = Field(default=None, ge=0, le=100)
    financiamento: Optional[bool] = None
    fgts: Optional[bool] = None
    validade_ate: Optional[date] = None
    observacoes: Optional[str] = Field(default=None, max_length=4000)
    #: Snapshot content is typed loosely HERE on purpose and validated by
    #: `service.validar_snapshots` against `ParcelaSnapshot` & co., so a bad
    #: item is a 400 `snapshot_invalido` with per-field paths instead of
    #: FastAPI's 422 (a non-list / non-object is still a 422).
    parcelas: list[dict[str, Any]] = Field(default_factory=list, max_length=360)
    favorecidos: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    intermediarios: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    termos: dict[str, Any] = Field(default_factory=dict)
    imobiliaria_id: Optional[UUID] = None
    testemunha_ids: list[UUID] = Field(default_factory=list, max_length=20)


class PropostaRecusarBody(StrictHttpModel):
    motivo: Optional[str] = Field(default=None, max_length=2000)


class PropostaAceitarBody(StrictHttpModel):
    pass


def dump_snapshot(model: Any) -> Any:
    """JSON-safe dump (Decimal -> str, UUID -> str) for the jsonb columns."""
    return model.model_dump(mode="json")


#: snapshot key -> the model each item (or the object, for termos) must satisfy.
SNAPSHOT_MODELS = {
    "parcelas": ParcelaSnapshot,
    "favorecidos": FavorecidoSnapshot,
    "intermediarios": IntermediarioSnapshot,
    "termos": TermosSnapshot,
}

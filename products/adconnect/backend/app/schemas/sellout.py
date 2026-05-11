"""
Pydantic schemas for the sellout router.

Three submission modes are exposed (estruturado / nfe_xml / freeform) plus
review + listing shapes. The DB column inventory lives in the migration
`001_adconnect.sql` under "Sellout reports".

History — response-model silent-drop fix (2026-05-11, RESPONSE-MODEL-AUDIT
de045c3 R2): aligned every field below to the `relatorios_sellout` table
inventory + CHECK constraints. Three drifts closed:
  - SubmissionMode literal `"attachment"` was rejected by the DB CHECK,
    which only allows `"freeform"`. Renamed everywhere (schema + service
    + tests). Frontend already used `"freeform"`.
  - `SelloutOut.periodo: Optional[str]` collapsed two DB columns
    (`periodo_inicio DATE NOT NULL` + `periodo_fim DATE NOT NULL`). Split
    into matching fields so both round-trip end-to-end.
  - `SelloutOut.org_id` had no corresponding DB column — silently dropped
    from responses. Removed. Tenant scoping flows through
    `distributor_id → distributors.org_id` via RLS, not a direct column.
  - `SelloutStatus` / `SelloutReviewIn.status` aligned to the DB CHECK
    (`'pendente','em_analise','aprovado','recusado'`); the prior
    `"rejeitado"` value would CHECK-violate on write.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel

# DB CHECK: submission_mode IN ('estruturado', 'nfe_xml', 'freeform')
SubmissionMode = Literal["estruturado", "nfe_xml", "freeform"]
# DB CHECK: status IN ('pendente', 'em_analise', 'aprovado', 'recusado')
SelloutStatus = Literal["pendente", "em_analise", "aprovado", "recusado"]


class SelloutEstruturadoIn(StrictHttpModel):
    """Estruturado-mode submission — distributor fills structured fields directly."""

    distributor_id: str
    periodo_inicio: date
    periodo_fim: date
    cnpj_cliente_final: Optional[str] = None
    valor_total: float
    quantidade_itens: int
    descricao_resumida: Optional[str] = None
    items_json: Optional[list[dict[str, Any]]] = None
    observacoes: Optional[str] = None


class SelloutAttachmentIn(StrictHttpModel):
    """Form-fields piece of a freeform/attachment submission. The actual
    file bytes are uploaded as multipart `file` and stored via `storage`
    integration. (Class name kept for backward-compat with consumer
    imports; submission_mode persisted is `freeform` per DB CHECK.)"""

    distributor_id: str
    periodo_inicio: date
    periodo_fim: date
    observacoes: Optional[str] = None


class SelloutReviewIn(StrictHttpModel):
    status: Literal["aprovado", "recusado"]
    review_notes: Optional[str] = None


class SelloutOut(StrictHttpModel):
    id: str
    distributor_id: str
    submitted_by: Optional[str] = None
    submission_mode: SubmissionMode
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    cnpj_cliente_final: Optional[str] = None
    valor_total: Optional[float] = None
    quantidade_itens: Optional[int] = None
    descricao_resumida: Optional[str] = None
    items_json: Optional[list[dict[str, Any]]] = None
    nfe_chave: Optional[str] = None
    nfe_xml_url: Optional[str] = None
    attachment_url: Optional[str] = None
    observacoes: Optional[str] = None
    status: SelloutStatus
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SelloutListOut(StrictHttpModel):
    data: list[SelloutOut] = Field(default_factory=list)


__all__ = [
    "SubmissionMode",
    "SelloutStatus",
    "SelloutEstruturadoIn",
    "SelloutAttachmentIn",
    "SelloutReviewIn",
    "SelloutOut",
    "SelloutListOut",
]

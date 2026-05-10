"""
Pydantic schemas for the sellout router.

Three submission modes are exposed (estruturado / nfe_xml / attachment) plus
review + listing shapes. The DB column inventory lives in the migration
`001_adconnect.sql` under "Sellout reports".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SubmissionMode = Literal["estruturado", "nfe_xml", "attachment"]
SelloutStatus = Literal["pendente", "aprovado", "rejeitado"]


class SelloutEstruturadoIn(BaseModel):
    """Estruturado-mode submission — distributor fills structured fields directly."""

    distributor_id: str
    periodo: Optional[str] = None
    cnpj_cliente_final: Optional[str] = None
    valor_total: float
    quantidade_itens: int
    descricao_resumida: Optional[str] = None
    items_json: Optional[list[dict[str, Any]]] = None
    observacoes: Optional[str] = None


class SelloutAttachmentIn(BaseModel):
    """Form-fields piece of an attachment submission. The actual file bytes
    are uploaded as multipart `file` and stored via `storage` integration."""

    distributor_id: str
    periodo: Optional[str] = None
    observacoes: Optional[str] = None


class SelloutReviewIn(BaseModel):
    status: Literal["aprovado", "rejeitado"]
    review_notes: Optional[str] = None


class SelloutOut(BaseModel):
    id: str
    org_id: Optional[str] = None
    distributor_id: str
    submission_mode: SubmissionMode
    periodo: Optional[str] = None
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
    submitted_by: Optional[str] = None


class SelloutListOut(BaseModel):
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

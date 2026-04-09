"""
Invoice Schemas — Invoice generation and status management.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InvoiceCreate(BaseModel):
    """Generate an invoice from a financial transaction."""

    transaction_id: UUID
    descricao: Optional[str] = Field(default=None, max_length=2000)


class InvoiceUpdate(BaseModel):
    """Update invoice status."""

    status: Literal["gerada", "enviada", "cancelada"]

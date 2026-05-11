"""
Invoice Schemas — Invoice (recibo) generation and status management.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class InvoiceCreate(StrictHttpModel):
    """Generate an invoice (recibo) from a financial transaction.

    `patient_id` is supplied by the therapist at generation time and is
    used to address the resulting invoice. `transaction_id` references an
    existing financial transaction row.
    """

    transaction_id: str = Field(..., min_length=1)
    patient_id: str = Field(..., min_length=1)
    descricao: Optional[str] = Field(default=None, max_length=2000)


class InvoiceUpdate(StrictHttpModel):
    """Update invoice status."""

    status: Literal["gerada", "enviada", "cancelada"]

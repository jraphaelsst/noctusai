"""
WhatsApp Schemas — Message sending and reminder scheduling.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class WhatsAppSendCreate(StrictHttpModel):
    """Send a WhatsApp message via WAHA."""

    appointment_id: Optional[UUID] = None
    destinatario_telefone: str = Field(..., min_length=10, max_length=20)
    tipo: Literal["lembrete", "confirmacao", "cancelamento", "personalizado"]
    conteudo: str = Field(..., min_length=1, max_length=4096)


class ReminderScheduleCreate(StrictHttpModel):
    """Configure automatic appointment reminders."""

    tipo: Literal["lembrete", "confirmacao"]
    horas_antes: int = Field(..., ge=1, le=168, description="Hours before appointment")
    mensagem_template: Optional[str] = Field(default=None, max_length=4096)
    is_active: bool = True

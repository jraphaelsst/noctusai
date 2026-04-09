"""
Room Schemas — Physical room management and booking for clinics.
"""
from __future__ import annotations

from datetime import date, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

class RoomCreate(BaseModel):
    """Create a physical room in a clinic."""

    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    capacidade: int = Field(default=1, ge=1)


class RoomUpdate(BaseModel):
    """Partial update for a room."""

    nome: Optional[str] = Field(default=None, min_length=1, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    capacidade: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Room Bookings
# ---------------------------------------------------------------------------

class RoomBookingCreate(BaseModel):
    """Book a room for an appointment time slot."""

    room_id: UUID
    appointment_id: UUID
    data: date
    horario_inicio: time
    horario_fim: time

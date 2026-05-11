"""
Room Schemas — Physical room management and booking for clinics.
"""
from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

class RoomCreate(StrictHttpModel):
    """Create a physical room in a clinic."""

    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    capacidade: int = Field(default=1, ge=1)


class RoomUpdate(StrictHttpModel):
    """Partial update for a room."""

    nome: Optional[str] = Field(default=None, min_length=1, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=2000)
    capacidade: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Room Bookings
# ---------------------------------------------------------------------------

class RoomBookingCreate(StrictHttpModel):
    """Book a room for an appointment time slot."""

    room_id: str = Field(..., min_length=1)
    appointment_id: str = Field(..., min_length=1)
    data: date
    horario_inicio: time
    horario_fim: time

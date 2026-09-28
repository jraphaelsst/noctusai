"""Schema for `GET /api/eu` — contract §Identity, slice BE-A."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EuMembro(BaseModel):
    """The `membro` sub-object — present only when `papel == "membro"`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    plano_id: Optional[UUID] = None
    plano_nome: Optional[str] = None
    nivel_grupoterapia: Literal["nenhum", "ouvir", "falar"]


class EuOut(BaseModel):
    """Response body for `GET /api/eu`."""

    papel: Literal["admin", "moderador", "membro"]
    nome: str
    email: str
    membro: Optional[EuMembro] = None

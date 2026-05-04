"""`media_scheduling.service_types` row shape."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ServiceType(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    active: bool = True

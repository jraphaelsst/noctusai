"""`media_scheduling.crew_skills` row shape (composite PK)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CrewSkill(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    skill: str

"""`media_scheduling.authorized_users` row shape (minimal).

WhatsApp-authorized actor. Phase 4 reads `id`, `phone_number`, `role`, `active`,
`name`, `email` for crew-assignment + tool-handler `find_authorized_user`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthorizedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    phone_number: str
    email: str | None = None
    linked_identity: str | None = None
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

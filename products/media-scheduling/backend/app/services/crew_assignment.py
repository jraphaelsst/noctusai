"""Crew-skill matching for real-estate media production.

Source reference:
`whatsapp-google-scheduling/app/services/crew_assignment.py:pick_crew_for_services`

Algorithm preserved verbatim — pick the active `media_crew` user whose
`crew_skills` superset the requested services. Lowest-id deterministic
tie-break (so a videomaker who also holds the `photos` skill doesn't
preempt a dedicated photographer with a lower id on a pure-photos
request).

Storage difference vs. source: source uses SQLAlchemy `.join` over the
`users` + `crew_skills` tables; we use the Supabase client (this product's
DB layer choice — see `app/database.py`). Same shape, different driver.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.models.authorized_user import AuthorizedUser

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


def pick_crew_for_services(
    supabase: "Client",
    services: Iterable[str],
) -> AuthorizedUser | None:
    """Pick the active `media_crew` whose skill set covers ALL requested services.

    Returns the matching `AuthorizedUser` (lowest id wins among full-coverage
    candidates), or `None` when no active crew member covers every service.
    """
    needed = set(services)
    if not needed:
        return None

    # Active media_crew users.
    user_resp = (
        supabase.schema("media_scheduling")
        .table("authorized_users")
        .select("id, name, role, phone_number, email, linked_identity, active, created_at, updated_at")
        .eq("role", "media_crew")
        .eq("active", True)
        .order("id", desc=False)
        .execute()
    )
    user_rows = user_resp.data or []
    if not user_rows:
        return None

    user_ids = [int(r["id"]) for r in user_rows]

    # Their skills.
    skills_resp = (
        supabase.schema("media_scheduling")
        .table("crew_skills")
        .select("user_id, skill")
        .in_("user_id", user_ids)
        .execute()
    )
    skills_rows = skills_resp.data or []

    skills_by_user: dict[int, set[str]] = {}
    for row in skills_rows:
        skills_by_user.setdefault(int(row["user_id"]), set()).add(row["skill"])

    for row in user_rows:
        uid = int(row["id"])
        owned = skills_by_user.get(uid, set())
        if needed.issubset(owned):
            return AuthorizedUser.model_validate(row)

    return None

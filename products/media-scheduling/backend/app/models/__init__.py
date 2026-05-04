"""Domain models — minimal Pydantic representations of `media_scheduling.*` rows.

The product uses the Supabase client (`app/database.py`) for IO, NOT SQLAlchemy.
These models are Pydantic value objects used by services to type-narrow row dicts
returned by Supabase. They mirror the columns landed in
`migrations/002_initial_schema.sql` exactly — keep in sync.

Engineer D (Phase 4) ships ONLY the columns/relationships its scheduling /
calendar / maps services touch. Engineer C (Phase 3) may add fields to these
same models for admin-router consumption — merge will dedupe (architect
intervenes on column conflicts).
"""

from app.models.appointment import Appointment
from app.models.authorized_user import AuthorizedUser
from app.models.condominium import Condominium
from app.models.crew_skill import CrewSkill
from app.models.oauth_credential import OAuthCredential
from app.models.property import Property
from app.models.route_group import RouteGroup
from app.models.service_type import ServiceType

__all__ = [
    "Appointment",
    "AuthorizedUser",
    "Condominium",
    "CrewSkill",
    "OAuthCredential",
    "Property",
    "RouteGroup",
    "ServiceType",
]

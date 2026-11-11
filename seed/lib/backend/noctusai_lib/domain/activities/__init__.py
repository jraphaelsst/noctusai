"""Activities -- tasks / calls / meetings / visits linked to any entity, as an L1 seed organ (CRM vertical, W1-5).

One activity = something a person must do about `(entity_kind, entity_id)` by `due_at`, assigned to a user, done or not.
The market's activity TYPES are DATA seeded from
`CrmPreset.activity_types`; the org edits them. Every create / complete / reopen / reassign / reschedule / edit / cancel is one
row-locked RPC that updates the activity AND appends an immutable intent-named event in the same transaction
(`KB § PATTERNS/architect/event-oriented-architecture.md`). The assignee is a plain user id validated against org membership.

Mount it from a product:

    app = create_product_app(..., organs=[mount_activities(schema="crm", auth_dependency=..., get_admin_client=..., get_core_client=..., preset=PRESET)])
    sql = activities_migration(ActivitiesConfig.for_preset("crm", PRESET), "crm")      # -> noctus.dev.render_organ_migration organ=activities
"""
from .config import ActivitiesConfig, ActivitiesContext
from .errors import ActivitiesError
from .guards import activities_guard_probes
from .pages import ACTIVITIES_PAGES
from .router import make_activities_router
from .sql import ACTIVITIES_MIGRATION_HEADER, ACTIVITIES_TABLES, APPEND_ONLY_TABLES, activities_migration
from .types import (
    ACTIVITY_EVENTS,
    ACTIVITY_KINDS,
    ACTIVITY_OUTCOMES,
    GENERIC_ACTIVITY_TYPES,
    ActivityTypeSpec,
)

__all__ = [
    "ACTIVITIES_MIGRATION_HEADER",
    "ACTIVITIES_PAGES",
    "ACTIVITIES_TABLES",
    "ACTIVITY_EVENTS",
    "ACTIVITY_KINDS",
    "ACTIVITY_OUTCOMES",
    "APPEND_ONLY_TABLES",
    "ActivitiesConfig",
    "ActivitiesContext",
    "ActivitiesError",
    "ActivityTypeSpec",
    "GENERIC_ACTIVITY_TYPES",
    "activities_guard_probes",
    "activities_migration",
    "make_activities_router",
]

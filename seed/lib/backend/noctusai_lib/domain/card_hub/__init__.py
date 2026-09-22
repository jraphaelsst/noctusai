"""Card hub — the Trello-shaped detail surface of one entity row.

Notes (one description + many comments, soft-deleted), an org tag catalogue
+ per-card tag links, assignable members, checklists with served progress,
operator-authored checklist lines, LGPD-complete documents (access log,
short-TTL signed URLs, table-driven retention + an explicitly-registered
sweep), reminders, a unified cursor-paged timeline with a gatherer registry,
and the badge row.

WHERE IT CAME FROM
------------------
Social-wiring's `app/modules/card_hub/` (lead-card-hub P2), whose own project
file recorded the debt: "lifting later must be a MOVE, not a rewrite" (D13/S3).
This package is that move — bodies verbatim, literal table/FK names replaced by
the `CardHubConfig` fields they were always instances of. Social-wiring's
tables are the `table_prefix="cliente"` defaults, so it adopts this with zero
DDL; a new product (igig's `lead`) gets the same card from a config literal
and `card_hub_migration(cfg, schema)`.

WHAT STAYS IN THE PRODUCT
-------------------------
Anything that is ABOUT the product's domain plugs in through a named seam:
extra timeline kinds (`timeline_gatherers`), extra badges / resumo keys
(`badge_extensions` / `resumo_extensions`), retention policy + extra document
columns (`DocumentoPolicy`), a post-upload hook (`card_hub_routers(...,
documento_upload_hook=...)`), and the entity read itself (`ensure_entity`).

Seam: the PostgREST `db` client (like `noctusai_lib.domain.pipeline`); the
fake is `noctusai_lib.testing.MockSupabaseClient`. There is no `RecordStore`
path yet — see the remediation marker below.

Design: `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`.
"""
# NOC-REMEDIATE[card-hub-recordstore]: no RecordStore path — a product on
# noctusai_lib.integrations.persistence.RecordStore (igig's SQLite dev loop)
# reaches the card hub through its Supabase client until the store grows the
# in_/ilike/is_/count shapes these reads need (tech-lead decision D-A1). — 2026-09-22
from . import badges, checklist_extras, documentos, lembretes, services, timeline
from .badges import compute_badges, get_card_resumo
from .config import (
    BadgeExtension,
    CardHubConfig,
    CardHubContext,
    CardHubTables,
    DocumentoPolicy,
    EntityGetter,
    MemberSource,
    ResumoExtension,
)
from .documentos import register_retention_sweep
from .gatherers import SEED_GATHERERS, Gatherer
from .router import DocumentoUploadHook, card_hub_routers
from .services import ensure_entity
from .sql import card_hub_migration
from .timeline import decode_cursor, encode_cursor, get_timeline

__all__ = [
    "BadgeExtension",
    "CardHubConfig",
    "CardHubContext",
    "CardHubTables",
    "DocumentoPolicy",
    "DocumentoUploadHook",
    "EntityGetter",
    "Gatherer",
    "MemberSource",
    "ResumoExtension",
    "SEED_GATHERERS",
    "badges",
    "card_hub_migration",
    "card_hub_routers",
    "checklist_extras",
    "compute_badges",
    "decode_cursor",
    "documentos",
    "encode_cursor",
    "ensure_entity",
    "get_card_resumo",
    "get_timeline",
    "lembretes",
    "register_retention_sweep",
    "services",
    "timeline",
]

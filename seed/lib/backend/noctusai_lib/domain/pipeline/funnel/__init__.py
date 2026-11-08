"""Funnel organ — ONE board + card API for every product ("same component, different context").

Composes `noctusai_lib.domain.pipeline` (stages, ordering, `move_card`) and
`noctusai_lib.domain.card_hub` and adds the card DTO, create/edit, lose/reopen/
archive, stage gates and product actions. A product declares a `FunnelConfig`
and calls `mount_funnel`; the wire contract is `projects/noc-funnel/CONTRACT.md`.

Backend notes
-------------
* Tenancy is explicit: ``tenancy="org"`` refuses a missing org (500), never
  widening to all tenants; ``tenancy="platform"`` scopes to one declared
  ``platform_org_id`` (see `config`).
* DDL: `pipeline_migration(cfg.pipeline, schema, tier=...)` emits the stages +
  append-only history tables (service-role only) and the card columns;
  `card_hub_migration` emits the hub tables. Both are idempotent.
* The card hub's tables are `org_id NOT NULL` — a platform funnel's hub rows
  carry its `platform_org_id`; its `CardHubConfig.ensure_entity` is mandatory.
* Timeline: register `movimentos_gatherer(cfg.pipeline)` under `"movimento"` in
  the card hub's `timeline_gatherers` to show stage moves in the card timeline.
* Errors ride the platform envelope (`{"error": {"code", "message",
  "details"}}`); codes in `errors`.
"""
from .config import (
    CANONICAL_STATUSES,
    FunnelAction,
    FunnelConfig,
    FunnelContext,
    FunnelGate,
    LostReason,
    Pendencia,
)
from .errors import FunnelError
from .gates import GateRefused
from .mount import mount_funnel
from .router import pipeline_board_router
from .schemas import CardDTO

__all__ = [
    "CANONICAL_STATUSES",
    "CardDTO",
    "FunnelAction",
    "FunnelConfig",
    "FunnelContext",
    "FunnelError",
    "FunnelGate",
    "GateRefused",
    "LostReason",
    "Pendencia",
    "mount_funnel",
    "pipeline_board_router",
]

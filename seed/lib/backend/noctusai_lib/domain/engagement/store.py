"""Engagement rule store -- `OrgTableStore` over `eng_point_rules` / `eng_badge_rules` (the ledger has its own seam)."""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain._organ_common import OrgTableStore, TableSpec, UniqueKey, make_org_table_store
from noctusai_lib.domain.engagement.config import EngagementConfig
from noctusai_lib.domain.engagement.sql import UQ_BADGE_RULES, UQ_POINT_RULES


def engagement_table_specs(cfg: EngagementConfig) -> dict[str, TableSpec]:
    p = cfg.table_prefix
    return {
        "point_rules": TableSpec(cfg.table("point_rules"), unique=(UniqueKey(UQ_POINT_RULES.format(p=p), ("source", "action")),)),
        "badge_rules": TableSpec(cfg.table("badge_rules"), unique=(UniqueKey(UQ_BADGE_RULES.format(p=p), ("badge_id",)),)),
    }


def build_engagement_store(
    cfg: EngagementConfig, *, use_fake: bool = False, supabase_client: Any = None, schema: Optional[str] = None
) -> OrgTableStore:
    return make_org_table_store(engagement_table_specs(cfg), use_fake=use_fake, supabase_client=supabase_client, schema=schema)


__all__ = ["build_engagement_store", "engagement_table_specs"]

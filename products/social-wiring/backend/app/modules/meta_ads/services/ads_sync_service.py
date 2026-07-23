"""Meta Ads console — sync service (W2.2/W2.3). Idempotent upserts from
``noctusai_lib.integrations.meta`` into the ``social_wiring`` schema's
four ``ads_*`` tables (migration ``030_meta_ads.sql``).

Zero Graph HTTP here — every Meta call goes through the injected
``adapter: MetaAdapter`` (Fake in tests, ``MetaOAuthAdapter`` in
production via ``app.services.meta.get_meta_adapter``). This module is
pure orchestration + the DB write shape.

No-silent-error contract (roadmap Anti-goals / CLAUDE.md § no-silent-
errors): a ``MetaGraphError`` (e.g. ``ads_read`` not yet granted,
Graph-side throttling) is NEVER caught here — it propagates to the
caller (the router's ``handle_meta_graph_error`` uniform gate, or the
scheduler's per-org warning-log-and-continue). A sync that silently
writes nothing on a Graph failure is exactly the failure mode this
initiative exists to prevent.

DI seam: ``AdsSyncService(admin_supabase=...)`` — same Class-B
constructor-injection shape as
``app.modules.youtube.services.snapshot_service.SnapshotService``
(``KB § PATTERNS/backend/di-test-seam.md``). Tests inject a fake
Supabase-shaped admin client; production code passes the real
``get_admin_client()``.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.meta import (
    Ad,
    AdAccount,
    AdActivity,
    AdCampaign,
    AdInsightsSeries,
    AdSet,
    MetaAdapter,
)

from app.modules.meta_ads.services.money import (
    cents_from_major_unit_float,
    cents_from_minor_unit_string,
    safe_int,
)

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


class AdsSyncServiceError(Exception):
    """Raised on an unrecoverable sync failure (never used to swallow a
    ``MetaGraphError`` — that always propagates verbatim; this wraps
    non-Graph failures, e.g. an admin-client write error, with context
    the caller can log)."""


def _bare_account_id(ad_account_id: str) -> str:
    return ad_account_id[4:] if ad_account_id.startswith("act_") else ad_account_id


def _acct_prefixed(ad_account_id: str) -> str:
    return (
        ad_account_id
        if ad_account_id.startswith("act_")
        else f"act_{ad_account_id}"
    )


def _breakdown_key(breakdown: dict[str, Any]) -> str | None:
    """Render a requested-breakdown dimension map to the ``breakdown_key``
    string column (e.g. ``{"publisher_platform": "instagram"}`` →
    ``"publisher_platform=instagram"``). Empty/absent breakdown → ``None``
    (the unbroken-total row) — see the migration's ``breakdown_key_norm``
    generated column for how the NULL case dedupes under the UNIQUE
    constraint."""
    if not breakdown:
        return None
    return ",".join(f"{k}={v}" for k, v in sorted(breakdown.items()))


def _monthly_chunks(today: date, months: int) -> list[tuple[date, date]]:
    """Split ``[today - months calendar-months, today]`` into ``months``
    consecutive (since, until) windows, oldest first — calendar-month
    arithmetic (not a fixed 30-day stride) so boundaries land on sensible
    dates. Chunking (rather than one 12-month ``time_increment=1`` pull)
    keeps each Graph round-trip bounded and spreads rate-limit exposure
    (Graph code 17/613 = throttling — roadmap O4) across N calls."""
    boundaries = [today]
    cursor = today
    for _ in range(months):
        cursor = _shift_months(cursor, -1)
        boundaries.append(cursor)
    boundaries.reverse()  # oldest -> newest
    return [
        (boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)
    ]


def _shift_months(d: date, delta: int) -> date:
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class AdsSyncService:
    """Per-call sync worker. Admin client used for ALL writes (service
    role) — same convention as ``YouTube``'s ``SnapshotService``."""

    def __init__(self, *, admin_supabase: Any) -> None:
        self._admin = admin_supabase

    # ─── W2.2 — hierarchy + account sync ───────────────────────────────

    def sync_accounts(self, *, org_id: UUID, adapter: MetaAdapter) -> int:
        """``list_ad_accounts`` → upsert ``ads_accounts``. Returns the
        count of accounts upserted."""
        accounts = adapter.list_ad_accounts()
        now_iso = datetime.now(timezone.utc).isoformat()
        count = 0
        for acct in accounts:
            row = self._account_row(acct, org_id=org_id, synced_at=now_iso)
            (
                self._admin
                .schema(_SCHEMA)
                .table("ads_accounts")
                .upsert(row, on_conflict="org_id,act_id")
                .execute()
            )
            count += 1
        return count

    def sync_hierarchy(
        self, *, org_id: UUID, adapter: MetaAdapter, ad_account_id: str
    ) -> dict[str, int]:
        """``list_ad_campaigns`` + (for each) ``list_ad_sets`` +
        ``list_ads`` → upsert the unified ``ads_objects`` hierarchy.
        Returns per-level upsert counts."""
        acct = _acct_prefixed(ad_account_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        counts = {"campaigns": 0, "adsets": 0, "ads": 0}

        campaigns = adapter.list_ad_campaigns(ad_account_id)
        for camp in campaigns:
            self._upsert_object(
                self._campaign_row(camp, org_id=org_id, act_id=acct, synced_at=now_iso)
            )
            counts["campaigns"] += 1

            adsets = adapter.list_ad_sets(ad_account_id, campaign_id=camp.id)
            for aset in adsets:
                self._upsert_object(
                    self._adset_row(
                        aset, org_id=org_id, act_id=acct,
                        parent_id=camp.id, synced_at=now_iso,
                    )
                )
                counts["adsets"] += 1

                ads = adapter.list_ads(ad_account_id, adset_id=aset.id)
                for ad in ads:
                    self._upsert_object(
                        self._ad_row(
                            ad, org_id=org_id, act_id=acct,
                            parent_id=aset.id, synced_at=now_iso,
                        )
                    )
                    counts["ads"] += 1

        return counts

    # ─── W2.2/W2.3 — insight snapshots ──────────────────────────────────

    def snapshot_campaign_insights(
        self,
        *,
        org_id: UUID,
        adapter: MetaAdapter,
        ad_account_id: str,
        since: date,
        until: date,
        time_increment: int | str = 1,
    ) -> int:
        """``ad_insights_series`` at CAMPAIGN level with
        ``time_increment=1`` (one row per campaign per day) → upsert
        ``ads_insight_snapshots``. This is both the daily-going-forward
        path (``since=yesterday, until=today``) and the per-chunk
        backfill path (``backfill_campaign_insights`` below)."""
        campaigns = adapter.list_ad_campaigns(ad_account_id)
        count = 0
        for camp in campaigns:
            series = adapter.ad_insights_series(
                camp.id,
                "campaign",
                time_range=(since, until),
                time_increment=time_increment,
            )
            count += self._persist_series(org_id=org_id, level="campaign", series=series)
        return count

    def _persist_series(
        self, *, org_id: UUID, level: str, series: AdInsightsSeries
    ) -> int:
        count = 0
        for row in series.rows:
            if not row.date_start:
                # `time_increment=1` always returns date_start on every
                # row; a missing one means the series wasn't day-bucketed
                # (e.g. a future `time_increment="all_days"` caller) —
                # this path is not exercised by W2 today, so a loud skip
                # beats a silent NULL-date insert.
                logger.warning(
                    "ads sync: insight row for %s (%s) has no date_start "
                    "— skipped (raw=%r)",
                    series.object_id, level, row.raw,
                )
                continue
            persisted = {
                "org_id": str(org_id),
                "object_id": series.object_id,
                "level": level,
                "date": row.date_start,
                "breakdown_key": _breakdown_key(row.breakdown),
                "spend_cents": cents_from_major_unit_float(row.metrics.get("spend")),
                "impressions": safe_int(row.metrics.get("impressions")),
                "reach": safe_int(row.metrics.get("reach")),
                # `frequency` is not in the seed's default
                # `_AD_INSIGHTS_SERIES_FIELDS` set — always NULL here
                # until a caller passes `fields=[...,"frequency"]`
                # explicitly (the column exists for that day, honestly
                # empty until then, never faked).
                "frequency": row.metrics.get("frequency"),
                "clicks": safe_int(row.metrics.get("clicks")),
                "cpc_cents": cents_from_major_unit_float(row.metrics.get("cpc")),
                "cpm_cents": cents_from_major_unit_float(row.metrics.get("cpm")),
                "ctr": row.metrics.get("ctr"),
                "actions": dict(row.actions),
                "action_values": dict(row.action_values),
                "raw": dict(row.raw),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            (
                self._admin
                .schema(_SCHEMA)
                .table("ads_insight_snapshots")
                .upsert(
                    persisted,
                    on_conflict="org_id,object_id,date,breakdown_key_norm",
                )
                .execute()
            )
            count += 1
        return count

    # ─── W2.2 — activity change-log ingest ──────────────────────────────

    def ingest_activities(
        self,
        *,
        org_id: UUID,
        adapter: MetaAdapter,
        ad_account_id: str,
        since: datetime,
        until: datetime,
    ) -> int:
        """``list_activities`` → insert ``ads_activity_events``, deduped
        on ``event_key`` (``ON CONFLICT DO NOTHING`` — append-only; a
        previously-ingested audit-log row is never overwritten).
        ``since``/``until`` are converted to the UNIX-epoch-seconds
        convention ``list_activities`` takes (see the seed adapter's
        docstring). Paginates defensively via the adapter (one month of
        the pilot account = ~500 events; roadmap O3)."""
        since_epoch = int(since.timestamp())
        until_epoch = int(until.timestamp())
        activities: list[AdActivity] = adapter.list_activities(
            ad_account_id, since_epoch, until_epoch
        )
        count = 0
        for act in activities:
            row = {
                "org_id": str(org_id),
                "event_key": act.id,
                "object_id": act.object_id,
                "object_level": act.object_level,
                "event_type": act.event_type,
                "occurred_at": act.occurred_at.isoformat() if act.occurred_at else None,
                "actor_name": act.actor_name,
                "actor_id": act.actor_id,
                "old_value": act.old_value,
                "new_value": act.new_value,
                "raw": dict(act.raw),
            }
            (
                self._admin
                .schema(_SCHEMA)
                .table("ads_activity_events")
                .upsert(row, on_conflict="org_id,event_key", ignore_duplicates=True)
                .execute()
            )
            count += 1
        return count

    # ─── W2.3 — 12-month backfill ────────────────────────────────────────

    def backfill_campaign_insights(
        self,
        *,
        org_id: UUID,
        adapter: MetaAdapter,
        ad_account_id: str,
        months: int = 12,
    ) -> int:
        """Campaign-level daily backfill, chunked into monthly
        ``time_range`` windows (never one 12-month
        ``time_increment=1`` pull — see ``_monthly_chunks``). Per the
        operator's decision (roadmap "Sync" row): campaign-level ONLY —
        ad-set / ad daily history is NOT backfilled; it is fetched LIVE
        on drill-down (W3's ``/children`` + ``/insights/series``
        adset|ad-level routes). Also runs one account + hierarchy sync
        so the backfill leaves ``ads_accounts``/``ads_objects``
        populated too."""
        today = datetime.now(timezone.utc).date()
        total = 0
        for chunk_since, chunk_until in _monthly_chunks(today, months):
            total += self.snapshot_campaign_insights(
                org_id=org_id,
                adapter=adapter,
                ad_account_id=ad_account_id,
                since=chunk_since,
                until=chunk_until,
            )
        self.sync_accounts(org_id=org_id, adapter=adapter)
        self.sync_hierarchy(org_id=org_id, adapter=adapter, ad_account_id=ad_account_id)
        return total

    def backfill_activities(
        self,
        *,
        org_id: UUID,
        adapter: MetaAdapter,
        ad_account_id: str,
        months: int = 12,
    ) -> int:
        """Activity change-log backfill over the same chunked window as
        ``backfill_campaign_insights`` — Graph's ``/activities`` edge
        pages defensively (roadmap O3: retention is NOT the binding
        constraint, volume is — one month of the pilot account is ~500
        events with a ``next`` cursor continuing further back)."""
        today = datetime.now(timezone.utc)
        total = 0
        for chunk_since, chunk_until in _monthly_chunks(today.date(), months):
            since_dt = datetime(
                chunk_since.year, chunk_since.month, chunk_since.day,
                tzinfo=timezone.utc,
            )
            until_dt = datetime(
                chunk_until.year, chunk_until.month, chunk_until.day,
                tzinfo=timezone.utc,
            )
            total += self.ingest_activities(
                org_id=org_id,
                adapter=adapter,
                ad_account_id=ad_account_id,
                since=since_dt,
                until=until_dt,
            )
        return total

    # ─── Row-shape builders ─────────────────────────────────────────────

    def _account_row(
        self, acct: AdAccount, *, org_id: UUID, synced_at: str
    ) -> dict[str, Any]:
        return {
            "org_id": str(org_id),
            "act_id": acct.id,
            "name": acct.name,
            "currency": acct.currency,
            "timezone_name": acct.timezone_name,
            "amount_spent_cents": cents_from_minor_unit_string(acct.amount_spent),
            "balance_cents": cents_from_minor_unit_string(acct.balance),
            "spend_cap_cents": cents_from_minor_unit_string(acct.spend_cap),
            "account_status": acct.account_status,
            "synced_at": synced_at,
            "raw": asdict(acct),
        }

    def _campaign_row(
        self, camp: AdCampaign, *, org_id: UUID, act_id: str, synced_at: str
    ) -> dict[str, Any]:
        return {
            "org_id": str(org_id),
            "object_id": camp.id,
            "level": "campaign",
            "parent_id": None,
            "act_id": act_id,
            "name": camp.name,
            "objective": camp.objective,
            "status": camp.status,
            "effective_status": camp.effective_status,
            # The seed's `AdCampaign` type does not expose a campaign-
            # level budget field (Meta's campaign-budget-optimization
            # value) — NULL, honestly, rather than a fake 0. Budgets
            # ARE captured at the ad-SET level below.
            "daily_budget_cents": None,
            "lifetime_budget_cents": None,
            "optimization_goal": None,
            "creative_id": None,
            "creative_thumbnail_url": None,
            "synced_at": synced_at,
            "raw": asdict(camp),
        }

    def _adset_row(
        self, aset: AdSet, *, org_id: UUID, act_id: str, parent_id: str, synced_at: str
    ) -> dict[str, Any]:
        return {
            "org_id": str(org_id),
            "object_id": aset.id,
            "level": "adset",
            "parent_id": parent_id,
            "act_id": act_id,
            "name": aset.name,
            "objective": None,
            "status": aset.status,
            "effective_status": aset.effective_status,
            # `AdSet.daily_budget` is already Meta's minor-unit int (see
            # `money.py` module docstring) — no conversion needed.
            "daily_budget_cents": aset.daily_budget,
            # The seed's `AdSet` type does not expose a lifetime-budget
            # field — NULL, honestly, until it does.
            "lifetime_budget_cents": None,
            "optimization_goal": aset.optimization_goal,
            "creative_id": None,
            "creative_thumbnail_url": None,
            "synced_at": synced_at,
            "raw": asdict(aset),
        }

    def _ad_row(
        self, ad: Ad, *, org_id: UUID, act_id: str, parent_id: str, synced_at: str
    ) -> dict[str, Any]:
        return {
            "org_id": str(org_id),
            "object_id": ad.id,
            "level": "ad",
            "parent_id": parent_id,
            "act_id": act_id,
            "name": ad.name,
            "objective": None,
            "status": ad.status,
            "effective_status": ad.effective_status,
            "daily_budget_cents": None,
            "lifetime_budget_cents": None,
            "optimization_goal": None,
            "creative_id": ad.creative_id,
            "creative_thumbnail_url": ad.creative_thumbnail_url,
            "synced_at": synced_at,
            "raw": asdict(ad),
        }

    def _upsert_object(self, row: dict[str, Any]) -> None:
        (
            self._admin
            .schema(_SCHEMA)
            .table("ads_objects")
            .upsert(row, on_conflict="org_id,object_id")
            .execute()
        )


__all__ = ["AdsSyncService", "AdsSyncServiceError"]

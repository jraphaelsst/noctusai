"""Daily Instagram catalog + snapshot sync — one Instagram-Login account.

Owner decision (2026-10-06): track EVERY post EVERY day with every metric
Meta serves for its media type. One run per (account, BRT day), guarded by
the shared ``snapshot_runs`` claim row:

1. claim the day (skip if done, or if another worker started < 2h ago);
2. ``GET /me`` → profile; ``GET /<IG_ID>/insights`` (total_value) for the
   PREVIOUS BRT day → one ``ig_profile_snapshots`` row (+ channel_info on the
   connection row);
3. walk ALL of ``/me/media`` (paged) — upsert the catalog page, then fetch
   each media's insights (metric set per product type) and upsert today's
   ``ig_media_snapshots`` rows + the catalog's ``latest_metrics``;
4. live Stories (``/me/stories``, 24h) the same way — after 24h Meta stops
   serving story insights, so each story gets snapshots only while live;
5. mark the run ``done`` (``note`` lists per-item failures) or ``error``.

Error policy (no silent errors):
- connection-level ``MetaGraphError`` (profile / account insights / media
  listing; any auth or rate-limit error anywhere) → the run is marked
  ``error`` and ``IgSyncError`` is raised with the Graph error as ``cause``;
- a per-media insights failure (e.g. a Story under 5 viewers = Graph code 10,
  a deleted post) → logged WARNING, counted in ``media_failed`` and named in
  ``errors``; the catalog row keeps its previous ``latest_metrics``; the run
  ends ``partial``;
- a metric Meta does not serve for that media → ``None`` in the row and its
  name in ``unsupported_metrics`` — never 0.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.meta import (
    IG_USER_TOTAL_VALUE_METRICS,
    IgMediaItem,
    MetaGraphError,
)

from app.modules.instagram.repository import (
    MEDIA_TYPED_METRICS,
    PROFILE_TYPED_METRICS,
    IgInsightsRepository,
    split_metrics,
    utc_iso,
)
from app.services.snapshot_runs import claim_snapshot_run, mark_snapshot_run

logger = logging.getLogger(__name__)

TZ_BR = ZoneInfo("America/Sao_Paulo")
REQUIRED_SCOPE = "instagram_business_manage_insights"
STALE_RUNNING_AFTER = timedelta(hours=2)
MEDIA_PAGE_SIZE = 50
# Stories are only insight-readable while live (24h).
STORY_LIFETIME = timedelta(hours=24)
_MAX_ERRORS_REPORTED = 20

AdapterBuilder = Callable[[UUID, UUID], Any]


class IgSyncError(Exception):
    """The run failed at connection level (marked ``error``). ``__cause__``
    carries the underlying ``MetaGraphError`` when Graph was the reason."""


@dataclass
class IgSyncOutcome:
    account_id: UUID
    snapshot_date: date
    status: str = "done"          # done | partial | skipped
    media_synced: int = 0         # catalog rows upserted (posts + live stories)
    stories_synced: int = 0
    snapshots_written: int = 0    # ig_media_snapshots rows
    profile_snapshot_written: bool = False
    media_failed: int = 0
    media_skipped: int = 0        # Graph item without a timestamp (logged)
    errors: list[str] = field(default_factory=list)

    def note(self) -> Optional[str]:
        if not self.errors:
            return None
        return f"{self.media_failed} item(s) failed: " + "; ".join(self.errors)


def granted_scopes(account: dict[str, Any]) -> Optional[set[str]]:
    """The scopes this connection holds, as stored at OAuth time
    (``metadata.granted_scopes`` — what Instagram actually granted — else
    ``metadata.scopes`` — what we requested). ``None`` when the row carries no
    scope record (manual-token connections): unknown, let Graph decide."""
    meta = account.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    for key in ("granted_scopes", "scopes"):
        val = meta.get(key)
        if isinstance(val, list):
            return {str(s) for s in val}
        if isinstance(val, str) and val:
            return {s.strip() for s in val.split(",") if s.strip()}
    return None


def missing_insights_scope(account: dict[str, Any]) -> bool:
    scopes = granted_scopes(account)
    return scopes is not None and REQUIRED_SCOPE not in scopes


def previous_day_window(snapshot_date: date) -> tuple[datetime, datetime]:
    """[D-1 00:00, D 00:00) in America/Sao_Paulo — the account-insights
    window stored on a day-D profile snapshot. Meta notes data may lag up to
    48h, so the most recent day can be revised upward later; we store the
    value as served at capture time (``captured_at``)."""
    until = datetime.combine(snapshot_date, time.min, tzinfo=TZ_BR)
    return until - timedelta(days=1), until


class IgSyncService:
    """Per-call worker. ``adapter_builder(account_id, org_id)`` returns an
    Instagram-Login adapter bound to that account (DI seam — production uses
    ``app.services.meta.get_instagram_login_adapter_for_account``; tests pass
    a builder returning the seed ``FakeInstagramLoginAdapter``)."""

    def __init__(
        self,
        *,
        repo: IgInsightsRepository,
        adapter_builder: AdapterBuilder,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._repo = repo
        self._build_adapter = adapter_builder
        self._now = now

    def run_for_account(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        snapshot_date: Optional[date] = None,
        force: bool = False,
    ) -> IgSyncOutcome:
        if snapshot_date is None:
            snapshot_date = self._now().astimezone(TZ_BR).date()
        outcome = IgSyncOutcome(account_id=account_id, snapshot_date=snapshot_date)
        admin = self._repo.client

        if not claim_snapshot_run(
            admin,
            account_id=account_id,
            snapshot_date=snapshot_date,
            force=force,
            stale_running_after=STALE_RUNNING_AFTER,
            now=self._now(),
        ):
            logger.info(
                "instagram sync: account=%s date=%s skipped (done or in progress)",
                account_id, snapshot_date,
            )
            outcome.status = "skipped"
            return outcome

        try:
            self._run_inner(org_id, account_id, snapshot_date, outcome)
        except Exception as exc:
            logger.error(
                "instagram sync: account=%s date=%s FAILED: %s",
                account_id, snapshot_date, exc, exc_info=True,
            )
            mark_snapshot_run(
                admin, account_id=account_id, snapshot_date=snapshot_date,
                status="error", note=str(exc),
            )
            raise IgSyncError(
                f"instagram sync failed for account {account_id} on {snapshot_date}: {exc}"
            ) from exc

        outcome.status = "partial" if outcome.media_failed else "done"
        mark_snapshot_run(
            admin, account_id=account_id, snapshot_date=snapshot_date,
            status="done", note=outcome.note(),
        )
        logger.info(
            "instagram sync: account=%s date=%s %s media=%d stories=%d snapshots=%d failed=%d skipped=%d",
            account_id, snapshot_date, outcome.status, outcome.media_synced,
            outcome.stories_synced, outcome.snapshots_written, outcome.media_failed,
            outcome.media_skipped,
        )
        return outcome

    # ─── pipeline ───────────────────────────────────────────────────────
    def _run_inner(
        self, org_id: UUID, account_id: UUID, snapshot_date: date, outcome: IgSyncOutcome
    ) -> None:
        adapter = self._build_adapter(account_id, org_id)
        now = self._now()

        profile = adapter.get_profile()
        since, until = previous_day_window(snapshot_date)
        user = adapter.get_user_insights(
            profile.ig_user_id,
            list(IG_USER_TOTAL_VALUE_METRICS),
            metric_type="total_value",
            period="day",
            since=int(since.timestamp()),
            until=int(until.timestamp()),
        )
        typed, extra = split_metrics(user.totals, PROFILE_TYPED_METRICS)
        self._repo.upsert_profile_snapshot(
            {
                "org_id": str(org_id),
                "account_id": str(account_id),
                "snapshot_date": snapshot_date.isoformat(),
                "ig_user_id": profile.ig_user_id,
                "username": profile.username,
                "followers_count": profile.followers_count,
                "follows_count": profile.follows_count,
                "media_count": profile.media_count,
                **typed,
                "extra_metrics": extra,
                "unsupported_metrics": list(user.unsupported),
                "window_since": utc_iso(since),
                "window_until": utc_iso(until),
                "captured_at": utc_iso(now),
            }
        )
        outcome.profile_snapshot_written = True
        self._repo.update_account_sync(
            account_id,
            org_id,
            channel_info={
                "channel_id": profile.ig_user_id,
                "title": profile.username,
                "username": profile.username,
                "name": profile.name,
                "profile_picture_url": profile.profile_picture_url,
                "followers_count": profile.followers_count,
                "follows_count": profile.follows_count,
                "media_count": profile.media_count,
                "biography": profile.biography,
                "website": profile.website,
                "account_type": profile.account_type,
            },
            last_synced_at=now,
        )

        cursor: Optional[str] = None
        while True:
            page = adapter.list_media(cursor=cursor, limit=MEDIA_PAGE_SIZE)
            self._ingest(adapter, org_id, account_id, snapshot_date, page.items, outcome, now)
            cursor = page.next_cursor
            if not cursor:
                break

        try:
            stories = adapter.list_stories()
        except MetaGraphError as exc:
            if exc.is_auth_error or exc.is_rate_limited:
                raise
            self._record_failure(outcome, "stories", exc)
            stories = []
        live = [
            s for s in stories
            if s.timestamp is None or now - s.timestamp <= STORY_LIFETIME
        ]
        before = outcome.media_synced
        self._ingest(adapter, org_id, account_id, snapshot_date, live, outcome, now)
        outcome.stories_synced = outcome.media_synced - before

    def _ingest(
        self,
        adapter: Any,
        org_id: UUID,
        account_id: UUID,
        snapshot_date: date,
        items: list[IgMediaItem],
        outcome: IgSyncOutcome,
        now: datetime,
    ) -> None:
        catalog: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        latest: list[dict[str, Any]] = []
        for item in items:
            if item.timestamp is None:
                outcome.media_skipped += 1
                logger.warning(
                    "instagram sync: account=%s media=%s has no timestamp — not cataloged",
                    account_id, item.id,
                )
                continue
            catalog.append(
                {
                    "org_id": str(org_id),
                    "account_id": str(account_id),
                    "ig_media_id": item.id,
                    "caption": item.caption,
                    "media_type": item.media_type,
                    "media_product_type": item.media_product_type,
                    "permalink": item.permalink,
                    "thumbnail_url": item.thumbnail_url,
                    "media_url": item.media_url,
                    "published_at": utc_iso(item.timestamp),
                    "like_count": item.like_count,
                    "comments_count": item.comments_count,
                    "is_shared_to_feed": item.is_shared_to_feed,
                    "synced_at": utc_iso(now),
                }
            )
            try:
                res = adapter.get_media_insights(
                    item.id, item.media_product_type, media_type=item.media_type
                )
            except MetaGraphError as exc:
                if exc.is_auth_error or exc.is_rate_limited:
                    raise
                self._record_failure(outcome, item.id, exc)
                continue
            typed, extra = split_metrics(res.values, MEDIA_TYPED_METRICS)
            snapshots.append(
                {
                    "org_id": str(org_id),
                    "account_id": str(account_id),
                    "ig_media_id": item.id,
                    "media_product_type": item.media_product_type,
                    "snapshot_date": snapshot_date.isoformat(),
                    **typed,
                    "extra_metrics": extra,
                    "unsupported_metrics": list(res.unsupported),
                    "captured_at": utc_iso(now),
                }
            )
            latest.append(
                {
                    "org_id": str(org_id),
                    "account_id": str(account_id),
                    "ig_media_id": item.id,
                    "latest_metrics": dict(res.values),
                    "latest_snapshot_date": snapshot_date.isoformat(),
                }
            )
        # Catalog first: the latest-metrics batch upserts onto existing rows.
        self._repo.upsert_catalog(catalog)
        self._repo.upsert_media_snapshots(snapshots)
        self._repo.upsert_latest(latest)
        outcome.media_synced += len(catalog)
        outcome.snapshots_written += len(snapshots)

    @staticmethod
    def _record_failure(outcome: IgSyncOutcome, what: str, exc: MetaGraphError) -> None:
        outcome.media_failed += 1
        logger.warning(
            "instagram sync: %s insights failed (code=%s): %s", what, exc.code, exc
        )
        if len(outcome.errors) < _MAX_ERRORS_REPORTED:
            outcome.errors.append(f"{what}: [{exc.code}] {exc}")


__all__ = [
    "IgSyncError",
    "IgSyncOutcome",
    "IgSyncService",
    "REQUIRED_SCOPE",
    "granted_scopes",
    "missing_insights_scope",
    "previous_day_window",
]

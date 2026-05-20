"""Local mirror of the connected channel's video catalog.

Phase 3 surface: read-side serves the Videos page + Dashboard from a
local DB cache; write-side is a single ``sync`` operation that pulls
all-pages from YouTube via :class:`YouTubeService` and upserts rows into
``social_wiring.video_cache``.

Why a cache: a 500-video channel costs 20 quota units to fully list
(2 per page × 10 pages of 50). The Dashboard hits the data multiple
times per session; without a cache we'd burn quota on every dashboard
load. The cache makes lookups free; sync is explicit (POST /sync), not
implicit.

The ``uploaded_via_app`` flag is computed at sync time by joining against
``upload_jobs.youtube_video_id`` (where ``status='published'``) — that
flag is what powers the Videos page's app-badge + the Dashboard's
"recent uploads via app" panel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.modules.youtube.services.youtube import (
    VideoSummary,
    YouTubeService,
    YouTubeServiceError,
)

logger = logging.getLogger(__name__)

_TABLE = "video_cache"
_SCHEMA = "social_wiring"
_UPLOAD_JOBS = "upload_jobs"


class VideoCacheError(Exception):
    """All cache-side failures route through this — routers translate to
    HTTP. Distinct from YouTubeServiceError so router handlers can pick
    the right status (cache write failure vs YouTube API failure)."""


@dataclass
class SyncOutcome:
    """What :meth:`VideoCacheService.sync` returns to the router.

    `inserted + updated` may equal `fetched` (full hit), be less than
    `fetched` (some rows skipped), or be greater than `fetched` (a stale
    DB row was overwritten by an unmodified API response — counts only
    new/changed UPSERT actions, but the upsert itself happens on every
    fetched row regardless)."""

    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    pages: int = 0
    quota_units_estimated: int = 0
    last_synced_at: datetime | None = None


class VideoCacheService:
    """Per-request collaborator. Constructed from the user-scoped supabase
    client (read path; RLS-bounded) and the service-role admin client
    (write path; service-role bypasses RLS during sync upserts).

    The two-client split mirrors UploadService and follows the same
    rationale: reads must be RLS-bounded so a user can't peek across
    orgs, but the sync writer has no JWT context bound to a specific
    org's invocation that the policy could check against (the org_id
    flows through the call-site, not the JWT)."""

    def __init__(
        self,
        *,
        user_supabase,
        admin_supabase,
        youtube_service: YouTubeService,
    ):
        self._user = user_supabase
        self._admin = admin_supabase
        self._youtube = youtube_service

    # ─── Read path (RLS-bounded; user_supabase) ────────────────────────
    def list(
        self,
        *,
        org_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
        uploaded_via_app: bool | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        """Return (items, next_cursor, total_known) for the Videos page.

        Cursor is the ISO-8601 ``published_at`` of the last item plus its
        ``id`` (tie-breaker for items with identical published_at). Both
        encoded as ``"<ts>|<id>"``. Opaque to the UI — never parsed
        client-side."""
        builder = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*", count="exact")
            .eq("org_id", str(org_id))
            .order("published_at", desc=True)
            .order("id", desc=True)            # stable tie-breaker
            .limit(limit + 1)                  # +1 to detect "has next page"
        )
        if uploaded_via_app is not None:
            builder = builder.eq("uploaded_via_app", uploaded_via_app)
        if cursor:
            ts_part, _, id_part = cursor.partition("|")
            if ts_part:
                # Strict less-than on (published_at, id) — emulated as
                # OR(published_at < ts, AND(published_at = ts, id < cursor_id)).
                # PostgREST `or` syntax accepts the compound expression below.
                # Falling back to the simpler `lt` filter on published_at when
                # id is missing keeps the query honest for partial cursors.
                if id_part:
                    builder = builder.or_(
                        f"published_at.lt.{ts_part},"
                        f"and(published_at.eq.{ts_part},id.lt.{id_part})"
                    )
                else:
                    builder = builder.lt("published_at", ts_part)

        response = builder.execute()
        rows = list(response.data or [])
        total_known = getattr(response, "count", None) or len(rows)

        next_cursor: str | None = None
        if len(rows) > limit:
            tail = rows[limit - 1]
            next_cursor = f"{tail.get('published_at') or ''}|{tail['id']}"
            rows = rows[:limit]

        return rows, next_cursor, total_known

    def get(self, *, org_id: UUID, youtube_video_id: str) -> dict[str, Any] | None:
        """Single-row lookup. Returns the cache row (decrypted, RLS-checked)
        or None when the video isn't in the cache yet."""
        response = (
            self._user
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("youtube_video_id", youtube_video_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    # ─── Write path (service-role; admin_supabase) ─────────────────────
    def sync(self, *, org_id: UUID) -> SyncOutcome:
        """Pull the channel's full video list from YouTube and upsert
        into the cache. Walks all pages until ``next_page_token`` is
        None.

        Returns counts so the UI can display "synced N videos in M pages
        (~K quota units)" without a second round trip. Raises
        :class:`VideoCacheError` on any cache-side write failure;
        re-raises :class:`YouTubeServiceError` so routers translate
        YouTube-API failures distinctly from cache failures."""
        outcome = SyncOutcome()
        page_token: str | None = None

        # First pass: discover which youtube_video_ids in this org came
        # from our own upload pipeline. One query is enough — the join
        # of the (potentially large) cache against (modest) upload_jobs
        # is faster as a Python set than as a Postgres IN-clause when
        # the set is small.
        app_uploaded_ids = self._fetch_app_uploaded_ids(org_id=org_id)

        while True:
            try:
                items, page_token = self._youtube.list_all_videos(
                    org_id=org_id, page_token=page_token
                )
            except YouTubeServiceError:
                # Re-raise unchanged — routers map YouTubeServiceError to
                # 502/503 ("YouTube API said no") distinct from
                # VideoCacheError ("we failed to write what YouTube returned").
                raise

            outcome.pages += 1
            outcome.fetched += len(items)
            outcome.quota_units_estimated += 2  # search.list + videos.list

            if items:
                inserted, updated = self._upsert_batch(
                    org_id=org_id,
                    items=items,
                    app_uploaded_ids=app_uploaded_ids,
                )
                outcome.inserted += inserted
                outcome.updated += updated

            if not page_token:
                break

        outcome.last_synced_at = datetime.now(timezone.utc)
        return outcome

    # ─── Internals ─────────────────────────────────────────────────────
    def _fetch_app_uploaded_ids(self, *, org_id: UUID) -> set[str]:
        """All YouTube IDs published via this product's upload pipeline.

        Filtered by ``status='published'`` so failed jobs (which carry
        no youtube_video_id) don't poison the set."""
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_UPLOAD_JOBS)
            .select("youtube_video_id")
            .eq("org_id", str(org_id))
            .eq("status", "published")
            .execute()
        )
        return {
            row["youtube_video_id"]
            for row in (response.data or [])
            if row.get("youtube_video_id")
        }

    def _upsert_batch(
        self,
        *,
        org_id: UUID,
        items: list[VideoSummary],
        app_uploaded_ids: set[str],
    ) -> tuple[int, int]:
        """Batch-upsert a page of VideoSummary rows. Returns (inserted, updated).

        Supabase's upsert returns the row data but doesn't distinguish
        insert vs update at the response level; we approximate by checking
        whether the row existed before via a pre-fetch of the ids in
        this batch. Cheap because the batch is at most 50 rows."""
        if not items:
            return 0, 0

        ids_in_batch = [item.video_id for item in items]
        existing_ids = self._existing_video_ids(
            org_id=org_id, video_ids=ids_in_batch
        )

        payload = [
            self._summary_to_row(
                item, org_id=org_id,
                uploaded_via_app=item.video_id in app_uploaded_ids,
            )
            for item in items
        ]

        try:
            (
                self._admin
                .schema(_SCHEMA)
                .table(_TABLE)
                .upsert(payload, on_conflict="org_id,youtube_video_id")
                .execute()
            )
        except Exception as exc:
            raise VideoCacheError(
                f"video_cache upsert failed for org_id={org_id}: {exc}"
            ) from exc

        updated = sum(1 for vid in ids_in_batch if vid in existing_ids)
        inserted = len(ids_in_batch) - updated
        return inserted, updated

    def _existing_video_ids(
        self, *, org_id: UUID, video_ids: list[str]
    ) -> set[str]:
        """Set of youtube_video_ids already in the cache for this org +
        the requested IDs. Cheap lookup used to compute insert vs update."""
        if not video_ids:
            return set()
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_TABLE)
            .select("youtube_video_id")
            .eq("org_id", str(org_id))
            .in_("youtube_video_id", video_ids)
            .execute()
        )
        return {row["youtube_video_id"] for row in (response.data or [])}

    @staticmethod
    def _summary_to_row(
        summary: VideoSummary,
        *,
        org_id: UUID,
        uploaded_via_app: bool,
    ) -> dict[str, Any]:
        """Translate a :class:`VideoSummary` (YouTube-API shape) into the
        cache-table row shape. Centralised so column-name drift surfaces
        in one place when the schema changes."""
        return {
            "org_id": str(org_id),
            "youtube_video_id": summary.video_id,
            "title": summary.title,
            "description": summary.description,
            "thumbnail_url": summary.thumbnail_url,
            "published_at": summary.published_at.isoformat(),
            "duration": summary.duration,
            "privacy_status": summary.privacy_status,
            "view_count": summary.view_count,
            "like_count": summary.like_count,
            "comment_count": summary.comment_count,
            "favorite_count": 0,                # not in VideoSummary; YouTube deprecated
            "tags": summary.tags,
            "category_id": summary.category_id,
            "uploaded_via_app": uploaded_via_app,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

"""Daily YouTube snapshot service — Phase 3 core.

Claim-row-guarded quota-spend: one snapshot per (account, date).
Each run:
  1. Claims a snapshot_runs row (status='running'); skips if already 'done'.
  2. Fetches fresh channel stats via channels.list?mine=True (1 unit).
  3. Updates integration_accounts.channel_info + last_synced_at.
  4. Upserts youtube_channel_snapshots for the date.
  5. Pages ALL uploads via the cheap uploads-playlist path (~3 units/page).
  6. Classifies each video as Short or regular; routes to youtube_shorts /
     youtube_videos; upserts youtube_video_snapshots.
  7. Marks snapshot_runs status='done'; sets 'error' + re-raises on failure.

Backfill: on first run for an account (catalog tables empty), reads existing
video_cache rows and seeds the catalog tables before the live API walk.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.youtube import classify_short

from app.modules.youtube.services.youtube import YouTubeService
from app.services.account_credentials import build_youtube_service_for_org
from app.services.integration_account_service import (
    IntegrationAccountService,
    build_integration_account_service,
)

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_TZ_BR = ZoneInfo("America/Sao_Paulo")


@dataclass
class SnapshotOutcome:
    """Return type for SnapshotService.run_for_account."""

    account_id: UUID
    snapshot_date: date
    skipped: bool = False              # True when a done row exists and not force
    videos_upserted: int = 0
    shorts_upserted: int = 0
    video_snapshots_upserted: int = 0
    backfilled: bool = False           # True when backfill_from_video_cache ran
    needs_probe_count: int = 0         # ambiguous items left for the probe tier
    # NOC-REMEDIATE[yt-shorts-probe] — ambiguous items not probed in v1;
    # a follow-up scheduler job can walk needs_probe items and resolve via
    # GET youtube.com/shorts/{id} HTTP probe (un-quota'd) + update the row. — 2026-06-02
    error: str | None = None


class SnapshotServiceError(Exception):
    """Raised on unrecoverable snapshot failure (after marking status='error')."""


class SnapshotService:
    """Per-call snapshot worker. Admin client used for ALL writes (service role).

    Construction: SnapshotService(admin_supabase=..., cfg=...)

    DI seam: ``yt_service_builder`` and ``ia_service_builder`` are optional
    callables injected at construction time. Production code leaves them ``None``
    (the real builders are used); tests pass in fakes without patching our symbols.
    Per KB § PATTERNS/backend/di-test-seam.md (Class-B, service DI).
    """

    def __init__(
        self,
        *,
        admin_supabase: Any,
        cfg: Any,
        yt_service_builder: Any = None,
        ia_service_builder: Any = None,
    ) -> None:
        self._admin = admin_supabase
        self._cfg = cfg
        # Optional DI seam — defaults to the real module-level builders.
        self._yt_service_builder = yt_service_builder or build_youtube_service_for_org
        self._ia_service_builder = ia_service_builder or build_integration_account_service

    # ─── Public API ─────────────────────────────────────────────────────

    def run_for_account(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        snapshot_date: date | None = None,
        force: bool = False,
    ) -> SnapshotOutcome:
        """Run a full daily snapshot for one account.

        Thread-safe via the snapshot_runs claim-row guard (UNIQUE constraint
        on (account_id, snapshot_date)). Idempotent: re-running the same
        day updates rows, never duplicates them.

        Args:
            org_id: The org that owns this account.
            account_id: The integration_accounts row to snapshot.
            snapshot_date: Defaults to today in America/Sao_Paulo.
            force: Re-run even if a 'done' row exists (overwrites snapshot data).
        """
        if snapshot_date is None:
            snapshot_date = datetime.now(_TZ_BR).date()

        outcome = SnapshotOutcome(account_id=account_id, snapshot_date=snapshot_date)

        # ── Step 1: claim row ──────────────────────────────────────────
        if not self._claim_run(account_id=account_id, snapshot_date=snapshot_date, force=force):
            logger.info(
                "snapshot_service: skipping account=%s date=%s (already done)",
                account_id, snapshot_date,
            )
            outcome.skipped = True
            return outcome

        try:
            self._run_inner(
                org_id=org_id,
                account_id=account_id,
                snapshot_date=snapshot_date,
                outcome=outcome,
            )
        except Exception as exc:
            logger.error(
                "snapshot_service: error for account=%s date=%s: %s",
                account_id, snapshot_date, exc,
                exc_info=True,
            )
            self._mark_run(account_id=account_id, snapshot_date=snapshot_date, status="error")
            outcome.error = str(exc)
            raise SnapshotServiceError(
                f"snapshot failed for account {account_id} on {snapshot_date}: {exc}"
            ) from exc

        self._mark_run(account_id=account_id, snapshot_date=snapshot_date, status="done")
        return outcome

    def backfill_from_video_cache(self, *, org_id: UUID, account_id: UUID) -> int:
        """Seed youtube_videos/youtube_shorts from existing video_cache rows.

        Called lazily by run_for_account when the catalog tables are empty
        for this account. Returns count of rows backfilled.

        Exposed publicly so callers can trigger it explicitly (e.g. a one-time
        migration endpoint) without running a full snapshot.
        """
        resp = (
            self._admin
            .schema(_SCHEMA)
            .table("video_cache")
            .select("*")
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            return 0

        count = 0
        for row in rows:
            self._backfill_one_row(row=row, org_id=org_id, account_id=account_id)
            count += 1

        logger.info(
            "snapshot_service: backfilled %d rows from video_cache for account=%s",
            count, account_id,
        )
        return count

    # ─── Inner pipeline ──────────────────────────────────────────────────

    def _run_inner(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        snapshot_date: date,
        outcome: SnapshotOutcome,
    ) -> None:
        # Build YouTube service pinned to this account (via DI seam or real builder).
        yt_svc: YouTubeService = self._yt_service_builder(
            self._admin, self._cfg, account_id=account_id
        )

        # ── Step 2: channel stats ─────────────────────────────────────
        info = yt_svc.get_channel_info(org_id=org_id)

        # ── Step 3: update integration_accounts ──────────────────────
        ia_svc = self._ia_service_builder(
            self._admin, encryption_key=self._cfg.encryption_key
        )
        channel_info_dict = {
            "channel_id": info.channel_id,
            "title": info.title,
            "thumbnail_url": getattr(info, "thumbnail_url", ""),
            "subscriber_count": info.subscriber_count,
            "video_count": info.video_count,
            "view_count": info.view_count,
        }
        ia_svc.update_channel_info(
            account_id,
            org_id,
            channel_info=channel_info_dict,    # dict — NOT json.dumps; JSONB fix applied
            status="validated",
            last_synced_at=datetime.now(timezone.utc),
        )

        # ── Step 4: upsert youtube_channel_snapshots ──────────────────
        (
            self._admin
            .schema(_SCHEMA)
            .table("youtube_channel_snapshots")
            .upsert(
                {
                    "account_id": str(account_id),
                    "org_id": str(org_id),
                    "snapshot_date": snapshot_date.isoformat(),
                    "subscriber_count": info.subscriber_count,
                    "view_count": info.view_count,
                    "video_count": info.video_count,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="account_id,snapshot_date",
            )
            .execute()
        )

        # ── Step 5: check if backfill needed, then page ALL uploads ───
        if self._catalog_is_empty(account_id=account_id):
            outcome.backfilled = True
            self.backfill_from_video_cache(org_id=org_id, account_id=account_id)

        app_uploaded_ids = self._fetch_app_uploaded_ids(org_id=org_id)

        page_token: str | None = None
        while True:
            items, page_token = yt_svc.list_all_videos_full(
                org_id=org_id,
                account_id=account_id,
                page_token=page_token,
                page_size=50,
            )
            for vf in items:
                classification = classify_short(vf)

                # ── Step 6a: route to catalog table ──────────────────
                catalog_row = {
                    "org_id": str(org_id),
                    "account_id": str(account_id),
                    "youtube_video_id": vf.id,
                    "title": vf.title,
                    "description": vf.description,
                    "thumbnail_url": vf.thumbnail_url,
                    "published_at": vf.published_at.isoformat() if vf.published_at else None,
                    "channel_id": vf.channel_id,
                    "tags": list(vf.tags),
                    "category_id": vf.category_id,
                    "duration_iso": vf.duration_iso,
                    "duration_seconds": vf.duration_seconds,
                    "privacy_status": str(vf.privacy_status) if vf.privacy_status != "unknown" else None,
                    "view_count": vf.view_count,
                    "like_count": vf.like_count,
                    "comment_count": vf.comment_count,
                    "favorite_count": 0,
                    "uploaded_via_app": vf.id in app_uploaded_ids,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }

                if classification.is_short:
                    catalog_row.update({
                        "detected_via": classification.detected_via,
                        "is_short_confidence": classification.confidence,
                        "classified_at": datetime.now(timezone.utc).isoformat(),
                    })
                    (
                        self._admin
                        .schema(_SCHEMA)
                        .table("youtube_shorts")
                        .upsert(catalog_row, on_conflict="account_id,youtube_video_id")
                        .execute()
                    )
                    outcome.shorts_upserted += 1
                else:
                    (
                        self._admin
                        .schema(_SCHEMA)
                        .table("youtube_videos")
                        .upsert(catalog_row, on_conflict="account_id,youtube_video_id")
                        .execute()
                    )
                    outcome.videos_upserted += 1

                if classification.needs_probe:
                    outcome.needs_probe_count += 1

                # ── Step 6b: upsert video snapshot ────────────────────
                kind = "short" if classification.is_short else "video"
                (
                    self._admin
                    .schema(_SCHEMA)
                    .table("youtube_video_snapshots")
                    .upsert(
                        {
                            "org_id": str(org_id),
                            "account_id": str(account_id),
                            "youtube_video_id": vf.id,
                            "kind": kind,
                            "snapshot_date": snapshot_date.isoformat(),
                            "view_count": vf.view_count,
                            "like_count": vf.like_count,
                            "comment_count": vf.comment_count,
                            "captured_at": datetime.now(timezone.utc).isoformat(),
                        },
                        on_conflict="account_id,youtube_video_id,snapshot_date",
                    )
                    .execute()
                )
                outcome.video_snapshots_upserted += 1

            if page_token is None:
                break

        logger.info(
            "snapshot_service: done account=%s date=%s videos=%d shorts=%d snapshots=%d needs_probe=%d",
            account_id, snapshot_date,
            outcome.videos_upserted, outcome.shorts_upserted,
            outcome.video_snapshots_upserted, outcome.needs_probe_count,
        )

    # ─── Claim-row helpers ───────────────────────────────────────────────

    def _claim_run(
        self, *, account_id: UUID, snapshot_date: date, force: bool
    ) -> bool:
        """Try to claim the snapshot_runs row. Returns True = proceed, False = skip.

        Uses upsert ON CONFLICT to atomically insert-or-check. If an existing
        'done' row is found and force=False, returns False (caller skips).
        """
        # Check for existing done row first.
        resp = (
            self._admin
            .schema(_SCHEMA)
            .table("snapshot_runs")
            .select("status")
            .eq("account_id", str(account_id))
            .eq("snapshot_date", snapshot_date.isoformat())
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows and rows[0].get("status") == "done" and not force:
            return False

        # Upsert 'running' (inserts fresh or resets an existing 'error' row).
        (
            self._admin
            .schema(_SCHEMA)
            .table("snapshot_runs")
            .upsert(
                {
                    "account_id": str(account_id),
                    "snapshot_date": snapshot_date.isoformat(),
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="account_id,snapshot_date",
            )
            .execute()
        )
        return True

    def _mark_run(
        self, *, account_id: UUID, snapshot_date: date, status: str
    ) -> None:
        (
            self._admin
            .schema(_SCHEMA)
            .table("snapshot_runs")
            .update({"status": status})
            .eq("account_id", str(account_id))
            .eq("snapshot_date", snapshot_date.isoformat())
            .execute()
        )

    # ─── Backfill helpers ────────────────────────────────────────────────

    def _catalog_is_empty(self, *, account_id: UUID) -> bool:
        """Return True when youtube_videos + youtube_shorts both have zero rows."""
        for table in ("youtube_videos", "youtube_shorts"):
            resp = (
                self._admin
                .schema(_SCHEMA)
                .table(table)
                .select("id", count="exact")
                .eq("account_id", str(account_id))
                .limit(1)
                .execute()
            )
            count = getattr(resp, "count", None) or len(resp.data or [])
            if count:
                return False
        return True

    def _backfill_one_row(
        self, *, row: dict[str, Any], org_id: UUID, account_id: UUID
    ) -> None:
        """Convert one video_cache row to youtube_videos/youtube_shorts.

        Builds a minimal VideoFull-like object so classify_short works.
        Duration in video_cache is stored as ISO string (e.g. 'PT5M30S');
        parse to seconds for classification.
        """
        from noctusai_lib.integrations.youtube.types import VideoFull
        from datetime import datetime as _dt

        duration_iso = row.get("duration") or ""
        duration_seconds = _parse_iso_duration(duration_iso)
        tags = row.get("tags") or []

        # Build a minimal VideoFull for classification (no API call).
        try:
            pub = _dt.fromisoformat(row["published_at"]) if row.get("published_at") else _dt.now(timezone.utc)
        except (ValueError, TypeError):
            pub = _dt.now(timezone.utc)

        vf = VideoFull(
            id=row["youtube_video_id"],
            title=row.get("title") or "",
            description=row.get("description") or "",
            channel_id="",
            published_at=pub,
            duration_seconds=duration_seconds,
            duration_iso=duration_iso,
            thumbnail_url=row.get("thumbnail_url") or "",
            privacy_status=row.get("privacy_status") or "unknown",
            view_count=int(row.get("view_count") or 0),
            like_count=int(row.get("like_count") or 0),
            comment_count=int(row.get("comment_count") or 0),
            tags=tuple(tags) if isinstance(tags, list) else (tags if isinstance(tags, tuple) else ()),
            category_id=row.get("category_id") or "",
        )

        classification = classify_short(vf)
        synced_at = row.get("synced_at") or datetime.now(timezone.utc).isoformat()
        catalog_row = {
            "org_id": str(org_id),
            "account_id": str(account_id),
            "youtube_video_id": vf.id,
            "title": vf.title,
            "description": vf.description,
            "thumbnail_url": vf.thumbnail_url,
            "published_at": vf.published_at.isoformat(),
            "channel_id": vf.channel_id,
            "tags": list(vf.tags),
            "category_id": vf.category_id,
            "duration_iso": vf.duration_iso,
            "duration_seconds": vf.duration_seconds,
            "privacy_status": str(vf.privacy_status) if vf.privacy_status != "unknown" else None,
            "view_count": vf.view_count,
            "like_count": vf.like_count,
            "comment_count": vf.comment_count,
            "favorite_count": int(row.get("favorite_count") or 0),
            "uploaded_via_app": bool(row.get("uploaded_via_app", False)),
            "synced_at": synced_at,
        }

        if classification.is_short:
            catalog_row.update({
                "detected_via": classification.detected_via,
                "is_short_confidence": classification.confidence,
                "classified_at": synced_at,
            })
            table = "youtube_shorts"
        else:
            table = "youtube_videos"

        (
            self._admin
            .schema(_SCHEMA)
            .table(table)
            .upsert(catalog_row, on_conflict="account_id,youtube_video_id")
            .execute()
        )

    def _fetch_app_uploaded_ids(self, *, org_id: UUID) -> set[str]:
        resp = (
            self._admin
            .schema(_SCHEMA)
            .table("upload_jobs")
            .select("youtube_video_id")
            .eq("org_id", str(org_id))
            .eq("status", "published")
            .execute()
        )
        return {
            row["youtube_video_id"]
            for row in (resp.data or [])
            if row.get("youtube_video_id")
        }


def _parse_iso_duration(iso: str) -> int:
    """Parse ISO-8601 duration (PT5M30S) → total seconds. Returns 0 on failure."""
    if not iso:
        return 0
    import re
    m = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        iso.strip().upper(),
    )
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(float(m.group(3) or 0))
    return h * 3600 + mins * 60 + secs


__all__ = ["SnapshotOutcome", "SnapshotService", "SnapshotServiceError"]

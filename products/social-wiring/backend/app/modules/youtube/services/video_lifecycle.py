"""Property-video lifecycle on YouTube: a remake REPLACES the property's previous video of the same kind.

Owner rule (2026-11-28, project julia-videos-prontos-youtube): when a new video of a property (`product_code`) is
published, the property's previous published video(s) of the SAME kind -- standard (`target_format='youtube'`) <->
standard, Shorts <-> Shorts -- are set to **private** on YouTube. Never deleted: private is reversible.

`ProductVideoLifecycle.supersede_previous` is the ONE implementation; Julia's "Vídeos Prontos" intake orchestrates it
and the YouTube page / chat can call the same thing. Every privacy change goes through the module's existing call,
`YouTubeService.update_video_metadata(privacy_status='private')` (the same one the chat command `privacidade` uses),
then the local catalog + `upload_jobs` mirror (`SupabaseCatalogSync.mirror_update`).

Previous = `upload_jobs` rows of the org + product code that are PUBLISHED (`PUBLISHED_STATUSES`), carry a video id,
are of a kind that was just published, are not one of the new jobs / new videos, and are not already private. A caller
may add `extra_video_ids` (e.g. the property's YouTube field pointing at a video imported from Vista or set by hand,
which no upload_jobs row covers): they are treated as standard videos.

Nothing raises per video: a YouTube refusal (not our channel, not found, quota) is returned as `result='recusado'`
with the error CLASS name (never the message: a Google error body can echo request data) and logged at WARNING; a
catalog mirror that failed after a successful privacy change is `mirror_ok=False`, logged at ERROR.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol, Sequence
from uuid import UUID

from app.modules.youtube.services.upload import PUBLISHED_STATUSES

logger = logging.getLogger(__name__)

STANDARD_FORMAT = "youtube"
SHORTS_FORMAT = "shorts"
PRIVATE = "private"

RESULT_PRIVATE = "privado"
RESULT_REFUSED = "recusado"


class PublishedJobsLookup(Protocol):
    """`upload_jobs` rows of one product code of the org (newest first): `youtube_chat_commands.SupabaseJobLookup`."""

    def list_jobs(self, code: str) -> list[dict[str, Any]]: ...


class PrivacyUpdater(Protocol):
    """The slice of `YouTubeService` used here (never a second YouTube privacy call)."""

    def update_video_metadata(self, *, org_id: UUID, video_id: str, privacy_status: Optional[str] = None) -> Any: ...


class CatalogMirror(Protocol):
    def mirror_update(self, video_id: str, patch: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SupersededVideo:
    """One previous video the supersede step tried to set private."""

    youtube_video_id: str
    upload_job_id: Optional[str]
    target_format: str
    result: str  # RESULT_PRIVATE | RESULT_REFUSED
    error: Optional[str] = None  # the exception CLASS name on a refusal
    mirror_ok: bool = True
    source: str = "upload_job"  # upload_job | extra

    @property
    def ok(self) -> bool:
        return self.result == RESULT_PRIVATE


class ProductVideoLifecycle:
    def __init__(self, *, org_id: Any, jobs: PublishedJobsLookup, youtube: PrivacyUpdater,
                 catalog: Optional[CatalogMirror] = None) -> None:
        self._org_id = UUID(str(org_id))
        self._jobs = jobs
        self._youtube = youtube
        self._catalog = catalog

    def previous_of_kinds(self, product_code: str, *, kinds: Iterable[str], exclude_job_ids: Iterable[str] = (),
                          exclude_video_ids: Iterable[str] = (),
                          rows: Optional[Sequence[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        """The published, non-private upload_jobs rows of `product_code` of the given kinds, minus the excluded
        jobs / videos, one per video id (newest first). `rows` = an already-read `list_jobs(product_code)`."""
        kinds_set = set(kinds)
        jobs_out = {str(j) for j in exclude_job_ids}
        videos_out = {str(v) for v in exclude_video_ids}
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in (self._jobs.list_jobs(product_code) or []) if rows is None else rows:
            vid = row.get("youtube_video_id")
            if (not vid or row.get("status") not in PUBLISHED_STATUSES or row.get("target_format") not in kinds_set
                    or str(row.get("id")) in jobs_out or vid in videos_out or vid in seen
                    or row.get("privacy_status") == PRIVATE):
                continue
            seen.add(vid)
            out.append(row)
        return out

    def supersede_previous(self, *, product_code: str, new_jobs: Sequence[dict[str, Any]],
                           extra_video_ids: Iterable[str] = ()) -> list[SupersededVideo]:
        """Set private every previous video of the kinds in `new_jobs` (the just-PUBLISHED jobs: `id`,
        `youtube_video_id`, `target_format`). `extra_video_ids` are standard videos with no upload_jobs row (only
        considered when a new standard video was published). Call it only AFTER the new upload is published: a
        failed new upload must never private the old one."""
        published_new = [j for j in new_jobs if j.get("youtube_video_id")]
        kinds = {j.get("target_format") for j in published_new} & {STANDARD_FORMAT, SHORTS_FORMAT}
        if not kinds:
            return []
        new_videos = {str(j["youtube_video_id"]) for j in published_new}
        rows = list(self._jobs.list_jobs(product_code) or [])
        previous = self.previous_of_kinds(product_code, kinds=kinds, exclude_job_ids=(j.get("id") for j in published_new),
                                          exclude_video_ids=new_videos, rows=rows)
        # an extra already known private (a job row of ours) is not set private again
        already_private = {str(r["youtube_video_id"]) for r in rows
                           if r.get("youtube_video_id") and r.get("privacy_status") == PRIVATE}
        covered = {str(r["youtube_video_id"]) for r in previous} | new_videos | already_private
        results = [self._set_private(str(r["youtube_video_id"]), upload_job_id=str(r["id"]),
                                     target_format=str(r["target_format"]), source="upload_job") for r in previous]
        if STANDARD_FORMAT in kinds:
            for vid in dict.fromkeys(str(v) for v in extra_video_ids if v):
                if vid in covered:
                    continue
                covered.add(vid)
                results.append(self._set_private(vid, upload_job_id=None, target_format=STANDARD_FORMAT, source="extra"))
        return results

    def _set_private(self, video_id: str, *, upload_job_id: Optional[str], target_format: str, source: str) -> SupersededVideo:
        try:
            self._youtube.update_video_metadata(org_id=self._org_id, video_id=video_id, privacy_status=PRIVATE)
        except Exception as exc:  # not our channel / not found / quota: recorded by the caller, never raised
            logger.warning("video lifecycle: could not set %s private (org=%s, %s)", video_id, self._org_id,
                           type(exc).__name__)
            return SupersededVideo(video_id, upload_job_id, target_format, RESULT_REFUSED, error=type(exc).__name__,
                                   source=source)
        mirror_ok = True
        if self._catalog is not None:
            try:
                self._catalog.mirror_update(video_id, {"privacy_status": PRIVATE})
            except Exception as exc:  # YouTube already private; the local catalog lags until the next sync
                logger.error("video lifecycle: %s set private on YouTube but the catalog mirror failed (%s)",
                             video_id, type(exc).__name__)
                mirror_ok = False
        return SupersededVideo(video_id, upload_job_id, target_format, RESULT_PRIVATE, mirror_ok=mirror_ok, source=source)


def build_product_video_lifecycle(org_id: Any) -> ProductVideoLifecycle:
    """Production wiring over the service-role client: the same lookup / YouTube service / catalog mirror the upload
    chat uses."""
    from app.config import settings
    from app.dependencies import get_admin_client
    from app.services.account_credentials import build_youtube_service_for_org
    from app.services.youtube_chat_commands import SupabaseCatalogSync, SupabaseJobLookup

    admin = get_admin_client()
    org = UUID(str(org_id))
    return ProductVideoLifecycle(
        org_id=org, jobs=SupabaseJobLookup(admin, org), youtube=build_youtube_service_for_org(admin, settings),
        catalog=SupabaseCatalogSync(admin, org),
    )


__all__ = [
    "CatalogMirror", "PRIVATE", "ProductVideoLifecycle", "PrivacyUpdater", "PublishedJobsLookup", "RESULT_PRIVATE",
    "RESULT_REFUSED", "SHORTS_FORMAT", "STANDARD_FORMAT", "SupersededVideo", "build_product_video_lifecycle",
]

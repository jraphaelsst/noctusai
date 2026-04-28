"""Audio Retention Service — physical deletion of expired session audio.

compliance-audit-reconciliation Phase 5 (finding 6, 2026-04-22): the
original code set `download_expires_at` but never physically deleted the
audio files — the product copy promised "deleted after 24h" while the files
lived on. This service closes that gap.

**Design:**

1. `find_expired_segments(db)` — list segments where
   `download_expires_at < now()` and `audio_file_url IS NOT NULL` (i.e.
   still referencing a storage object).
2. `expire_audio_file(segment, db)` — delete the storage object, null
   the `audio_file_url`, and set `session_records.audio_deleted_at`.
   Idempotent: already-nulled segments are skipped.
3. `run_retention_sweep(db)` — batch runner. Meant to be called from a
   scheduler (therapy has no scheduler today — follow-up project
   `therapy-scheduler-for-retention` will wire this to a cron-like loop).
   Exposed synchronously via `POST /api/lgpd/run-audio-retention`
   (admin-only) until the scheduler lands.

**LGPD Art. 16**: promised retention + actual retention must match. Without
this service the gap was "product text says deleted at 24h; data sits
indefinitely." — a direct LGPD violation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))

# Bucket name for session audio. The raw-audio feature is not yet live
# (confirmed via Supabase MCP 2026-04-22 Phase 4 — no therapy audio bucket
# exists). When the feature ships, the bucket MUST be PRIVATE to mirror
# the attachment-bucket hardening from Phase 4.
AUDIO_BUCKET = "therapy-session-audio"


def _now_iso() -> str:
    return datetime.now(SP_TZ).isoformat()


def _extract_storage_path(url: str) -> str:
    """Best-effort extraction of the storage object path from an audio URL.

    Supabase URLs follow the pattern
    `https://<project>.supabase.co/storage/v1/object/{sign/public}/<bucket>/<path>`.
    Returns the `<path>` portion, or the URL unchanged if the shape is
    unfamiliar (caller passes whatever is stored — the storage client will
    reject unknown paths cleanly).
    """
    parsed = urlparse(url)
    path = parsed.path or url
    marker = f"/{AUDIO_BUCKET}/"
    idx = path.find(marker)
    if idx >= 0:
        return path[idx + len(marker):]
    # Generic /object/<sign|public>/<bucket>/<path>
    parts = path.split("/object/", 1)
    if len(parts) == 2:
        tail = parts[1].split("/", 2)
        if len(tail) == 3:
            return tail[2]
    return url


def find_expired_segments(db: Any) -> List[Dict]:
    """Return segments whose `download_expires_at` is in the past and
    that still carry an `audio_file_url` (i.e. not already deleted).

    Caller supplies the admin/service-role client — RLS would scope a
    user client to their own sessions."""
    result = (
        db.table("session_audio_segments")
        .select("id, video_room_id, audio_file_url, download_expires_at")
        .lt("download_expires_at", _now_iso())
        .not_.is_("audio_file_url", "null")
        .execute()
    )
    return result.data or []


def expire_audio_file(segment: Dict, db: Any) -> bool:
    """Delete the storage object for one segment + clear `audio_file_url`.

    Returns True iff the deletion + metadata update succeeded. Storage-
    side errors are logged and swallowed (retention sweep continues);
    the DB update only runs if the storage call didn't raise — this
    preserves `audio_file_url` for a retry on the next sweep.
    """
    url = segment.get("audio_file_url")
    if not url:
        return False

    storage_path = _extract_storage_path(url)
    try:
        db.storage.from_(AUDIO_BUCKET).remove([storage_path])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Audio storage delete failed for segment %s (path=%s): %s",
            segment.get("id"), storage_path, exc,
        )
        return False

    try:
        db.table("session_audio_segments").update({
            "audio_file_url": None,
        }).eq("id", segment["id"]).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Audio metadata update failed after storage delete (segment=%s): %s",
            segment.get("id"), exc,
        )
        return False

    # Mark the parent session_record as audio-deleted (transitively via
    # video_rooms → appointment → session_records). Best-effort: if the
    # chain can't be resolved, we still succeeded on the bytes — log and
    # continue.
    try:
        vr = first_or_none(
            db.table("video_rooms")
            .select("appointment_id")
            .eq("id", segment["video_room_id"])
            .execute()
        )
        if vr and vr.get("appointment_id"):
            db.table("session_records").update({
                "audio_deleted_at": _now_iso(),
            }).eq("appointment_id", vr["appointment_id"]).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "audio_deleted_at propagation failed for segment %s: %s",
            segment.get("id"), exc,
        )

    return True


def run_retention_sweep(db: Any) -> Dict[str, int]:
    """Find + expire every segment past its retention window.

    Returns `{"found": N, "deleted": M}` — M ≤ N because storage-side
    failures count as "found but not deleted" and retry on the next sweep.
    """
    expired = find_expired_segments(db)
    deleted = 0
    for segment in expired:
        if expire_audio_file(segment, db):
            deleted += 1
    logger.info("Audio retention sweep: found=%d deleted=%d", len(expired), deleted)
    return {"found": len(expired), "deleted": deleted}

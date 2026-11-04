"""Pure mapping of Apify `instagram-scraper` dataset items -> our value objects."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from .types import (
    HANDLE_PATTERN,
    ApifyRunFailed,
    InstagramPublicPost,
    InstagramPublicProfile,
    MediaType,
)

_HANDLE_RE = re.compile(HANDLE_PATTERN)
_TYPE_MAP: dict[str, MediaType] = {"image": "IMAGE", "video": "VIDEO", "sidecar": "CAROUSEL_ALBUM"}


def normalize_handle(handle: str) -> str:
    """Validate with the same regex as `POST /biblioteca/perfis`; return it without '@'."""
    if not isinstance(handle, str) or not _HANDLE_RE.match(handle.strip()):
        raise ValueError("invalid instagram handle")
    return handle.strip().lstrip("@")


def _int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return None if n < 0 else n  # Apify uses -1 for "hidden"


def _float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _ts(v: Any) -> datetime:
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str) and v:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError("missing timestamp")


def map_profile(item: dict, fallback_username: str) -> InstagramPublicProfile:
    return InstagramPublicProfile(
        username=str(item.get("username") or fallback_username),
        full_name=item.get("fullName"),
        biography=item.get("biography"),
        followers_count=_int(item.get("followersCount")),
        follows_count=_int(item.get("followsCount")),
        posts_count=_int(item.get("postsCount")),
        profile_pic_url=item.get("profilePicUrlHD") or item.get("profilePicUrl"),
        is_private=bool(item.get("private") or item.get("isPrivate")),
        is_business=item.get("isBusinessAccount") if isinstance(item.get("isBusinessAccount"), bool) else None,
        verified=item.get("verified") if isinstance(item.get("verified"), bool) else None,
        external_id=str(item["id"]) if item.get("id") not in (None, "") else None,
    )


def map_post(item: dict, fallback_owner: str) -> InstagramPublicPost:
    try:
        raw_type = str(item.get("type") or "").lower()
        media_type: MediaType = _TYPE_MAP.get(raw_type, "VIDEO" if item.get("videoUrl") else "IMAGE")
        shortcode = str(item["shortCode"])
        views = _int(item.get("videoPlayCount"))
        if views is None:
            views = _int(item.get("videoViewCount"))
        return InstagramPublicPost(
            id=str(item["id"]),
            shortcode=shortcode,
            permalink=str(item.get("url") or f"https://www.instagram.com/p/{shortcode}/"),
            media_type=media_type,
            product_type=item.get("productType"),
            caption=item.get("caption"),
            timestamp=_ts(item.get("timestamp")),
            likes=_int(item.get("likesCount")),
            comments=_int(item.get("commentsCount")),
            views=views,
            duration_s=_float(item.get("videoDuration")),
            display_url=item.get("displayUrl"),
            video_url=item.get("videoUrl"),
            owner_username=str(item.get("ownerUsername") or fallback_owner),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ApifyRunFailed(f"malformed post item ({type(exc).__name__})") from None

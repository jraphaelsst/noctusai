"""Redis-backed cache for Drive folder downloads.

Why this exists: the multi-video disambiguation flow (F4 +
``_handle_video_choice``) downloads a Drive folder upfront so we can
list horizontal candidates. Without a cache:

  - Retrying a failed upload re-downloads the folder from Drive.
  - The dashboard's "🔄 Tentar de novo" button always pays the network
    cost again.
  - Each video in the "upload all candidates" flow would re-download.

With a cache, each ``(drive_url → local files)`` pairing is remembered
for ``settings.download_cache_ttl_hours`` (default 24). On retry/re-run,
the cache short-circuits the Drive call entirely as long as the local
files still exist on disk.

Cache shape (Redis hash entries, one per ``drive_url``):

    key:    ``download:cache:{sha1(drive_url)}``
    value:  JSON
        {
            "drive_url": "...",
            "downloaded_at": <epoch>,
            "expires_at": <epoch>,
            "candidates": [
                {"local_path": "/tmp/...", "file_name": "...",
                 "file_size_bytes": 12345, "format": "youtube",
                 "duration_seconds": 273.4},
                ...
            ],
        }

The Redis TTL is set to match ``expires_at`` so stale entries also
disappear when Redis evicts them. Local files orphaned by manual rm or
docker volume reset are detected on cache hit (the consumer verifies
``Path.exists()`` for each entry).

Eviction triggers:

  - TTL: Redis drops the key automatically; the next miss re-downloads.
  - File missing: consumer evicts via ``invalidate(drive_url)``.
  - Manual: ``cleanup_orphans()`` walks all cache entries and drops any
    where every local_path is gone (e.g. /tmp wiped during deploy).

This module is product-private. Lift to seed-lib if a second product
ever needs the same shape (recurrence rule N=2 → triage).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


_CACHE_KEY_PREFIX = "download:cache:"


@dataclass(frozen=True)
class CachedCandidate:
    """One downloaded video that's part of a cached Drive folder.

    Mirrors ``gdrive_service.VideoCandidate`` for cross-module
    compatibility but stores ``local_path`` as ``str`` so the whole
    cache entry is trivially JSON-serializable.
    """

    local_path: str
    file_name: str
    file_size_bytes: int
    format: str
    duration_seconds: float | None = None


@dataclass(frozen=True)
class CacheEntry:
    """A complete cached Drive folder."""

    drive_url: str
    downloaded_at: float
    expires_at: float
    candidates: list[CachedCandidate]


class _RedisLike(Protocol):
    """The Redis surface we need. ``redis.Redis`` satisfies this;
    tests pass an in-memory fake."""

    def get(self, name: str) -> Any: ...

    def set(self, name: str, value: str, ex: int | None = ...) -> bool | None: ...

    def delete(self, *names: str) -> int: ...

    def keys(self, pattern: str) -> list[Any]: ...


def _key_for(drive_url: str) -> str:
    """Hash the URL so the Redis key is fixed-length + safe regardless
    of weird query-string characters."""
    digest = hashlib.sha1(drive_url.encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest}"


class DownloadCache:
    """Cache facade. Wraps Redis-side reads/writes + path verification.

    All methods are sync (the underlying redis-py is sync); the consumer
    calls these from inside ``asyncio.to_thread`` blocks where
    appropriate.
    """

    def __init__(self, redis_client: _RedisLike, ttl_hours: int = 24):
        self._redis = redis_client
        self._ttl_seconds = max(1, ttl_hours) * 3600

    # ─── Public API ─────────────────────────────────────────────────────

    def get(self, drive_url: str) -> CacheEntry | None:
        """Return the cached entry for ``drive_url`` if all local files
        still exist on disk. Returns ``None`` on cache miss, expired
        entry, or partial-file-loss (in which case the entry is also
        evicted so the next call re-downloads cleanly).
        """
        raw = self._redis.get(_key_for(drive_url))
        if not raw:
            return None
        try:
            payload = json.loads(raw if isinstance(raw, (str, bytes, bytearray)) else str(raw))
        except Exception:
            # Corrupt entry — evict so the next call writes fresh.
            self._redis.delete(_key_for(drive_url))
            return None

        entry = self._entry_from_payload(payload)
        if entry is None:
            self._redis.delete(_key_for(drive_url))
            return None

        # Verify every local file is still on disk. Partial loss → evict
        # entirely; we want the next attempt to re-download everything,
        # not mix-and-match stale + fresh files (which could confuse the
        # candidate list).
        for cand in entry.candidates:
            if not Path(cand.local_path).exists():
                logger.info(
                    "download_cache: evicting %s (missing local file: %s)",
                    drive_url,
                    cand.local_path,
                )
                self._redis.delete(_key_for(drive_url))
                return None

        # Expiry: belt-and-suspenders alongside Redis TTL. Returning None
        # here triggers a fresh download even if Redis TTL hasn't fired
        # (clock drift, dev fast-forward).
        if time.time() > entry.expires_at:
            self._redis.delete(_key_for(drive_url))
            return None

        return entry

    def put(
        self,
        drive_url: str,
        candidates: list[CachedCandidate],
    ) -> CacheEntry:
        """Write a fresh entry. Overwrites any previous entry for the
        same ``drive_url`` (the consumer wins last-write-wins)."""
        now = time.time()
        entry = CacheEntry(
            drive_url=drive_url,
            downloaded_at=now,
            expires_at=now + self._ttl_seconds,
            candidates=list(candidates),
        )
        payload = json.dumps(self._payload_from_entry(entry))
        self._redis.set(_key_for(drive_url), payload, ex=self._ttl_seconds)
        return entry

    def invalidate(self, drive_url: str) -> None:
        """Drop the entry. Safe to call when absent. Use when the
        consumer detects a local file was lost mid-flight."""
        self._redis.delete(_key_for(drive_url))

    def cleanup_orphans(self) -> int:
        """Walk all cache entries; drop any where files are gone.

        Returns the count of evictions. Useful on app startup as a
        warm-up sweep — keeps the Redis hash from accumulating dead
        entries when /tmp was wiped (deploy, container restart) but
        Redis persisted.
        """
        try:
            keys = self._redis.keys(f"{_CACHE_KEY_PREFIX}*")
        except Exception:
            logger.exception("download_cache: keys() scan failed")
            return 0

        evicted = 0
        for raw_key in keys or []:
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            try:
                raw_value = self._redis.get(key)
                if not raw_value:
                    continue
                payload = json.loads(
                    raw_value if isinstance(raw_value, (str, bytes, bytearray)) else str(raw_value)
                )
                entry = self._entry_from_payload(payload)
                if entry is None:
                    self._redis.delete(key)
                    evicted += 1
                    continue
                if any(not Path(c.local_path).exists() for c in entry.candidates):
                    self._redis.delete(key)
                    evicted += 1
            except Exception:
                logger.exception("download_cache: cleanup of %s crashed", key)
        if evicted:
            logger.info("download_cache: cleanup_orphans evicted %d stale entries", evicted)
        return evicted

    # ─── Internals ──────────────────────────────────────────────────────

    @staticmethod
    def _payload_from_entry(entry: CacheEntry) -> dict[str, Any]:
        return {
            "drive_url": entry.drive_url,
            "downloaded_at": entry.downloaded_at,
            "expires_at": entry.expires_at,
            "candidates": [
                {
                    "local_path": c.local_path,
                    "file_name": c.file_name,
                    "file_size_bytes": c.file_size_bytes,
                    "format": c.format,
                    "duration_seconds": c.duration_seconds,
                }
                for c in entry.candidates
            ],
        }

    @staticmethod
    def _entry_from_payload(payload: dict[str, Any]) -> CacheEntry | None:
        try:
            return CacheEntry(
                drive_url=payload["drive_url"],
                downloaded_at=float(payload["downloaded_at"]),
                expires_at=float(payload["expires_at"]),
                candidates=[
                    CachedCandidate(
                        local_path=c["local_path"],
                        file_name=c["file_name"],
                        file_size_bytes=int(c["file_size_bytes"]),
                        format=c["format"],
                        duration_seconds=c.get("duration_seconds"),
                    )
                    for c in payload.get("candidates", [])
                ],
            )
        except (KeyError, TypeError, ValueError):
            return None


__all__ = ["CachedCandidate", "CacheEntry", "DownloadCache"]

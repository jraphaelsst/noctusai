"""Unit tests for the Drive download cache.

In-memory fake Redis driver — covers TTL expiry, file-existence
verification, orphan sweep, and corrupt-entry handling.
"""
from __future__ import annotations

import time

import pytest

from app.services.download_cache import (
    CachedCandidate,
    DownloadCache,
)


class FakeRedis:
    """Tiny redis subset the cache uses, with TTL emulation."""

    def __init__(self):
        self._values: dict[str, tuple[str, float | None]] = {}

    def get(self, name: str):
        entry = self._values.get(name)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() > expires_at:
            del self._values[name]
            return None
        return value

    def set(self, name: str, value: str, ex: int | None = None) -> bool:
        expires_at = time.time() + ex if ex else None
        self._values[name] = (value, expires_at)
        return True

    def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._values:
                del self._values[name]
                count += 1
        return count

    def keys(self, pattern: str):
        if not pattern.endswith("*"):
            return [name for name in self._values if name == pattern]
        prefix = pattern[:-1]
        return [name for name in self._values if name.startswith(prefix)]


@pytest.fixture
def cache() -> DownloadCache:
    return DownloadCache(FakeRedis(), ttl_hours=1)


@pytest.fixture
def candidates(tmp_path):
    """Three on-disk candidates rooted at tmp_path so file-existence
    checks land on real files."""
    paths = []
    for i in range(3):
        p = tmp_path / f"vid{i}.mp4"
        p.write_bytes(b"fake-video-bytes")
        paths.append(p)
    return [
        CachedCandidate(
            local_path=str(p),
            file_name=p.name,
            file_size_bytes=p.stat().st_size,
            format="youtube",
            duration_seconds=120.0 + i,
        )
        for i, p in enumerate(paths)
    ]


def test_get_returns_none_on_miss(cache: DownloadCache):
    assert cache.get("https://drive.google.com/drive/folders/abc") is None


def test_put_then_get_roundtrips(cache: DownloadCache, candidates):
    url = "https://drive.google.com/drive/folders/abc"
    cache.put(url, candidates)
    entry = cache.get(url)
    assert entry is not None
    assert len(entry.candidates) == 3
    assert entry.candidates[0].file_name == "vid0.mp4"
    assert entry.candidates[1].duration_seconds == 121.0


def test_get_evicts_when_file_missing(cache: DownloadCache, candidates, tmp_path):
    """If a cached candidate's local file vanished (cleanup, manual rm),
    the cache evicts the whole entry — partial reuse would mix stale +
    fresh files."""
    url = "https://drive.google.com/drive/folders/abc"
    cache.put(url, candidates)
    # Remove one file behind the cache's back
    (tmp_path / "vid1.mp4").unlink()
    assert cache.get(url) is None  # evicted because vid1 is gone
    # And the cache entry IS dropped (next get won't re-evict)
    cache.put(url, candidates)  # would normally pass — confirms eviction
    assert cache.get(url) is None  # second get still misses, vid1 still gone


def test_invalidate_drops_entry(cache: DownloadCache, candidates):
    url = "https://drive.google.com/drive/folders/abc"
    cache.put(url, candidates)
    assert cache.get(url) is not None
    cache.invalidate(url)
    assert cache.get(url) is None


def test_invalidate_is_safe_when_absent(cache: DownloadCache):
    cache.invalidate("never-existed-url")  # would raise if not safe


def test_cleanup_orphans_evicts_stale_files(
    cache: DownloadCache, candidates, tmp_path
):
    url_a = "https://drive.google.com/drive/folders/abc"
    url_b = "https://drive.google.com/drive/folders/def"
    cache.put(url_a, candidates)
    cache.put(url_b, [candidates[0]])  # only one file

    # Wipe everything under tmp_path
    for p in tmp_path.iterdir():
        if p.is_file():
            p.unlink()

    evicted = cache.cleanup_orphans()
    assert evicted == 2
    assert cache.get(url_a) is None
    assert cache.get(url_b) is None


def test_corrupt_payload_is_evicted_on_get(cache: DownloadCache):
    """A non-JSON value at the cache key (could happen on a bad write
    in prod) must NOT crash — the entry is evicted + None returned."""
    url = "https://drive.google.com/drive/folders/abc"
    cache._redis.set(  # type: ignore[attr-defined]
        "download:cache:" + __import__("hashlib").sha1(url.encode()).hexdigest(),
        "this-is-not-json",
    )
    assert cache.get(url) is None  # evicted, no crash

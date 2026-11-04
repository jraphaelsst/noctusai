"""Deterministic fake Instagram scraper (dev/test) driven by JSON fixtures."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .mapping import map_post, map_profile, normalize_handle
from .types import (
    ApifyProfileNotFound,
    ApifyRunCost,
    InstagramProfileScrape,
    MAX_POSTS_HARD_CAP,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "apify"


def _builtin_profiles() -> dict[str, dict]:
    """Bundled minimal fixtures so the Fake works with no test tree on disk."""
    return {
        "perfil.publico": {
            "username": "perfil.publico", "fullName": "Perfil Público", "followersCount": 1200,
            "private": False, "id": "111",
            "latestPosts": [{
                "id": "p1", "shortCode": "AAA", "url": "https://www.instagram.com/p/AAA/",
                "type": "Video", "productType": "clips", "caption": "gancho forte",
                "timestamp": "2026-10-01T12:00:00.000Z", "likesCount": 10, "commentsCount": 2,
                "videoPlayCount": 500, "videoDuration": 20.5, "videoUrl": "https://scontent.cdninstagram.com/v.mp4",
                "ownerUsername": "perfil.publico",
            }],
        },
        "perfil.privado": {"username": "perfil.privado", "private": True, "latestPosts": []},
    }


class FakeInstagramScraper:
    def __init__(self, profiles: Optional[dict[str, dict]] = None) -> None:
        self._profiles = profiles if profiles is not None else _builtin_profiles()
        self.calls: list[tuple[str, int]] = []

    @classmethod
    def from_fixtures(cls, directory: Path = FIXTURES_DIR) -> "FakeInstagramScraper":
        profiles = {p.stem: json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))}
        return cls(profiles)

    def scrape_profile(
        self, handle: str, *, max_posts: int, newer_than: Optional[date] = None, timeout_s: float = 240
    ) -> InstagramProfileScrape:
        user = normalize_handle(handle)
        self.calls.append((user, max_posts))
        item = self._profiles.get(user.lower())
        if item is None:
            raise ApifyProfileNotFound("profile not found", reason="nao_encontrado")
        if item.get("private"):
            raise ApifyProfileNotFound("profile is private", reason="privado")
        cap = max(1, min(max_posts, MAX_POSTS_HARD_CAP))
        posts = [map_post(p, user) for p in item.get("latestPosts", [])]
        if newer_than is not None:
            posts = [p for p in posts if p.timestamp.date() >= newer_than]
        posts = posts[:cap]
        return InstagramProfileScrape(
            profile=map_profile(item, user),
            posts=posts,
            cost=ApifyRunCost(results=len(posts), usd=Decimal("0"), run_id="fake-run"),
        )

"""Apify integration — Instagram public-profile scraper (Fake + Real + factory).

Owner decision 2026-11-04 (transitional, until Meta verification): the Biblioteca de
virais reads third-party public profiles through `apify/instagram-scraper`.
"""
from .actor_runner import (
    ActorRunner, ActorRunResult, ActorRunUsage, ApifyActorTimeout, FakeActorRunner, RealActorRunner,
)
from .factory import get_instagram_scraper, make_actor_runner
from .fake_adapter import FakeInstagramScraper
from .real_adapter import RealInstagramScraper
from .types import (
    ApifyError,
    ApifyNotConfigured,
    ApifyProfileNotFound,
    ApifyRateLimited,
    ApifyRunCost,
    ApifyRunFailed,
    InstagramProfileScrape,
    InstagramPublicPost,
    InstagramPublicProfile,
    InstagramScraper,
)

__all__ = [
    "ApifyError", "ApifyNotConfigured", "ApifyProfileNotFound", "ApifyRateLimited",
    "ApifyRunCost", "ApifyRunFailed", "FakeInstagramScraper", "InstagramProfileScrape",
    "InstagramPublicPost", "InstagramPublicProfile", "InstagramScraper",
    "RealInstagramScraper", "get_instagram_scraper",
    "ActorRunner", "ActorRunResult", "ActorRunUsage", "ApifyActorTimeout", "FakeActorRunner",
    "RealActorRunner", "make_actor_runner",
]

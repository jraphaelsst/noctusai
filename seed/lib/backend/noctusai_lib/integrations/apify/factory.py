"""Factory for the Instagram scraper port — never a silent fake in production."""
from __future__ import annotations

from typing import Optional

import httpx

from .actor_runner import ActorRunner, FakeActorRunner, RealActorRunner
from .fake_adapter import FakeInstagramScraper
from .real_adapter import RealInstagramScraper
from .types import ApifyNotConfigured, InstagramScraper
from ..fake_or_refuse import resolve_fake_or_refuse


def _refuse() -> InstagramScraper:
    raise ApifyNotConfigured("apify token not configured")


def get_instagram_scraper(
    *,
    token: Optional[str],
    real: Optional[bool] = None,
    allow_fake: bool = False,
    transport: Optional[httpx.BaseTransport] = None,
) -> InstagramScraper:
    """`real=False` -> Fake. Otherwise fake-or-refuse: a token -> Real; no token ->
    `ApifyNotConfigured` unless `allow_fake=True` (explicit test/dev opt-in)."""
    if real is False:
        return FakeInstagramScraper()
    return resolve_fake_or_refuse(
        configured=bool(token),
        build_real=lambda: RealInstagramScraper(token=token or "", transport=transport),
        build_fake=FakeInstagramScraper,
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )


def _refuse_runner() -> ActorRunner:
    raise ApifyNotConfigured("apify token not configured")


def make_actor_runner(
    *,
    token: Optional[str],
    real: Optional[bool] = None,
    allow_fake: bool = False,
    transport: Optional[httpx.BaseTransport] = None,
) -> ActorRunner:
    """Generic actor runner; same fake-or-refuse contract as `get_instagram_scraper`."""
    if real is False:
        return FakeActorRunner()
    return resolve_fake_or_refuse(
        configured=bool(token),
        build_real=lambda: RealActorRunner(token=token or "", transport=transport),
        build_fake=FakeActorRunner,
        allow_fake=allow_fake,
        unconfigured=_refuse_runner,
    )

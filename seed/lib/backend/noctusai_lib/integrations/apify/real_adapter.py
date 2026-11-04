"""Real Apify adapter: `apify/instagram-scraper` via run-sync-get-dataset-items.

The token travels ONLY in the Authorization header — never in the URL, a log
line, or an exception message.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from .mapping import map_post, map_profile, normalize_handle
from .types import (
    MAX_POSTS_HARD_CAP,
    ApifyNotConfigured,
    ApifyProfileNotFound,
    ApifyRateLimited,
    ApifyRunCost,
    ApifyRunFailed,
    InstagramProfileScrape,
)

logger = logging.getLogger(__name__)

ACTOR_URL = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"


class RealInstagramScraper:
    def __init__(self, *, token: str, transport: Optional[httpx.BaseTransport] = None) -> None:
        if not token:
            raise ApifyNotConfigured("apify token not configured")
        self._token = token
        self._transport = transport

    # -- http -------------------------------------------------------------
    def _run(self, payload: dict, timeout_s: float) -> tuple[list[dict], ApifyRunCost]:
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=timeout_s, transport=self._transport) as client:
                resp = client.post(
                    ACTOR_URL, params={"timeout": int(timeout_s)}, json=payload, headers=headers
                )
        except httpx.TimeoutException:
            raise ApifyRunFailed("apify run timed out") from None
        except httpx.HTTPError as exc:
            raise ApifyRunFailed(f"apify transport error ({type(exc).__name__})") from None
        if resp.status_code == 429:
            retry = resp.headers.get("retry-after")
            try:
                retry_s = float(retry) if retry else None
            except ValueError:
                retry_s = None
            raise ApifyRateLimited("apify rate limited", retry_after_s=retry_s)
        if resp.status_code not in (200, 201):
            raise ApifyRunFailed(f"apify returned HTTP {resp.status_code}")
        try:
            items = resp.json()
        except ValueError:
            raise ApifyRunFailed("apify returned a non-JSON body") from None
        if not isinstance(items, list):
            raise ApifyRunFailed("apify returned an unexpected body shape")
        usd: Optional[Decimal] = None
        raw_usd = resp.headers.get("x-apify-usage-total-usd")
        if raw_usd:
            try:
                usd = Decimal(raw_usd)
            except InvalidOperation:
                usd = None
        cost = ApifyRunCost(results=len(items), usd=usd, run_id=resp.headers.get("x-apify-run-id"))
        return [i for i in items if isinstance(i, dict)], cost

    # -- port -------------------------------------------------------------
    def scrape_profile(
        self, handle: str, *, max_posts: int, newer_than: Optional[date] = None, timeout_s: float = 240
    ) -> InstagramProfileScrape:
        user = normalize_handle(handle)
        cap = max(1, min(int(max_posts), MAX_POSTS_HARD_CAP))
        base = {
            "directUrls": [f"https://www.instagram.com/{user}/"],
            "resultsLimit": cap,
            "addParentData": False,
        }
        if newer_than is not None:
            base["onlyPostsNewerThan"] = newer_than.isoformat()

        items, cost = self._run({**base, "resultsType": "details"}, timeout_s)
        detail = next((i for i in items if not i.get("error") and (i.get("username") or i.get("latestPosts") is not None)), None)
        if detail is None:
            raise ApifyProfileNotFound("profile not found", reason="nao_encontrado")
        profile = map_profile(detail, user)
        if profile.is_private:
            raise ApifyProfileNotFound("profile is private", reason="privado")

        posts: dict[str, object] = {}
        for raw in detail.get("latestPosts") or []:
            if isinstance(raw, dict):
                p = map_post(raw, user)
                posts.setdefault(p.id, p)

        results, usd, run_ids = cost.results, cost.usd, cost.run_id
        if len(posts) < cap:
            more, cost2 = self._run({**base, "resultsType": "posts"}, timeout_s)
            for raw in more:
                if raw.get("error") or "shortCode" not in raw:
                    continue
                p = map_post(raw, user)
                posts.setdefault(p.id, p)
            results += cost2.results
            if usd is not None and cost2.usd is not None:
                usd += cost2.usd
            elif cost2.usd is not None:
                usd = cost2.usd
            run_ids = cost2.run_id or run_ids

        ordered = sorted(posts.values(), key=lambda p: p.timestamp, reverse=True)[:cap]
        logger.info("apify scrape ok: results=%s posts=%s", results, len(ordered))
        return InstagramProfileScrape(
            profile=profile, posts=list(ordered), cost=ApifyRunCost(results=results, usd=usd, run_id=run_ids)
        )

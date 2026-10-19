"""Lais wave 13 -- the Google Business Profile reviews seam (lais-build-contract 15).

`ReviewsProvider` Protocol + `FakeReviewsProvider` + `RealGbpReviewsProvider` + `make_reviews_provider`.

The seed ships NO Google Business Profile client and NO OAuth token store for the
`https://www.googleapis.com/auth/business.manage` scope (the seed Google scopes are base + Calendar + Drive +
YouTube). Until the owner connects it, the factory returns `NaoConfiguradoReviews`, whose `listar` raises
`ReviewsNaoConfigurado` -- the Avaliacoes page then shows "conecte o Google Business Profile" and the KPIs
simply read from the (empty) cache. The Real provider is complete against the GBP v4 reviews API: it only needs
an `access_token_resolver(org_id) -> str | None` (the missing piece, see the NOC-REMEDIATE marker below).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

logger = logging.getLogger(__name__)

GBP_REVIEWS_URL = "https://mybusiness.googleapis.com/v4/{location}/reviews"
_STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
PAGE_SIZE = 50
MAX_PAGES = 10


class ReviewsNaoConfigurado(Exception, IntegrationNotConfigured):
    """No Google Business Profile credentials / location for this org (not an error to log at ERROR)."""


class ReviewsErro(Exception):
    """The GBP API answered with an error or an unreadable body."""


@dataclass(frozen=True)
class Review:
    external_id: str
    autor: Optional[str]
    nota: int
    texto: Optional[str]
    publicado_at: Optional[datetime]
    link: Optional[str] = None


@runtime_checkable
class ReviewsProvider(Protocol):
    async def listar(self, location_id: str) -> Sequence[Review]: ...


class FakeReviewsProvider:
    """In-memory provider for tests/dev: `listar` returns what the test seeded."""

    def __init__(self, reviews: Optional[Sequence[Review]] = None, *, erro: Optional[Exception] = None):
        self.reviews = list(reviews or [])
        self.erro = erro
        self.chamadas: list[str] = []

    async def listar(self, location_id: str) -> Sequence[Review]:
        self.chamadas.append(location_id)
        if self.erro is not None:
            raise self.erro
        return list(self.reviews)


class NaoConfiguradoReviews:
    """What the factory returns while Google Business Profile is not connected."""

    async def listar(self, location_id: str) -> Sequence[Review]:
        raise ReviewsNaoConfigurado("Conecte o Google Business Profile para listar as avaliações.")


def _parse_ts(valor: Any) -> Optional[datetime]:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def review_de_api(item: dict[str, Any], location_id: str) -> Optional[Review]:
    """One GBP v4 review -> `Review` (None when it has no id / a usable star rating)."""
    rid = item.get("reviewId") or str(item.get("name") or "").rsplit("/", 1)[-1]
    nota = _STARS.get(str(item.get("starRating") or "").upper())
    if not rid or nota is None:
        return None
    autor = (item.get("reviewer") or {}).get("displayName")
    return Review(
        external_id=str(rid), autor=autor, nota=nota, texto=item.get("comment"),
        publicado_at=_parse_ts(item.get("createTime")), link=item.get("reviewUrl"),
    )


class RealGbpReviewsProvider:
    """Google Business Profile v4 `accounts/*/locations/*/reviews` over httpx (already a seed dependency).

    `access_token_resolver(org_id)` must return an OAuth access token carrying the `business.manage` scope."""

    def __init__(self, *, org_id: str, access_token_resolver: Callable[[str], Optional[str]], http_get: Optional[Callable[..., Any]] = None):
        self._org_id = org_id
        self._token = access_token_resolver
        self._http_get = http_get

    def _get(self, url: str, token: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        get = self._http_get or httpx.get
        resp = get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=20.0)
        if resp.status_code >= 400:
            raise ReviewsErro(f"GBP reviews HTTP {resp.status_code}")
        body = resp.json()
        if not isinstance(body, dict):
            raise ReviewsErro("GBP reviews: corpo inesperado")
        return body

    def _listar_sync(self, location_id: str) -> list[Review]:
        token = self._token(self._org_id)
        if not token:
            raise ReviewsNaoConfigurado("Conecte o Google Business Profile para listar as avaliações.")
        url = GBP_REVIEWS_URL.format(location=location_id.strip("/"))
        out: list[Review] = []
        page_token: Optional[str] = None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"pageSize": PAGE_SIZE, "orderBy": "updateTime desc"}
            if page_token:
                params["pageToken"] = page_token
            body = self._get(url, token, params)
            for item in body.get("reviews") or []:
                rev = review_de_api(item, location_id)
                if rev is not None:
                    out.append(rev)
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        return out

    async def listar(self, location_id: str) -> Sequence[Review]:
        return await asyncio.to_thread(self._listar_sync, location_id)


def make_reviews_provider(
    org_id: str, *, access_token_resolver: Optional[Callable[[str], Optional[str]]] = None, use_fake: bool = False,
) -> ReviewsProvider:
    """Fake when asked; Real when a token resolver exists; otherwise the explicit not-configured provider.

    NOC-REMEDIATE[lais-gbp-real]: no seed/product token store holds a Google OAuth token with the
    `business.manage` scope, so production passes no `access_token_resolver` and gets `NaoConfiguradoReviews`.
    Missing piece: a per-org Google OAuth connection granting `business.manage` (consent + token store), then
    `make_reviews_provider(org_id, access_token_resolver=<that store's access-token getter>)` — the Real is done — 2026-10-15
    """
    if use_fake:
        return FakeReviewsProvider()
    if access_token_resolver is None:
        return NaoConfiguradoReviews()
    return RealGbpReviewsProvider(org_id=str(org_id), access_token_resolver=access_token_resolver)


__all__ = [
    "FakeReviewsProvider", "GBP_REVIEWS_URL", "NaoConfiguradoReviews", "RealGbpReviewsProvider", "Review",
    "ReviewsErro", "ReviewsNaoConfigurado", "ReviewsProvider", "make_reviews_provider", "review_de_api",
]

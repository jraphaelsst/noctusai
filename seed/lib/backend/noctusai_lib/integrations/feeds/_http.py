"""Shared outbound seam for every feed source: one limiter bucket per source, one retry layer,
a generic User-Agent, body cap, and URL canonicalisation. Nothing calls out except through `FeedHttp.get`.
"""
from __future__ import annotations

import ipaddress
import time
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from noctusai_lib.integrations import rate_limit

from .types import FeedFetchError, FeedRateLimited

USER_AGENT = "noctusai-feed-collector/1.0 (+https://noctusai.com)"
MAX_BODY_BYTES = 5 * 1024 * 1024
_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid", "yclid", "_hsenc", "_hsmi"}


def canonicalize_url(url: str) -> str:
    """Dedup key form: lowercase scheme/host, drop fragment + tracking params, sort query, trim trailing slash."""
    parts = urlsplit(url.strip())
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in _TRACKING)
    path = parts.path.rstrip("/") or ("" if parts.netloc else parts.path)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def assert_public_http_url(url: str) -> str:
    """Only http(s) to a non-loopback/private host. Feed URLs are operator-entered in a UI, so a
    literal private/loopback target is refused (SSRF); DNS-based rebinding is the network egress layer's job."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise FeedFetchError("feed url must be http(s) with a host")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FeedFetchError("feed url host is not public")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not ip.is_global:
        raise FeedFetchError("feed url host is not public")
    return url


class FeedHttp:
    def __init__(self, *, bucket: str, rate_per_sec: float, burst: float,
                 transport: Optional[httpx.BaseTransport] = None, timeout_s: float = 20,
                 extra_headers: Optional[Mapping[str, str]] = None) -> None:
        self._bucket = bucket
        self._transport = transport
        self._timeout = timeout_s
        self._headers = {"User-Agent": USER_AGENT, **(extra_headers or {})}
        rate_limit.configure_bucket(bucket, rate_per_sec=rate_per_sec, burst=burst)

    @staticmethod
    def _retry_hint(resp: httpx.Response) -> Optional[float]:
        hint = rate_limit.parse_retry_after(resp.headers.get("retry-after"))
        if hint is None and resp.headers.get("x-ratelimit-remaining") == "0":
            reset = resp.headers.get("x-ratelimit-reset")
            try:
                hint = max(0.0, float(reset) - time.time()) if reset else None
            except ValueError:
                hint = None
        return hint

    def get(self, url: str, *, params: Optional[Mapping[str, Any]] = None,
            headers: Optional[Mapping[str, str]] = None, allow_304: bool = False) -> httpx.Response:
        def _once() -> httpx.Response:
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport,
                                  follow_redirects=True, max_redirects=3) as client:
                    resp = client.get(url, params=params, headers={**self._headers, **(headers or {})})
            except httpx.TimeoutException:
                raise FeedFetchError("feed request timed out") from None
            except httpx.HTTPError as exc:
                raise FeedFetchError(f"feed transport error ({type(exc).__name__})") from None
            throttled = resp.status_code == 429 or (
                resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0")
            if throttled:
                raise FeedRateLimited(retry_after_s=self._retry_hint(resp))
            if resp.status_code == 304 and allow_304:
                return resp
            if resp.status_code != 200:
                raise FeedFetchError(f"feed source returned HTTP {resp.status_code}")
            if len(resp.content) > MAX_BODY_BYTES:
                raise FeedFetchError("feed body exceeds size cap")
            return resp

        return rate_limit.paced_call(
            _once, bucket=self._bucket,
            is_retryable=lambda e: isinstance(e, FeedRateLimited),
            retry_after=lambda e: getattr(e, "retry_after_s", None),
        )

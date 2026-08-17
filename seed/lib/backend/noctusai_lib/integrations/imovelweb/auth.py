"""OAuth2 client-credentials for OpenNavent.

Deliberately NOT in `noctusai_lib.security.oauth`: that module is the
authorization-code / user-consent dance — `OAuthProvider`, a FastAPI
router, a scope resolver, a per-org token store. This is machine-to-machine
with no user, no redirect and no per-org consent, and putting it there
would drag a router into a two-parameter token fetch.

Kept vendor-local at N=1. **Lift trigger:** the second client-credentials
vendor lifts this to
`noctusai_lib/integrations/oauth_client_credentials.py`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from .errors import ImovelWebConfigError, ImovelWebUpstreamError, redact_secrets

logger = logging.getLogger(__name__)

#: Refresh this long before expiry. A token that expires mid-flight costs
#: a retry; refreshing a minute early costs nothing.
REFRESH_SKEW_SECONDS = 60

LOGIN_PATH = "/v1/application/login"
LOGOUT_PATH = "/v1/application/logout"


@dataclass(frozen=True)
class AccessToken:
    value: str
    token_type: str = "bearer"
    expires_at: Optional[datetime] = None
    scope: tuple[str, ...] = ()
    refresh_token: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def is_fresh(self, *, skew_seconds: int = REFRESH_SKEW_SECONDS) -> bool:
        """`True` while the token is safe to use.

        A token with no known expiry is treated as fresh: the vendor gave
        us nothing to act on, and refusing to use it would break the
        integration on a missing optional field.
        """
        if self.expires_at is None:
            return True
        return datetime.now(timezone.utc) + timedelta(seconds=skew_seconds) < self.expires_at


class TokenCache(Protocol):
    def get(self, key: str) -> Optional[AccessToken]: ...
    def set(self, key: str, token: AccessToken) -> None: ...
    def clear(self, key: str) -> None: ...


class InMemoryTokenCache:
    """Process-local cache. Keyed by `(base_url, client_id)` so a sandbox
    token can never be served to a production call, or vice versa."""

    def __init__(self) -> None:
        self._tokens: dict[str, AccessToken] = {}

    def get(self, key: str) -> Optional[AccessToken]:
        return self._tokens.get(key)

    def set(self, key: str, token: AccessToken) -> None:
        self._tokens[key] = token

    def clear(self, key: str) -> None:
        self._tokens.pop(key, None)


def parse_expiry(payload: dict[str, Any]) -> Optional[datetime]:
    """`OAuth2AccessToken` → an absolute UTC expiry, or `None`.

    Gate 0 read the model out of the vendor's live spec, which narrows this
    to **two** shapes rather than the four we would otherwise have to
    guess at: `expiration` is a `string` / `format: date-time` (ISO-8601),
    and `expiresIn` is an `int32` — seconds, per OAuth2 convention.
    `refreshToken` is `{value}` and carries no expiry of its own.

    Prefer the absolute value: a relative one is measured from a clock we
    do not share. Whether `expiration` is actually populated is Gate 1.2 —
    hence the fallback, and the WARNING when neither is present.
    """
    expiration = payload.get("expiration")
    if isinstance(expiration, str) and expiration.strip():
        raw = expiration.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(
                "imovelweb: could not parse expiration=%r — falling back to expiresIn",
                expiration,
            )
    if isinstance(expiration, (int, float)):
        # Not documented as a number, but a Java epoch would be millis.
        seconds = expiration / 1000 if expiration > 10_000_000_000 else expiration
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            logger.warning("imovelweb: expiration=%r is not a usable epoch", expiration)

    expires_in = payload.get("expiresIn")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))

    logger.warning(
        "imovelweb: login response carries neither a usable 'expiration' nor "
        "'expiresIn' — treating the token as non-expiring. Record what the "
        "vendor actually sends (Gate 1.2) and tighten this."
    )
    return None


def token_from_payload(payload: dict[str, Any]) -> AccessToken:
    """`OAuth2AccessToken` JSON → our value object."""
    value = payload.get("value") or payload.get("access_token") or ""
    if not value:
        raise ImovelWebUpstreamError(
            "login succeeded but the response carried no token value"
        )
    refresh = payload.get("refreshToken")
    if isinstance(refresh, dict):
        refresh = refresh.get("value")
    scope = payload.get("scope") or ()
    return AccessToken(
        value=value,
        token_type=payload.get("tokenType") or "bearer",
        expires_at=parse_expiry(payload),
        scope=tuple(scope) if isinstance(scope, (list, tuple)) else (),
        refresh_token=refresh if isinstance(refresh, str) else None,
        raw=dict(payload),
    )


class ImovelWebAuth:
    """Fetches and caches the application token.

    **Single-flight.** One `asyncio.Lock` per cache key, so N concurrent
    callers cause ONE login rather than N. This is not a micro-optimisation:
    the reconciliation job pages through every agency's messages, and
    without it each page would re-authenticate.
    """

    def __init__(
        self,
        *,
        base_url: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        http_client: Any = None,
        cache: Optional[TokenCache] = None,
        skew_seconds: int = REFRESH_SKEW_SECONDS,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_client = http_client
        self._cache: TokenCache = cache if cache is not None else InMemoryTokenCache()
        self._skew = skew_seconds
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._client_id and self._client_secret)

    @property
    def cache_key(self) -> str:
        return f"{self._base_url}|{self._client_id}"

    def _require_config(self) -> None:
        if not self.configured:
            missing = [
                name
                for name, value in (
                    ("base_url", self._base_url),
                    ("client_id", self._client_id),
                    ("client_secret", self._client_secret),
                )
                if not value
            ]
            raise ImovelWebConfigError(
                "ImovelWeb is not configured — missing " + ", ".join(missing)
                + ". Request Sandbox credentials from integracao@imovelweb.com.br."
            )

    def _lock(self) -> asyncio.Lock:
        key = self.cache_key
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    def redact(self, text: Optional[str]) -> Optional[str]:
        """Strip both secrets we hold from any string leaving this object."""
        cached = self._cache.get(self.cache_key)
        return redact_secrets(
            text, self._client_secret, cached.value if cached else None
        )

    async def token(self, *, force: bool = False) -> AccessToken:
        """A usable token, from cache when fresh."""
        self._require_config()
        key = self.cache_key

        if not force:
            cached = self._cache.get(key)
            if cached is not None and cached.is_fresh(skew_seconds=self._skew):
                return cached

        async with self._lock():
            # Re-check inside the lock: whoever held it may have just
            # logged in, and that is the whole point of single-flight.
            if not force:
                cached = self._cache.get(key)
                if cached is not None and cached.is_fresh(skew_seconds=self._skew):
                    return cached
            token = await self._login()
            self._cache.set(key, token)
            return token

    async def _login(self) -> AccessToken:
        payload = await self._post_login()
        return token_from_payload(payload)

    async def _post_login(self) -> dict[str, Any]:
        """Perform the login call.

        ⚠️ The documented form puts `client_secret` in the QUERY STRING,
        where it lands in access logs, proxies and `str(exception)`.
        Whether the endpoint also accepts `Authorization: Basic` + a form
        body could not be tested at Gate 0 — the grant handler never runs
        unauthenticated — so it is Gate 1.2. Until then we send what is
        documented, and redact aggressively on every error path.
        """
        if self._http_client is None:
            raise ImovelWebConfigError(
                "no http_client supplied to ImovelWebAuth — the seed does not "
                "construct one for you; pass httpx.AsyncClient or a Fake"
            )
        params = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        try:
            response = await self._http_client.post(
                f"{self._base_url}{LOGIN_PATH}", params=params
            )
        except Exception as exc:  # transport-level
            raise ImovelWebUpstreamError(
                f"login transport failure: {self.redact(str(exc))}"
            ) from exc

        status = getattr(response, "status_code", None)
        if status is None or status >= 400:
            raise ImovelWebUpstreamError(
                f"login failed: {self.redact(_describe_error(response))}",
                status=status,
            )
        try:
            return response.json()
        except Exception as exc:
            raise ImovelWebUpstreamError(
                f"login returned an unparseable body: {self.redact(str(exc))}",
                status=status,
            ) from exc

    async def logout(self) -> None:
        """Revoke the cached token.

        **Explicit-only — never wire this to a shutdown hook.** The MCP
        connector and the product backend may share one credential pair,
        and one process logging out on exit would revoke the other's live
        token.
        """
        self._require_config()
        cached = self._cache.get(self.cache_key)
        if cached is None:
            return
        if self._http_client is not None:
            try:
                await self._http_client.post(
                    f"{self._base_url}{LOGOUT_PATH}",
                    params={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "token": cached.value,
                    },
                )
            except Exception as exc:
                # A failed revoke is worth knowing about but must not stop
                # us dropping our own copy.
                logger.warning(
                    "imovelweb: logout call failed: %s", self.redact(str(exc))
                )
        self._cache.clear(self.cache_key)


def _describe_error(response: Any) -> str:
    """Best-effort description of a failed response.

    Gate 0 observed that this vendor answers errors in **XML**, not JSON,
    despite its spec declaring `produces: */*` — a 401 returns
    `<UnauthorizedException><error>…</error><error_description>…</error_description></UnauthorizedException>`.
    Assuming JSON here would turn every upstream failure into a decode
    error and hide the vendor's actual message.
    """
    from .real import describe_error_body  # local import: avoids a cycle

    return describe_error_body(response)


__all__ = [
    "LOGIN_PATH",
    "LOGOUT_PATH",
    "REFRESH_SKEW_SECONDS",
    "AccessToken",
    "ImovelWebAuth",
    "InMemoryTokenCache",
    "TokenCache",
    "parse_expiry",
    "token_from_payload",
]

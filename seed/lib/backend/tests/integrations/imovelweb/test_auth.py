"""OAuth2 client-credentials: expiry parsing, skew, and single-flight."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.integrations.imovelweb.auth import (
    REFRESH_SKEW_SECONDS,
    AccessToken,
    ImovelWebAuth,
    InMemoryTokenCache,
    parse_expiry,
    token_from_payload,
)
from noctusai_lib.integrations.imovelweb.errors import (
    ImovelWebConfigError,
    ImovelWebUpstreamError,
)

_LOGGER = "noctusai_lib.integrations.imovelweb.auth"


class _Response:
    def __init__(self, payload=None, *, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _RecordingHttpClient:
    """Counts logins. The DI seam — nothing is monkeypatched."""

    def __init__(self, payload=None, *, delay: float = 0.0, status_code: int = 200):
        self.payload = payload if payload is not None else {
            "value": "tok-1", "tokenType": "bearer", "expiresIn": 3600
        }
        self.delay = delay
        self.status_code = status_code
        self.post_calls: list[tuple] = []

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        return _Response(self.payload, status_code=self.status_code)


def _auth(http_client=None, **overrides) -> ImovelWebAuth:
    kwargs = dict(
        base_url="https://api-br-sandbox-open.navent.com",
        client_id="cid",
        client_secret="csecret-long-enough",
        http_client=http_client or _RecordingHttpClient(),
        cache=InMemoryTokenCache(),
    )
    kwargs.update(overrides)
    return ImovelWebAuth(**kwargs)


class TestParseExpiry:
    """Gate 0 read the model from the vendor's live spec, narrowing this to
    two documented shapes rather than four guessed ones."""

    def test_prefers_absolute_iso_expiration(self):
        when = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        assert parse_expiry({"expiration": when.isoformat(), "expiresIn": 60}) == when

    def test_handles_trailing_z(self):
        parsed = parse_expiry({"expiration": "2026-08-17T12:00:00Z"})
        assert parsed == datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    def test_naive_expiration_is_read_as_utc(self):
        parsed = parse_expiry({"expiration": "2026-08-17T12:00:00"})
        assert parsed.tzinfo is timezone.utc

    def test_falls_back_to_relative_expires_in(self):
        before = datetime.now(timezone.utc)
        parsed = parse_expiry({"expiresIn": 3600})
        assert timedelta(minutes=59) < parsed - before < timedelta(minutes=61)

    def test_unparseable_expiration_falls_back_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            parsed = parse_expiry({"expiration": "not a date", "expiresIn": 60})
        assert parsed is not None
        assert "could not parse expiration" in caplog.text

    def test_no_expiry_at_all_warns_loudly(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert parse_expiry({}) is None
        assert "neither a usable" in caplog.text

    def test_epoch_millis_are_tolerated(self):
        millis = 1_800_000_000_000
        parsed = parse_expiry({"expiration": millis})
        assert parsed.year > 2020


class TestTokenFromPayload:
    def test_unwraps_the_nested_refresh_token(self):
        token = token_from_payload(
            {"value": "t", "refreshToken": {"value": "r"}, "scope": ["a", "b"]}
        )
        assert token.refresh_token == "r"
        assert token.scope == ("a", "b")

    def test_raises_when_no_token_value(self):
        with pytest.raises(ImovelWebUpstreamError, match="no token value"):
            token_from_payload({"tokenType": "bearer"})


class TestFreshness:
    def test_token_without_expiry_is_treated_as_fresh(self):
        # The vendor gave us nothing to act on; refusing to use the token
        # would break the integration over a missing optional field.
        assert AccessToken(value="t").is_fresh() is True

    def test_token_expiring_inside_the_skew_is_stale(self):
        soon = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_SKEW_SECONDS - 5)
        assert AccessToken(value="t", expires_at=soon).is_fresh() is False

    def test_token_expiring_beyond_the_skew_is_fresh(self):
        later = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_SKEW_SECONDS + 60)
        assert AccessToken(value="t", expires_at=later).is_fresh() is True


class TestTokenLifecycle:
    @pytest.mark.asyncio
    async def test_unconfigured_raises_424_not_an_outage(self):
        auth = _auth(client_secret=None)
        with pytest.raises(ImovelWebConfigError) as exc:
            await auth.token()
        assert exc.value.status == 424
        assert "client_secret" in str(exc.value)

    @pytest.mark.asyncio
    async def test_second_call_is_served_from_cache(self):
        http = _RecordingHttpClient()
        auth = _auth(http)
        await auth.token()
        await auth.token()
        assert len(http.post_calls) == 1

    @pytest.mark.asyncio
    async def test_force_bypasses_the_cache(self):
        http = _RecordingHttpClient()
        auth = _auth(http)
        await auth.token()
        await auth.token(force=True)
        assert len(http.post_calls) == 2

    @pytest.mark.asyncio
    async def test_single_flight_causes_one_login_for_n_callers(self):
        # Not a micro-optimisation: the reconciliation job pages through
        # every agency's messages, and without this each page would
        # re-authenticate.
        http = _RecordingHttpClient(delay=0.02)
        auth = _auth(http)
        await asyncio.gather(*(auth.token() for _ in range(10)))
        assert len(http.post_calls) == 1

    @pytest.mark.asyncio
    async def test_cache_key_separates_sandbox_from_prod(self):
        sandbox = _auth(base_url="https://api-br-sandbox-open.navent.com")
        prod = _auth(base_url="https://api-br-open.navent.com")
        assert sandbox.cache_key != prod.cache_key

    @pytest.mark.asyncio
    async def test_failed_login_raises_upstream_not_config(self):
        http = _RecordingHttpClient(status_code=500)
        with pytest.raises(ImovelWebUpstreamError):
            await _auth(http).token()

    @pytest.mark.asyncio
    async def test_transport_failure_is_upstream(self):
        class _Boom:
            async def post(self, *a, **k):
                raise RuntimeError("connection reset")

        with pytest.raises(ImovelWebUpstreamError, match="transport failure"):
            await _auth(_Boom()).token()

    @pytest.mark.asyncio
    async def test_logout_clears_the_cache_even_if_the_call_fails(self):
        class _FailingLogout(_RecordingHttpClient):
            async def post(self, url, **kwargs):
                if "logout" in url:
                    raise RuntimeError("vendor down")
                return await super().post(url, **kwargs)

        http = _FailingLogout()
        auth = _auth(http)
        await auth.token()
        await auth.logout()
        # A failed revoke must not stop us dropping our own copy.
        assert auth._cache.get(auth.cache_key) is None  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_no_http_client_is_a_config_error(self):
        # Constructed directly: the `_auth` helper substitutes a recording
        # client for a falsy one, so it cannot express this case.
        auth = ImovelWebAuth(
            base_url="https://api-br-sandbox-open.navent.com",
            client_id="cid",
            client_secret="csecret-long-enough",
            http_client=None,
            cache=InMemoryTokenCache(),
        )
        with pytest.raises(ImovelWebConfigError, match="no http_client"):
            await auth.token()


class TestRedaction:
    @pytest.mark.asyncio
    async def test_secret_never_survives_an_error_message(self):
        secret = "csecret-long-enough"

        class _Leaky:
            async def post(self, *a, **k):
                raise RuntimeError(f"failed with client_secret={secret}")

        auth = _auth(_Leaky())
        with pytest.raises(ImovelWebUpstreamError) as exc:
            await auth.token()
        assert secret not in str(exc.value)
        assert "REDACTED" in str(exc.value)

    @pytest.mark.asyncio
    async def test_bearer_token_never_survives_either(self):
        http = _RecordingHttpClient({"value": "tok-supersecret", "expiresIn": 3600})
        auth = _auth(http)
        await auth.token()
        assert "tok-supersecret" not in (auth.redact("leaked tok-supersecret") or "")

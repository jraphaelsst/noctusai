"""`ProductDependencies.get_current_user` — 401 only when Supabase said "no".

2026-10-03: the owner's browser session on social.noctusai.com ended right
after three prod deploys. This dependency (the one every seed product's
standard routers + `get_current_user_org` call) wrapped `auth.get_user` in a
bare `except Exception -> 401 "Nao autenticado"`. gotrue raises
`AuthRetryableError` for any transport failure or Auth 502/503/504, so a blip
while validating a token came back as 401; the SPA's refresh could not fix a
server-side fault, the retry 401'd again, and `onUnauthenticated` signed the
user out. These tests raise what the real client raises.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from gotrue.errors import AuthApiError, AuthRetryableError

from noctusai_seed.dependencies import ProductDependencies


class _Db:
    def __init__(self, get_user):
        self._get_user = get_user

    def get_client(self):
        return SimpleNamespace(auth=SimpleNamespace(get_user=self._get_user))


def _raising(exc):
    def _get_user(_token):
        raise exc

    return _get_user


_REQ = httpx.Request("GET", "https://x.supabase.co/auth/v1/user")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        AuthRetryableError("[Errno 111] Connection refused", 0),
        AuthRetryableError("Bad Gateway", 502),
        AuthRetryableError("Gateway Timeout", 504),
        AuthApiError("Internal Server Error", 500, None),
        AuthApiError("Too Many Requests", 429, "over_request_rate_limit"),
        httpx.ConnectError("connection refused", request=_REQ),
        TimeoutError("timed out"),
    ],
    ids=["conn-refused", "502", "504", "api-500", "api-429", "httpx-connect", "timeout"],
)
async def test_auth_provider_not_answering_is_503_with_retry_after(exc):
    deps = ProductDependencies(_Db(_raising(exc)))
    with pytest.raises(HTTPException) as ei:
        await deps.get_current_user("Bearer valid-but-unverifiable")
    assert ei.value.status_code == 503
    assert ei.value.headers == {"Retry-After": "2"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_provider_rejecting_the_token_is_401(status):
    deps = ProductDependencies(_Db(_raising(AuthApiError("invalid JWT", status, "bad_jwt"))))
    with pytest.raises(HTTPException) as ei:
        await deps.get_current_user("Bearer bad")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_no_user_in_the_answer_is_401():
    deps = ProductDependencies(_Db(lambda _t: SimpleNamespace(user=None)))
    with pytest.raises(HTTPException) as ei:
        await deps.get_current_user("Bearer t")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_header_is_401():
    deps = ProductDependencies(_Db(lambda _t: None))
    with pytest.raises(HTTPException) as ei:
        await deps.get_current_user(None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_user_and_token():
    user = SimpleNamespace(id="u1")
    deps = ProductDependencies(_Db(lambda _t: SimpleNamespace(user=user)))
    assert await deps.get_current_user("Bearer good") == (user, "good")

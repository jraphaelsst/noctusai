"""HttpxMailchimpClient tests — httpx.MockTransport.

Covers:
- Auth header: Basic auth ("anystring", api_key) on every request.
- DC URL: key suffix drives the base URL (``xxxx-us6`` → ``us6.api.mailchimp.com``).
- Error mapping: every status-code → exact exception class.
- Pagination: ``count`` / ``offset`` forwarded as query params.
- PUT-by-hash path: upsert_member hits ``/lists/{id}/members/{hash}``.
- ping / list_audiences / list_members / list_templates / list_campaigns.

Pattern mirrors ``tests/integrations/whatsapp/test_client.py``.
"""

from __future__ import annotations

import asyncio
import base64
import json as json_lib
from typing import Any

import httpx
import pytest

from noctusai_lib.integrations.mailchimp.client import HttpxMailchimpClient
from noctusai_lib.integrations.mailchimp.mappers import subscriber_hash
from noctusai_lib.integrations.mailchimp.types import (
    MailchimpAuthError,
    MailchimpNotFoundError,
    MailchimpRateLimitedError,
    MailchimpRejectedError,
    MailchimpUnreachableError,
)


# ---------------------------------------------------------------------------
# MockTransport helpers
# ---------------------------------------------------------------------------


def _json_transport(
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> httpx.MockTransport:
    """Return a MockTransport that always responds with ``status`` and ``body``."""
    raw = json_lib.dumps(body or {}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=raw)

    return httpx.MockTransport(handler)


def _capturing_transport(
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Return a MockTransport that captures every request into ``captured``."""
    captured: list[httpx.Request] = []
    raw = json_lib.dumps(body or {}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, content=raw)

    return httpx.MockTransport(handler), captured


# ---------------------------------------------------------------------------
# Patch helper: inject a MockTransport into httpx.AsyncClient
# ---------------------------------------------------------------------------


def _make_client(
    api_key: str = "testkey-us6",
    *,
    server_prefix: str | None = None,
    transport: httpx.MockTransport | None = None,
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> tuple[HttpxMailchimpClient, httpx.MockTransport | None]:
    dc = server_prefix or "us6"
    client = HttpxMailchimpClient(api_key, server_prefix=dc)
    # Override _request to use the given transport.
    if transport is None:
        transport = _json_transport(status=status, body=body)
    # Monkey-patch the internal _request to inject the transport.
    original_request = client._request

    async def patched_request(
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        body_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        url = f"{client._base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(transport=transport) as http:
                kwargs: dict[str, Any] = {
                    "auth": ("anystring", client._api_key),
                    "params": params,
                }
                if body_bytes is not None:
                    kwargs["content"] = body_bytes
                    kwargs["headers"] = {"Content-Type": "application/json"}
                elif json is not None:
                    kwargs["json"] = json

                response = await http.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            from noctusai_lib.integrations.mailchimp.types import MailchimpUnreachableError
            raise MailchimpUnreachableError(str(exc), status=0) from exc
        return HttpxMailchimpClient._translate(response)

    client._request = patched_request  # type: ignore[method-assign]
    return client, transport


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


def test_basic_auth_header_sent() -> None:
    """Every request must carry a Basic auth header with the API key."""
    transport, captured = _capturing_transport(
        status=200, body={"health_status": "Everything's Chimpy!"}
    )
    client, _ = _make_client("mykey-us6", transport=transport)
    asyncio.run(client.ping())

    assert len(captured) == 1
    req = captured[0]
    auth_header = req.headers.get("authorization", "")
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[len("Basic "):]).decode()
    username, password = decoded.split(":", 1)
    assert username == "anystring"
    assert password == "mykey-us6"


# ---------------------------------------------------------------------------
# DC URL derivation from key suffix
# ---------------------------------------------------------------------------


def test_dc_url_derived_from_key_us6() -> None:
    client = HttpxMailchimpClient("sometoken-us6", server_prefix="us6")
    assert client._base_url == "https://us6.api.mailchimp.com/3.0"


def test_dc_url_derived_from_key_eu1() -> None:
    client = HttpxMailchimpClient("sometoken-eu1", server_prefix="eu1")
    assert client._base_url == "https://eu1.api.mailchimp.com/3.0"


def test_dc_url_request_goes_to_correct_host() -> None:
    transport, captured = _capturing_transport(
        status=200, body={"health_status": "Everything's Chimpy!"}
    )
    client, _ = _make_client("tok-us19", server_prefix="us19", transport=transport)
    asyncio.run(client.ping())
    assert "us19.api.mailchimp.com" in str(captured[0].url)


# ---------------------------------------------------------------------------
# Error status → exception class mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error_on_401_403(status: int) -> None:
    client, _ = _make_client(
        status=status,
        body={"title": "API Key Invalid", "detail": "Check the key."},
    )
    with pytest.raises(MailchimpAuthError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == status
    assert exc_info.value.title == "API Key Invalid"


def test_not_found_error_on_404() -> None:
    client, _ = _make_client(
        status=404,
        body={"title": "Resource Not Found", "detail": "No such list."},
    )
    with pytest.raises(MailchimpNotFoundError) as exc_info:
        asyncio.run(client.get_audience("missing"))
    assert exc_info.value.status == 404


def test_rate_limited_error_on_429() -> None:
    client, _ = _make_client(
        status=429,
        body={"title": "Too Many Requests", "detail": "Slow down."},
    )
    with pytest.raises(MailchimpRateLimitedError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == 429


@pytest.mark.parametrize("status", [400, 422])
def test_rejected_error_on_400_422(status: int) -> None:
    client, _ = _make_client(
        status=status,
        body={"title": "Bad Request", "detail": "Email already exists."},
    )
    with pytest.raises(MailchimpRejectedError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == status
    assert exc_info.value.detail == "Email already exists."


def test_unreachable_error_on_500() -> None:
    client, _ = _make_client(
        status=500,
        body={"title": "Internal Server Error"},
    )
    with pytest.raises(MailchimpUnreachableError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == 500


def test_unreachable_error_on_503() -> None:
    client, _ = _make_client(status=503, body={})
    with pytest.raises(MailchimpUnreachableError):
        asyncio.run(client.ping())


def test_transport_error_raises_unreachable() -> None:
    """Network-level failure (e.g. connection refused) → MailchimpUnreachableError."""

    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(fail_handler)
    client, _ = _make_client(transport=transport)
    with pytest.raises(MailchimpUnreachableError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == 0


# ---------------------------------------------------------------------------
# Pagination params forwarded
# ---------------------------------------------------------------------------


def test_list_audiences_forwards_count_offset() -> None:
    transport, captured = _capturing_transport(
        status=200,
        body={"lists": [], "total_items": 0},
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(client.list_audiences(count=10, offset=20))
    params = dict(captured[0].url.params)
    assert params["count"] == "10"
    assert params["offset"] == "20"


def test_list_members_forwards_count_offset_status() -> None:
    transport, captured = _capturing_transport(
        status=200,
        body={"members": [], "total_items": 0},
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(
        client.list_members("aud-1", count=5, offset=10, status="subscribed")
    )
    params = dict(captured[0].url.params)
    assert params["count"] == "5"
    assert params["offset"] == "10"
    assert params["status"] == "subscribed"


def test_list_templates_forwards_count_offset() -> None:
    transport, captured = _capturing_transport(
        status=200,
        body={"templates": [], "total_items": 0},
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(client.list_templates(count=3, offset=6))
    params = dict(captured[0].url.params)
    assert params["count"] == "3"
    assert params["offset"] == "6"
    assert params["type"] == "user"


def test_list_campaigns_forwards_count_offset() -> None:
    transport, captured = _capturing_transport(
        status=200,
        body={"campaigns": [], "total_items": 0},
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(client.list_campaigns(count=7, offset=14))
    params = dict(captured[0].url.params)
    assert params["count"] == "7"
    assert params["offset"] == "14"


# ---------------------------------------------------------------------------
# PUT-by-hash path for upsert_member
# ---------------------------------------------------------------------------


def test_upsert_member_puts_to_hash_path() -> None:
    email = "user@example.com"
    expected_hash = subscriber_hash(email)
    transport, captured = _capturing_transport(
        status=200,
        body={
            "email_address": email,
            "status": "subscribed",
            "merge_fields": {"FNAME": "", "LNAME": ""},
            "tags": [],
            "vip": False,
        },
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(client.upsert_member("aud-1", email))
    req = captured[0]
    assert req.method == "PUT"
    assert f"/members/{expected_hash}" in str(req.url)


def test_upsert_member_body_contains_status_if_new() -> None:
    email = "new@example.com"
    transport, captured = _capturing_transport(
        status=200,
        body={
            "email_address": email,
            "status": "subscribed",
            "merge_fields": {"FNAME": "", "LNAME": ""},
            "tags": [],
            "vip": False,
        },
    )
    client, _ = _make_client(transport=transport)
    asyncio.run(
        client.upsert_member("aud-1", email, status_if_new="pending")
    )
    body = json_lib.loads(captured[0].content)
    assert body["status_if_new"] == "pending"


# ---------------------------------------------------------------------------
# ping response shape
# ---------------------------------------------------------------------------


def test_ping_returns_parsed_body() -> None:
    client, _ = _make_client(
        status=200,
        body={"health_status": "Everything's Chimpy!"},
    )
    result = asyncio.run(client.ping())
    assert result["health_status"] == "Everything's Chimpy!"


# ---------------------------------------------------------------------------
# 204 No Content — empty body returns {}
# ---------------------------------------------------------------------------


def test_204_no_content_returns_empty_dict() -> None:
    def no_content_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204, content=b"")

    transport = httpx.MockTransport(no_content_handler)
    client, _ = _make_client(transport=transport)
    result = asyncio.run(client.archive_member("aud-1", "someone@test.com"))
    assert result is None  # archive_member returns None (no return value)

"""WahaClient send/download path tests — failure modes + header shape."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from noctusai_lib.integrations.whatsapp.client import WahaClient


# ---- Helpers -----------------------------------------------------------------


def _make_response(status_code: int = 200, json_body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {"id": "msg-123"}
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def _async_post_ctx(response: MagicMock) -> MagicMock:
    """Build an ``httpx.AsyncClient`` context-manager mock whose ``post``
    returns ``response`` — mirrors test_client_identity.py's `_async_ctx`
    (that file scopes to identity-resolution GET calls; this is the POST
    sibling for admin/action endpoints like `/api/sendSeen`)."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=response)
    return mock_client


# ---- send_text_sync ---------------------------------------------------------


def test_send_text_sync_returns_parsed_json_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.post.return_value = _make_response(200, {"id": "msg-abc"})

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    result = client.send_text_sync("5511999999999@c.us", "olá")

    assert result == {"id": "msg-abc"}
    assert fake_client.post.called
    posted_body = fake_client.post.call_args.kwargs["json"]
    assert posted_body["session"] == "default"
    assert posted_body["chatId"] == "5511999999999@c.us"
    assert posted_body["text"] == "olá"


def test_send_text_sync_propagates_5xx_as_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.post.return_value = _make_response(503)

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        client.send_text_sync("phone@c.us", "x")


def test_send_text_sync_propagates_4xx_as_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.post.return_value = _make_response(401)

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="bad-key")
    with pytest.raises(httpx.HTTPStatusError):
        client.send_text_sync("phone@c.us", "x")


def test_send_text_sync_propagates_network_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.post.side_effect = httpx.TimeoutException("read timeout")

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    with pytest.raises(httpx.TimeoutException):
        client.send_text_sync("phone@c.us", "x")


# ---- send_seen ---------------------------------------------------------------
# WAHA's SendSeenRequest schema (POST /api/sendSeen, verified against the live
# fleet's own OpenAPI spec): requires chatId + session; messageId + participant
# optional. These tests pin the exact body shape.


def test_send_seen_posts_full_body_when_message_id_and_participant_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _make_response(201, {"success": True})
    resp.content = b'{"success":true}'
    ctx = _async_post_ctx(resp)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    result = asyncio.run(
        client.send_seen(
            "120363@g.us",
            message_id="false_120363@g.us_ABCDEF",
            participant="5511999999999@c.us",
        )
    )

    assert result == {"success": True}
    ctx.post.assert_called_once()
    call = ctx.post.call_args
    assert call.args[0] == "/api/sendSeen"
    body = call.kwargs["json"]
    assert body == {
        "session": "default",
        "chatId": "120363@g.us",
        "messageId": "false_120363@g.us_ABCDEF",
        "participant": "5511999999999@c.us",
    }
    assert call.kwargs["headers"]["Content-Type"] == "application/json"


def test_send_seen_omits_optional_fields_when_not_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _make_response(201, {})
    resp.content = b""
    ctx = _async_post_ctx(resp)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    result = asyncio.run(client.send_seen("5511999999999@c.us"))

    body = ctx.post.call_args.kwargs["json"]
    assert body == {"session": "default", "chatId": "5511999999999@c.us"}
    # An empty body (WAHA sometimes answers a bare 2xx) tolerates via _safe_json.
    assert result == {}


def test_send_seen_propagates_5xx_as_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _make_response(503)
    ctx = _async_post_ctx(resp)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.send_seen("c@c.us"))


# ---- Header behavior --------------------------------------------------------


def test_headers_include_api_key_when_configured() -> None:
    client = WahaClient(base_url="https://waha", api_key="secret-123")
    headers = client._headers(json=True)
    assert headers["X-Api-Key"] == "secret-123"
    assert headers["Content-Type"] == "application/json"


def test_headers_omit_api_key_when_none() -> None:
    client = WahaClient(base_url="https://waha", api_key=None)
    headers = client._headers(json=True)
    assert "X-Api-Key" not in headers
    assert headers["Content-Type"] == "application/json"


def test_headers_omit_content_type_when_json_false() -> None:
    client = WahaClient(base_url="https://waha", api_key="k")
    headers = client._headers(json=False)
    assert "Content-Type" not in headers
    assert headers["X-Api-Key"] == "k"


def test_base_url_strips_trailing_slash() -> None:
    client = WahaClient(base_url="https://waha.test/", api_key=None)
    assert client.base_url == "https://waha.test"


# ---- download_media_sync ----------------------------------------------------


def test_download_media_sync_returns_bytes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    response = _make_response(200)
    response.content = b"\x00binary"
    fake_client.get.return_value = response

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    out = client.download_media_sync("https://waha.test/media/abc")
    assert out == b"\x00binary"


def test_download_media_sync_raises_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.return_value = _make_response(502)

    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        client.download_media_sync("https://waha.test/media/x")


# ---- vendor media-URL rewrite (SESSION-NOTES §4.3) --------------------------


def test_download_media_sync_rewrites_external_host_to_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    response = _make_response(200)
    response.content = b"oga-bytes"
    fake_client.get.return_value = response
    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    # base_url = docker-internal host the app reaches; external_base_url
    # = the host WAHA emits in media URLs.
    client = WahaClient(
        base_url="http://waha:3000",
        api_key="k",
        external_base_url="http://localhost:3000",
    )
    client.download_media_sync(
        "http://localhost:3000/api/files/default/false_3EB0.oga"
    )

    called_url = fake_client.get.call_args[0][0]
    assert called_url == "http://waha:3000/api/files/default/false_3EB0.oga"


def test_download_media_sync_noop_rewrite_when_single_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    response = _make_response(200)
    response.content = b"x"
    fake_client.get.return_value = response
    monkeypatch.setattr(httpx, "Client", lambda **_: fake_client)

    # external_base_url defaults to base_url ⇒ rewrite is a no-op.
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.download_media_sync("https://waha.test/media/abc")

    assert fake_client.get.call_args[0][0] == "https://waha.test/media/abc"


# ── _session_config: the anti-clobber guarantee (2026-06-23 empty-inbox bug) ──
# WAHA's session-config PUT is a full REPLACE; every config write MUST re-assert
# the NOWEB store or it gets dropped. These pin that contract structurally.

from noctusai_lib.integrations.whatsapp.client import _session_config  # noqa: E402


def test_session_config_always_includes_noweb_store() -> None:
    cfg = _session_config()["config"]
    assert cfg["noweb"]["store"]["enabled"] is True
    assert cfg["noweb"]["store"]["fullSync"] is True
    assert "webhooks" not in cfg  # no webhooks unless asked


def test_session_config_with_webhooks_keeps_BOTH_webhooks_and_store() -> None:
    # The regression: a webhook write must NOT drop the store block.
    hooks = [{"url": "https://x/wh", "events": ["message"]}]
    cfg = _session_config(webhooks=hooks)["config"]
    assert cfg["webhooks"] == hooks
    assert cfg["noweb"]["store"]["enabled"] is True
    assert cfg["noweb"]["store"]["fullSync"] is True


def test_set_webhook_put_body_reasserts_noweb_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """set_webhook's PUT must carry the store block (anti-clobber)."""
    import asyncio

    captured: dict = {}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def put(self, url, *, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            resp = _make_response(200)
            resp.content = b'{"name":"default"}'
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: _FakeAsyncClient())
    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    asyncio.run(client.set_webhook("https://x/wh", ["message", "session.status"]))

    cfg = captured["json"]["config"]
    assert cfg["webhooks"][0]["url"] == "https://x/wh"
    assert cfg["noweb"]["store"]["enabled"] is True, "webhook PUT dropped the store!"
    assert cfg["noweb"]["store"]["fullSync"] is True


def test_session_config_wire_key_is_camel_case_full_sync() -> None:
    """Pins the exact wire-format key. WAHA's NOWEB config key is
    camelCase ``fullSync`` — a prior snake_case ``full_sync`` typo was
    silently dropped by WAHA (unrecognized key ⇒ its own `false` default
    applied) and NOWEB never backfilled history. Nothing raised; this
    test is the only thing that would have caught it, because it asserts
    the exact emitted JSON key string rather than a Python-side alias.
    """
    payload = _session_config()
    assert "fullSync" in payload["config"]["noweb"]["store"]
    assert "full_sync" not in payload["config"]["noweb"]["store"]
    assert payload["config"]["noweb"]["store"]["fullSync"] is True

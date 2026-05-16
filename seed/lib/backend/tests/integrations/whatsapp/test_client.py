"""WahaClient send/download path tests — failure modes + header shape."""

from __future__ import annotations

from unittest.mock import MagicMock

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

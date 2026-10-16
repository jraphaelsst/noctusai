"""MetaCloudClient + FakeMetaCloudClient + get_meta_cloud_client factory tests.

Mirrors the patterns in `test_client.py` (WahaClient) per
`KB § PATTERNS/seed-fake-real-adapter.md`. Patches `httpx.AsyncClient` at
the seed module's import site — never monkey-patches the seed's own
methods.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from noctusai_lib.integrations.whatsapp import (
    META_CLOUD_DEFAULT_BASE_URL,
    FakeMetaCloudClient,
    MetaCloudClient,
    get_meta_cloud_client,
)
from noctusai_lib.integrations.whatsapp import meta_cloud_client as meta_cloud_module


# ---- Helpers ----------------------------------------------------------------


def _make_response(status_code: int = 200, json_body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(
        return_value=json_body
        or {
            "messaging_product": "whatsapp",
            "contacts": [{"input": "5511912345678", "wa_id": "5511912345678"}],
            "messages": [{"id": "wamid.abc"}],
        }
    )
    if status_code >= 400:
        response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"{status_code} error",
                request=MagicMock(),
                response=MagicMock(status_code=status_code),
            )
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def _install_fake_async_client(
    monkeypatch: pytest.MonkeyPatch, response: MagicMock
) -> dict[str, object]:
    """Patch `meta_cloud_module.httpx.AsyncClient` to return our mock,
    capturing the post call args. Returns a dict the test can read."""
    captured: dict[str, object] = {}

    async def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return response

    fake_async_client = AsyncMock()
    fake_async_client.post = fake_post
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        meta_cloud_module.httpx,
        "AsyncClient",
        lambda **_: fake_async_client,
    )
    return captured


# ---- MetaCloudClient.send_text — happy path --------------------------------


@pytest.mark.asyncio
async def test_send_text_returns_parsed_json_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fake_async_client(
        monkeypatch,
        _make_response(200, {"messages": [{"id": "wamid.xyz"}]}),
    )

    client = MetaCloudClient(
        phone_number_id="999",
        api_key="secret-key",
        base_url="https://graph.facebook.com/v18.0",
    )
    result = await client.send_text("5511912345678", "Olá")

    assert result == {"messages": [{"id": "wamid.xyz"}]}
    assert captured["url"] == "https://graph.facebook.com/v18.0/999/messages"


@pytest.mark.asyncio
async def test_send_text_body_shape_matches_meta_cloud_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200))

    client = MetaCloudClient(phone_number_id="999", api_key="k")
    await client.send_text("5511912345678", "Olá mundo")

    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "to": "5511912345678",
        "type": "text",
        "text": {"body": "Olá mundo"},
    }


@pytest.mark.asyncio
async def test_send_text_headers_carry_bearer_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200))

    client = MetaCloudClient(phone_number_id="999", api_key="secret-token")
    await client.send_text("5511999999999", "hi")

    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["Content-Type"] == "application/json"


# ---- MetaCloudClient.send_text — error paths --------------------------------


@pytest.mark.asyncio
async def test_send_text_propagates_4xx_as_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_async_client(monkeypatch, _make_response(401))

    client = MetaCloudClient(phone_number_id="999", api_key="bad-key")
    with pytest.raises(httpx.HTTPStatusError):
        await client.send_text("5511999999999", "x")


@pytest.mark.asyncio
async def test_send_text_propagates_5xx_as_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_async_client(monkeypatch, _make_response(503))

    client = MetaCloudClient(phone_number_id="999", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        await client.send_text("5511999999999", "x")


# ---- URL / base_url behavior ------------------------------------------------


def test_base_url_strips_trailing_slash() -> None:
    client = MetaCloudClient(
        phone_number_id="999",
        api_key="k",
        base_url="https://graph.facebook.com/v18.0/",
    )
    assert client.base_url == "https://graph.facebook.com/v18.0"


def test_send_url_composition() -> None:
    client = MetaCloudClient(
        phone_number_id="123",
        api_key="k",
        base_url="https://graph.facebook.com/v19.0",
    )
    assert client.send_url == "https://graph.facebook.com/v19.0/123/messages"


def test_default_base_url_is_v18() -> None:
    client = MetaCloudClient(phone_number_id="123", api_key="k")
    assert client.base_url == META_CLOUD_DEFAULT_BASE_URL
    assert client.base_url == "https://graph.facebook.com/v18.0"


# ---- FakeMetaCloudClient ----------------------------------------------------


@pytest.mark.asyncio
async def test_fake_records_sent_messages() -> None:
    fake = FakeMetaCloudClient(phone_number_id="999")
    response = await fake.send_text("5511912345678", "olá")

    assert len(fake.sent_messages) == 1
    assert fake.sent_messages[0]["phone"] == "5511912345678"
    assert fake.sent_messages[0]["text"] == "olá"
    assert fake.sent_messages[0]["message_id"].startswith("fake-meta-")


@pytest.mark.asyncio
async def test_fake_response_envelope_shape() -> None:
    fake = FakeMetaCloudClient(phone_number_id="999")
    response = await fake.send_text("5511912345678", "olá")

    # Canonical Meta Cloud API response envelope.
    assert response["messaging_product"] == "whatsapp"
    assert "messages" in response
    assert response["messages"][0]["id"].startswith("fake-meta-")


@pytest.mark.asyncio
async def test_fake_increments_message_ids() -> None:
    fake = FakeMetaCloudClient(phone_number_id="999")
    r1 = await fake.send_text("5511111111111", "a")
    r2 = await fake.send_text("5511222222222", "b")
    assert r1["messages"][0]["id"] == "fake-meta-1"
    assert r2["messages"][0]["id"] == "fake-meta-2"


@pytest.mark.asyncio
async def test_fake_clear_resets_recorded_messages() -> None:
    fake = FakeMetaCloudClient(phone_number_id="999")
    await fake.send_text("5511912345678", "olá")
    assert len(fake.sent_messages) == 1
    fake.clear()
    assert fake.sent_messages == []


# ---- get_meta_cloud_client factory -----------------------------------------


def test_factory_returns_fake_when_api_key_is_none() -> None:
    client = get_meta_cloud_client(phone_number_id="999", api_key=None)
    assert isinstance(client, FakeMetaCloudClient)


def test_factory_returns_fake_when_api_key_is_empty_string() -> None:
    client = get_meta_cloud_client(phone_number_id="999", api_key="")
    assert isinstance(client, FakeMetaCloudClient)


def test_factory_returns_real_when_api_key_is_set() -> None:
    client = get_meta_cloud_client(phone_number_id="999", api_key="secret-key")
    assert isinstance(client, MetaCloudClient)
    assert client.api_key == "secret-key"
    assert client.phone_number_id == "999"


def test_factory_respects_custom_base_url() -> None:
    client = get_meta_cloud_client(
        phone_number_id="999",
        api_key="k",
        base_url="https://graph.facebook.com/v19.0",
    )
    assert client.base_url == "https://graph.facebook.com/v19.0"


@pytest.mark.asyncio
async def test_factory_fake_round_trip() -> None:
    """End-to-end factory → fake → records the send."""
    fake = get_meta_cloud_client(phone_number_id="999", api_key=None)
    assert isinstance(fake, FakeMetaCloudClient)
    response = await fake.send_text("5511912345678", "olá")
    assert response["messages"][0]["id"] == "fake-meta-1"
    assert fake.sent_messages[0]["text"] == "olá"


# ---- template send / business profile / template creation -------------------


@pytest.mark.asyncio
async def test_send_template_body_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200))
    client = MetaCloudClient(phone_number_id="999", api_key="k")
    await client.send_template("5511912345678", "abordagem_comercial", "pt_BR", ["Ana", "Casa 12"])

    assert captured["url"] == "https://graph.facebook.com/v18.0/999/messages"
    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "to": "5511912345678",
        "type": "template",
        "template": {
            "name": "abordagem_comercial",
            "language": {"code": "pt_BR"},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": "Ana"}, {"type": "text", "text": "Casa 12"}]}],
        },
    }


@pytest.mark.asyncio
async def test_send_template_without_params_has_no_components(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200))
    await MetaCloudClient(phone_number_id="999", api_key="k").send_template("5511912345678", "oi")
    assert "components" not in captured["json"]["template"]


@pytest.mark.asyncio
async def test_update_business_profile_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200, {"success": True}))
    client = MetaCloudClient(phone_number_id="999", api_key="k")
    await client.update_business_profile({"about": "Sobre", "description": "Desc", "address": "Rua A",
                                          "email": "a@b.co", "websites": ["https://x.co"], "nome_exibicao": "Ignored"})
    assert captured["url"] == "https://graph.facebook.com/v18.0/999/whatsapp_business_profile"
    assert captured["json"] == {"messaging_product": "whatsapp", "about": "Sobre", "description": "Desc",
                                "address": "Rua A", "email": "a@b.co", "websites": ["https://x.co"]}


@pytest.mark.asyncio
async def test_create_template_posts_to_waba(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_async_client(monkeypatch, _make_response(200, {"id": "1", "status": "PENDING"}))
    client = MetaCloudClient(phone_number_id="999", api_key="k", waba_id="W1")
    out = await client.create_template("t1", "MARKETING", "pt_BR", "Oi {{1}}", ["Ana"])
    assert out["status"] == "PENDING"
    assert captured["url"] == "https://graph.facebook.com/v18.0/W1/message_templates"
    assert captured["json"]["components"] == [{"type": "BODY", "text": "Oi {{1}}", "example": {"body_text": [["Ana"]]}}]


@pytest.mark.asyncio
async def test_create_template_requires_waba_id() -> None:
    with pytest.raises(ValueError):
        await MetaCloudClient(phone_number_id="999", api_key="k").create_template("t", "MARKETING", "pt_BR", "x")


@pytest.mark.asyncio
async def test_fake_records_template_profile_and_creation() -> None:
    fake = FakeMetaCloudClient(phone_number_id="999")
    sent = await fake.send_template("5511912345678", "t1", "pt_BR", ["a"])
    await fake.update_business_profile({"about": "x"})
    created = await fake.create_template("t1", "UTILITY", "pt_BR", "Oi {{1}}", ["a"])
    assert sent["messages"][0]["id"] == "fake-meta-tpl-1"
    assert fake.sent_templates[0]["body_params"] == ["a"]
    assert fake.profile_updates == [{"messaging_product": "whatsapp", "about": "x"}]
    assert created["status"] == "PENDING" and fake.created_templates[0]["name"] == "t1"
    fake.clear()
    assert not fake.sent_templates and not fake.profile_updates and not fake.created_templates


def test_factory_passes_waba_id() -> None:
    assert get_meta_cloud_client(api_key="k", phone_number_id="1", waba_id="W").waba_id == "W"
    assert get_meta_cloud_client(phone_number_id="1", waba_id="W").waba_id == "W"

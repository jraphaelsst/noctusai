"""Tests for FakeWahaClient + get_whatsapp_client factory + WhatsAppClient Protocol.

Pattern parity check: matches the Protocol/Fake/Real/factory test shape
used by google_calendar (test_fake_adapter.py) and google_maps
(test_static_adapter.py).
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.whatsapp import (
    FakeWahaClient,
    WahaClient,
    WhatsAppClient,
    WhatsAppInboundMessage,
    get_whatsapp_client,
)


# ---- send_text -------------------------------------------------------------


def test_send_text_sync_records_in_sent_messages() -> None:
    client = FakeWahaClient()
    response = client.send_text_sync("5511999999999@c.us", "olá")

    assert response["chatId"] == "5511999999999@c.us"
    assert response["text"] == "olá"
    assert response["session"] == "default"
    assert response["id"] == "fake-msg-1"
    assert client.sent_messages == [response]


def test_send_text_async_records_in_sent_messages() -> None:
    client = FakeWahaClient()
    response = asyncio.run(client.send_text("chat-1", "hi"))

    assert response["text"] == "hi"
    assert response["id"] == "fake-msg-1"
    assert len(client.sent_messages) == 1


def test_message_ids_increment_across_sends() -> None:
    client = FakeWahaClient()
    a = client.send_text_sync("c", "first")
    b = client.send_text_sync("c", "second")

    assert a["id"] == "fake-msg-1"
    assert b["id"] == "fake-msg-2"


def test_session_propagates_to_outbound_record() -> None:
    client = FakeWahaClient(session="custom-session")
    response = client.send_text_sync("c", "t")

    assert response["session"] == "custom-session"


# ---- download_media --------------------------------------------------------


def test_download_media_returns_pre_populated_bytes_sync() -> None:
    client = FakeWahaClient()
    client.media_bytes["https://waha/files/audio-1.ogg"] = b"audio-bytes"

    result = client.download_media_sync("https://waha/files/audio-1.ogg")

    assert result == b"audio-bytes"


def test_download_media_returns_pre_populated_bytes_async() -> None:
    client = FakeWahaClient()
    client.media_bytes["url-1"] = b"image-bytes"

    result = asyncio.run(client.download_media("url-1"))

    assert result == b"image-bytes"


def test_download_media_missing_url_raises_keyerror() -> None:
    client = FakeWahaClient()

    with pytest.raises(KeyError, match="missing-url"):
        client.download_media_sync("missing-url")


# ---- inbound queue ---------------------------------------------------------


def test_inject_text_queues_inbound_message() -> None:
    client = FakeWahaClient()
    msg = client.inject_text(
        chat_id="5511999999999@c.us",
        from_phone="5511999999999",
        text="quero agendar pra terça",
    )

    assert client.inbound_queue == [msg]
    assert isinstance(msg, WhatsAppInboundMessage)
    assert msg.text == "quero agendar pra terça"
    assert msg.session == "default"


def test_inject_inbound_preserves_injection_order() -> None:
    client = FakeWahaClient()
    a = client.inject_text(chat_id="c", from_phone="p", text="first")
    b = client.inject_text(chat_id="c", from_phone="p", text="second")

    assert client.inbound_queue == [a, b]


def test_inject_text_propagates_optional_fields() -> None:
    client = FakeWahaClient()
    msg = client.inject_text(
        chat_id="c",
        from_phone="p",
        text="t",
        provider_message_id="provider-msg-1",
        from_name="João",
    )

    assert msg.provider_message_id == "provider-msg-1"
    assert msg.from_name == "João"


# ---- clear -----------------------------------------------------------------


def test_clear_resets_all_state() -> None:
    client = FakeWahaClient()
    client.send_text_sync("chat", "hi")
    client.inject_text(chat_id="c", from_phone="p", text="t")
    client.media_bytes["u"] = b"x"

    client.clear()

    assert client.sent_messages == []
    assert client.inbound_queue == []
    assert client.media_bytes == {}


# ---- factory ---------------------------------------------------------------


def test_factory_returns_fake_when_base_url_unset() -> None:
    client = get_whatsapp_client(base_url=None, api_key="k")
    assert isinstance(client, FakeWahaClient)


def test_factory_returns_fake_when_base_url_empty_string() -> None:
    client = get_whatsapp_client(base_url="", api_key="k")
    assert isinstance(client, FakeWahaClient)


def test_factory_returns_real_when_base_url_set() -> None:
    client = get_whatsapp_client(base_url="https://waha.test", api_key="k")
    assert isinstance(client, WahaClient)


def test_factory_propagates_session_to_fake() -> None:
    client = get_whatsapp_client(base_url=None, session="my-session")
    assert isinstance(client, FakeWahaClient)
    assert client.session == "my-session"


# ---- Protocol conformance --------------------------------------------------


def test_fake_satisfies_whatsapp_client_protocol() -> None:
    client = FakeWahaClient()
    assert isinstance(client, WhatsAppClient)


def test_real_satisfies_whatsapp_client_protocol() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    assert isinstance(client, WhatsAppClient)


# ---- start_session (multi-session pairing) ---------------------------------


def test_start_session_increments_count_and_keeps_qr_state() -> None:
    client = FakeWahaClient()
    payload = asyncio.run(client.start_session())
    assert client.start_count == 1
    # A fresh (unpaired) session offers a QR after start.
    assert payload["status"] == "SCAN_QR_CODE"
    assert asyncio.run(client.get_qr())  # scannable


def test_start_session_leaves_paired_session_working() -> None:
    client = FakeWahaClient()
    client.simulate_pair()
    payload = asyncio.run(client.start_session())
    assert payload["status"] == "WORKING"


def test_real_client_exposes_start_session() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    assert hasattr(client, "start_session")

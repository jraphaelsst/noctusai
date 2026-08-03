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


# The six session-admin methods (get_session/start_session/restart_session/
# logout_session/get_qr/set_webhook) shipped on both WahaClient and
# FakeWahaClient long before they were declared on the Protocol — a partial
# connector still type-checked clean. These pin the completed surface at a
# finer grain than the bare `isinstance(..., WhatsAppClient)` checks above
# (which would only fail opaquely if a method went missing).
_SESSION_ADMIN_AND_NEW_METHODS = (
    "get_session",
    "start_session",
    "restart_session",
    "logout_session",
    "get_qr",
    "set_webhook",
    "recover_session",
    "send_seen",
    "get_chats_overview",
)


@pytest.mark.parametrize("method_name", _SESSION_ADMIN_AND_NEW_METHODS)
def test_fake_exposes_full_admin_and_new_method_surface(method_name: str) -> None:
    client = FakeWahaClient()
    assert callable(getattr(client, method_name, None)), method_name


@pytest.mark.parametrize("method_name", _SESSION_ADMIN_AND_NEW_METHODS)
def test_real_exposes_full_admin_and_new_method_surface(method_name: str) -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    assert callable(getattr(client, method_name, None)), method_name


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


# ---- send_seen ---------------------------------------------------------------


def test_send_seen_records_full_call_shape() -> None:
    client = FakeWahaClient()
    result = asyncio.run(
        client.send_seen(
            "120363@g.us", message_id="msg-1", participant="5511999999999@c.us"
        )
    )

    assert result == {"success": True}
    assert client.seen_calls == [
        {
            "session": "default",
            "chatId": "120363@g.us",
            "messageId": "msg-1",
            "participant": "5511999999999@c.us",
        }
    ]


def test_send_seen_records_none_for_omitted_optional_fields() -> None:
    client = FakeWahaClient()
    asyncio.run(client.send_seen("c@c.us"))

    assert client.seen_calls == [
        {
            "session": "default",
            "chatId": "c@c.us",
            "messageId": None,
            "participant": None,
        }
    ]


def test_send_seen_appends_across_multiple_calls() -> None:
    client = FakeWahaClient()
    asyncio.run(client.send_seen("a@c.us"))
    asyncio.run(client.send_seen("b@c.us"))

    assert [call["chatId"] for call in client.seen_calls] == ["a@c.us", "b@c.us"]


# ---- get_chats_overview -------------------------------------------------------


def test_get_chats_overview_returns_seeded_list_up_to_limit() -> None:
    client = FakeWahaClient()
    client.fake_chats_overview = [
        {"id": f"{i}@c.us", "name": f"Chat {i}", "picture": None, "lastMessage": {}, "_chat": {}}
        for i in range(3)
    ]

    result = asyncio.run(client.get_chats_overview(limit=2))

    assert [c["id"] for c in result] == ["0@c.us", "1@c.us"]


def test_get_chats_overview_returns_empty_list_when_unseeded() -> None:
    client = FakeWahaClient()
    assert asyncio.run(client.get_chats_overview()) == []


# ---- recover_session (fake ladder mirrors WahaClient's) ----------------------


def test_recover_session_fake_already_working_short_circuits() -> None:
    client = FakeWahaClient()
    client.simulate_pair()

    result = asyncio.run(client.recover_session())

    assert result["stage"] == "already_working"
    assert result["status"] == "WORKING"
    assert result["paired"] is True
    assert client.start_count == 0


def test_recover_session_fake_converges_at_start_for_never_paired_session() -> None:
    client = FakeWahaClient()  # default: unpaired, SCAN_QR_CODE

    result = asyncio.run(client.recover_session())

    assert result["stage"] == "start"
    assert result["status"] == "SCAN_QR_CODE"
    assert result["paired"] is False
    assert client.restart_count == 0


def test_recover_session_fake_converges_at_restart_when_paired_but_stopped() -> None:
    client = FakeWahaClient()
    client.simulate_pair()
    client.session_status = "STOPPED"  # paired but not WORKING/SCAN_QR_CODE

    result = asyncio.run(client.recover_session())

    # start_session is a no-op for a paired (`me` set) session per the fake's
    # state machine, so the ladder escalates to restart, which brings a
    # paired session back to WORKING.
    assert result["stage"] == "restart"
    assert result["status"] == "WORKING"
    assert result["paired"] is True


def test_recover_session_fake_converges_at_logout_start_from_stuck_failed() -> None:
    """The exact live-fleet bug, reproduced deterministically: a session
    with dead stored credentials stays FAILED through start AND restart;
    only logout+start clears it — proving the ladder's full convergence
    path (not just its individual rungs) end to end."""
    client = FakeWahaClient()
    client.simulate_stuck_session()

    result = asyncio.run(client.recover_session())

    assert result == {
        "status": "SCAN_QR_CODE",
        "stage": "logout_start",
        "paired": False,
        "me": None,
    }
    assert client.credentials_dead is False  # logout cleared it
    assert client.start_count == 2  # rung 2 (no-op) + rung 4 (post-logout)
    assert client.restart_count == 1


def test_recover_session_fake_stuck_session_start_and_restart_are_no_ops() -> None:
    """Isolates the no-op behaviour simulate_stuck_session() drives: while
    credentials_dead, start_session/restart_session must NOT change status
    — only logout_session may."""
    client = FakeWahaClient()
    client.simulate_stuck_session(status="FAILED")

    asyncio.run(client.start_session())
    assert client.session_status == "FAILED"

    asyncio.run(client.restart_session())
    assert client.session_status == "FAILED"

    asyncio.run(client.logout_session())
    assert client.session_status == "SCAN_QR_CODE"
    assert client.me is None
    assert client.credentials_dead is False


def test_clear_resets_new_state() -> None:
    client = FakeWahaClient()
    asyncio.run(client.send_seen("c@c.us"))
    client.fake_chats_overview = [{"id": "c@c.us"}]

    client.clear()

    assert client.seen_calls == []
    assert client.fake_chats_overview == []

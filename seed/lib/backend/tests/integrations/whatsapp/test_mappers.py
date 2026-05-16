"""Mapper tests — 11 cases ported verbatim from
`whatsapp-google-scheduling/tests/test_waha_mappers.py` 2026-05-03.

Vocabulary translation: `app.services.waha` → `noctusai_lib.integrations.whatsapp`.
The legacy `Waha*` class aliases preserve sibling import shape.
"""

import pytest

from noctusai_lib.integrations.whatsapp import (
    WhatsAppIgnoredEvent,
    WhatsAppPayloadError,
    build_send_text_body,
    chat_id_for_phone,
    parse_waha_inbound_message,
    phone_from_chat_id,
    rewrite_vendor_media_url,
)


# ---- rewrite_vendor_media_url (SESSION-NOTES §4.3, workspace fedd4cf) ----


def test_rewrite_swaps_external_host_for_internal() -> None:
    out = rewrite_vendor_media_url(
        "http://localhost:3000/api/files/default/false_3EB0.oga",
        external_base_url="http://localhost:3000",
        internal_base_url="http://waha:3000",
    )
    assert out == "http://waha:3000/api/files/default/false_3EB0.oga"


def test_rewrite_keeps_path_query_fragment_verbatim() -> None:
    out = rewrite_vendor_media_url(
        "http://localhost:3000/api/files/x.jpg?token=abc#frag",
        external_base_url="http://localhost:3000",
        internal_base_url="http://waha:3000",
    )
    assert out == "http://waha:3000/api/files/x.jpg?token=abc#frag"


def test_rewrite_passes_external_cdn_url_unchanged() -> None:
    cdn = "https://cdn.example.com/media/abc.jpg"
    assert (
        rewrite_vendor_media_url(
            cdn,
            external_base_url="http://localhost:3000",
            internal_base_url="http://waha:3000",
        )
        == cdn
    )


def test_rewrite_noop_on_relative_or_empty_bases() -> None:
    assert (
        rewrite_vendor_media_url(
            "/api/files/x", external_base_url="http://localhost:3000",
            internal_base_url="http://waha:3000",
        )
        == "/api/files/x"
    )
    assert (
        rewrite_vendor_media_url(
            "http://localhost:3000/api/x", external_base_url="",
            internal_base_url="http://waha:3000",
        )
        == "http://localhost:3000/api/x"
    )


def test_parse_waha_payload_from_nested_event() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "message-1",
                "from": "5511999999999@c.us",
                "body": "Preciso de fotos para ONE0007 amanha de manha",
            },
        }
    )

    assert inbound.provider_message_id == "message-1"
    assert inbound.chat_id == "5511999999999@c.us"
    assert inbound.from_phone == "+5511999999999"
    assert inbound.text == "Preciso de fotos para ONE0007 amanha de manha"
    assert inbound.session == "default"


def test_parse_waha_payload_from_flat_event() -> None:
    inbound = parse_waha_inbound_message(
        {
            "id": {"_serialized": "serialized-message-id"},
            "chatId": "5511888888888@c.us",
            "text": "Reels ONE0008 terça a tarde",
        }
    )

    assert inbound.provider_message_id == "serialized-message-id"
    assert inbound.from_phone == "+5511888888888"
    assert inbound.text == "Reels ONE0008 terça a tarde"


def test_parse_waha_payload_extracts_pushname_from_top_level() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "m-1",
                "from": "5511992694172@c.us",
                "body": "oi",
                "notifyName": "Rapha NoctusAI",
            },
        }
    )

    assert inbound.from_name == "Rapha NoctusAI"


def test_parse_waha_payload_extracts_pushname_from_nested_data() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "m-2",
                "from": "5511992694172@c.us",
                "body": "oi",
                "_data": {"notifyName": "Rapha"},
            },
        }
    )

    assert inbound.from_name == "Rapha"


def test_parse_waha_payload_pushname_absent_returns_none() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {"id": "m-3", "from": "5511888888888@c.us", "body": "oi"},
        }
    )

    assert inbound.from_name is None


def test_ignores_non_message_events() -> None:
    with pytest.raises(WhatsAppIgnoredEvent):
        parse_waha_inbound_message(
            {
                "event": "session.status",
                "session": "default",
                "payload": {"status": "WORKING"},
            }
        )


def test_parse_waha_payload_with_audio_media() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "audio-1",
                "from": "5511999999999@c.us",
                "body": "",
                "hasMedia": True,
                "media": {
                    "url": "https://waha.example/files/audio-1.ogg",
                    "mimetype": "audio/ogg; codecs=opus",
                },
            },
        }
    )

    assert inbound.media is not None
    assert inbound.media.url == "https://waha.example/files/audio-1.ogg"
    assert inbound.media.mimetype.startswith("audio/")
    assert inbound.from_phone == "+5511999999999"


def test_parse_waha_payload_with_image_media() -> None:
    inbound = parse_waha_inbound_message(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "image-1",
                "from": "5511999999999@c.us",
                "body": "",
                "hasMedia": True,
                "media": {
                    "url": "https://waha.example/files/image-1.jpg",
                    "mimetype": "image/jpeg",
                },
            },
        }
    )

    assert inbound.media is not None
    assert inbound.media.mimetype == "image/jpeg"


def test_parse_waha_payload_rejects_message_with_no_text_and_no_media() -> None:
    with pytest.raises(WhatsAppPayloadError):
        parse_waha_inbound_message(
            {
                "event": "message",
                "session": "default",
                "payload": {
                    "id": "x",
                    "from": "5511999999999@c.us",
                    "body": "",
                },
            }
        )


def test_chat_id_for_phone_strips_plus_and_appends_c_us() -> None:
    assert chat_id_for_phone("+5511999999999") == "5511999999999@c.us"
    assert chat_id_for_phone("5511999999999") == "5511999999999@c.us"


def test_phone_from_chat_id_inverse() -> None:
    assert phone_from_chat_id("5511999999999@c.us") == "+5511999999999"
    assert phone_from_chat_id("+5511999999999@c.us") == "+5511999999999"


def test_build_send_text_body_returns_waha_send_text_shape() -> None:
    body = build_send_text_body(
        session="default",
        chat_id="5511999999999@c.us",
        text="Olá!",
    )

    assert body == {
        "session": "default",
        "chatId": "5511999999999@c.us",
        "text": "Olá!",
    }


def test_ignores_own_message_any_events() -> None:
    with pytest.raises(WhatsAppIgnoredEvent):
        parse_waha_inbound_message(
            {
                "event": "message.any",
                "session": "default",
                "payload": {
                    "id": "message-1",
                    "from": "5511999999999@c.us",
                    "fromMe": True,
                    "source": "api",
                    "body": "Mensagem enviada pela API",
                },
            }
        )

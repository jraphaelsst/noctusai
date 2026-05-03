"""Conversation mapper tests."""

import base64
from io import BytesIO

from noctusai_lib.domain.conversation.mappers import (
    audio_bytes_to_named_buffer,
    format_conversation_for_transcript,
    image_bytes_to_data_url,
    memory_to_chat_messages,
)


def test_memory_to_chat_messages_marks_outbound_as_assistant() -> None:
    memory = [
        {"direction": "inbound", "text": "oi", "timestamp": 1000},
        {"direction": "outbound", "text": "olá", "timestamp": 1010},
        {"direction": "inbound", "text": "tudo bem?", "timestamp": 1020},
    ]
    assert memory_to_chat_messages(memory) == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "olá"},
        {"role": "user", "content": "tudo bem?"},
    ]


def test_memory_to_chat_messages_drops_empty_text_items() -> None:
    memory = [
        {"direction": "inbound", "text": "real", "timestamp": 1000},
        {"direction": "inbound", "text": "", "timestamp": 1001},
        {"direction": "inbound", "timestamp": 1002},  # no text key
    ]
    assert memory_to_chat_messages(memory) == [{"role": "user", "content": "real"}]


def test_format_transcript_uses_default_labels() -> None:
    memory = [
        {"direction": "inbound", "text": "Hi"},
        {"direction": "outbound", "text": "Hello"},
    ]
    assert format_conversation_for_transcript(memory) == "USER: Hi\nASSISTANT: Hello"


def test_format_transcript_overrides_labels() -> None:
    memory = [
        {"direction": "inbound", "text": "oi"},
        {"direction": "outbound", "text": "olá"},
    ]
    transcript = format_conversation_for_transcript(
        memory, assistant_label="ASSISTENTE", user_label="CORRETOR"
    )
    assert transcript == "CORRETOR: oi\nASSISTENTE: olá"


def test_format_transcript_returns_marker_for_empty_memory() -> None:
    assert format_conversation_for_transcript([]) == "(empty conversation)"


def test_image_bytes_to_data_url_round_trips_via_base64() -> None:
    raw = b"\x89PNG\r\n\x1a\n"
    url = image_bytes_to_data_url(raw, "image/png")

    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == raw


def test_audio_bytes_to_named_buffer_sets_name_attribute() -> None:
    buffer = audio_bytes_to_named_buffer(b"OGGdata", "voice.ogg")
    assert isinstance(buffer, BytesIO)
    assert buffer.name == "voice.ogg"
    assert buffer.read() == b"OGGdata"

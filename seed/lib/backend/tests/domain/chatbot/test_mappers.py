"""Chatbot mapper tests."""

from noctusai_lib.domain.chatbot.mappers import (
    format_conversation_for_transcript,
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

"""Pure-function translators between the buffer's memory shape and
LLM/transcript shapes.

Ported from
`whatsapp-google-scheduling/app/services/openai/mappers.py` 2026-05-03
via `projects/whatsapp-seed-absorption/` Phase 5.

Sibling's `user_context_to_chat_system_block` and `_summary_system_block`
are NOT lifted — they're product-specific (pt-BR real-estate framing
per project §7 Q3 "system prompts are product-specific"). Consumers
build their own system-prompt strings.

LLM-input helpers (`image_bytes_to_data_url`, `audio_bytes_to_named_buffer`)
moved to `noctusai_lib.integrations.llm.inputs` — they're vendor-shape
helpers, not chatbot domain concerns.
"""

from __future__ import annotations

from typing import Any


def memory_to_chat_messages(memory: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert buffer memory (list of dicts with `text` + `direction`) to
    OpenAI chat-completion messages. Outbound = assistant; everything else
    (default `inbound`) = user. Items with empty/missing `text` are dropped.
    """
    messages: list[dict[str, str]] = []
    for item in memory:
        text = item.get("text")
        if not text:
            continue
        role = "assistant" if item.get("direction") == "outbound" else "user"
        messages.append({"role": role, "content": text})
    return messages


def format_conversation_for_transcript(
    memory: list[dict[str, Any]],
    *,
    assistant_label: str = "ASSISTANT",
    user_label: str = "USER",
    empty_marker: str = "(empty conversation)",
) -> str:
    """Render the conversation as a labeled transcript (one line per message).

    Defaults to English labels; override for product-specific framing
    (sibling used `ASSISTENTE` / `CORRETOR`)."""
    lines: list[str] = []
    for item in memory:
        text = item.get("text")
        if not text:
            continue
        speaker = assistant_label if item.get("direction") == "outbound" else user_label
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines) if lines else empty_marker



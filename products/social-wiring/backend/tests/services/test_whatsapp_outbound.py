"""Unit tests for the WhatsApp paragraph-split outbound helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.whatsapp_outbound import send_paragraphs, split_for_whatsapp


def test_split_returns_empty_for_empty_input():
    assert split_for_whatsapp("") == []
    assert split_for_whatsapp("   ") == []


def test_split_returns_singleton_for_single_paragraph():
    assert split_for_whatsapp("hello") == ["hello"]


def test_split_breaks_on_double_newline():
    text = "oi\n\ntudo bem?\n\nsim"
    assert split_for_whatsapp(text) == ["oi", "tudo bem?", "sim"]


def test_split_preserves_single_newlines_within_paragraph():
    """A single \\n inside a paragraph is a soft-wrap; WhatsApp renders
    it. Only \\n\\n or more is a paragraph break."""
    text = "linha 1\nlinha 2 (same bubble)\n\noutro bubble"
    parts = split_for_whatsapp(text)
    assert parts == ["linha 1\nlinha 2 (same bubble)", "outro bubble"]


def test_split_collapses_extra_blank_lines():
    """\\n\\n\\n\\n should still produce one break, not three empty
    bubbles."""
    text = "a\n\n\n\nb"
    assert split_for_whatsapp(text) == ["a", "b"]


def test_split_strips_each_paragraph():
    text = "  hello  \n\n  world  "
    assert split_for_whatsapp(text) == ["hello", "world"]


def test_split_honors_toggle_off():
    """When the paragraph-split toggle is False, return a single-element
    list with the original text trimmed — caller loops unconditionally.
    Injected via the `enabled` DI seam (no settings-singleton mutation)."""
    result = split_for_whatsapp("a\n\nb\n\nc", enabled=False)
    assert result == ["a\n\nb\n\nc"]


@pytest.mark.asyncio
async def test_send_paragraphs_sends_one_per_part():
    intake = AsyncMock()
    intake.send_reply = AsyncMock()
    sent = await send_paragraphs(
        intake=intake, sender="+5511999999999@c.us", text="a\n\nb\n\nc",
        split=True, delay_seconds=0.0,
    )
    assert sent == 3
    assert intake.send_reply.await_count == 3
    # Each send got its own paragraph as the second positional arg
    calls = [c.args[1] for c in intake.send_reply.await_args_list]
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_send_paragraphs_continues_after_a_send_failure():
    """One failed paragraph send must NOT block subsequent ones —
    partial delivery beats no delivery for chatbot replies."""
    intake = AsyncMock()
    intake.send_reply = AsyncMock(
        side_effect=[Exception("WAHA fail"), None, None]
    )
    sent = await send_paragraphs(
        intake=intake, sender="+5511999999999@c.us", text="a\n\nb\n\nc",
        split=True, delay_seconds=0.0,
    )
    assert sent == 2  # one failed, two succeeded
    assert intake.send_reply.await_count == 3  # all attempted


@pytest.mark.asyncio
async def test_send_paragraphs_returns_zero_for_empty_text():
    intake = AsyncMock()
    sent = await send_paragraphs(
        intake=intake, sender="+5511999999999@c.us", text=""
    )
    assert sent == 0
    intake.send_reply.assert_not_called()

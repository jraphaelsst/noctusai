"""Tests for the channel-neutral reply-delivery primitive.

Covers `split_reply` (pure paragraph split) + `send_reply_parts` /
`send_reply_parts_sync` (sequential emit with partial-delivery resilience +
inter-message delay). Mirrors the product-side cases that lived in
social-wiring's `tests/services/test_whatsapp_outbound.py` before the lift,
plus the sync sibling the documented wiring recipe uses.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noctusai_lib.domain.chatbot import (
    send_reply_parts,
    send_reply_parts_sync,
    split_reply,
)


# --- split_reply (pure) -------------------------------------------------

def test_split_empty_inputs_return_empty_list() -> None:
    assert split_reply("") == []
    assert split_reply("   ") == []
    assert split_reply("\n\n  \n") == []


def test_split_single_paragraph_returns_singleton() -> None:
    assert split_reply("hello") == ["hello"]


def test_split_breaks_on_blank_line() -> None:
    assert split_reply("oi\n\ntudo bem?\n\nsim") == ["oi", "tudo bem?", "sim"]


def test_split_preserves_single_newline_softwrap() -> None:
    text = "linha 1\nlinha 2 (same bubble)\n\noutro bubble"
    assert split_reply(text) == ["linha 1\nlinha 2 (same bubble)", "outro bubble"]


def test_split_collapses_extra_blank_lines() -> None:
    assert split_reply("a\n\n\n\nb") == ["a", "b"]


def test_split_strips_each_part() -> None:
    assert split_reply("  hello  \n\n  world  ") == ["hello", "world"]


def test_split_disabled_returns_single_trimmed_entry() -> None:
    assert split_reply("a\n\nb\n\nc", enabled=False) == ["a\n\nb\n\nc"]
    assert split_reply("  x  ", enabled=False) == ["x"]
    assert split_reply("", enabled=False) == []


# --- send_reply_parts (async) ------------------------------------------

@pytest.mark.asyncio
async def test_send_parts_one_per_part_in_order() -> None:
    send_one = AsyncMock()
    sent = await send_reply_parts("a\n\nb\n\nc", send_one, delay_seconds=0.0)
    assert sent == 3
    assert send_one.await_count == 3
    assert [c.args[0] for c in send_one.await_args_list] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_send_parts_continues_after_failure() -> None:
    send_one = AsyncMock(side_effect=[Exception("transport fail"), None, None])
    sent = await send_reply_parts("a\n\nb\n\nc", send_one, delay_seconds=0.0)
    assert sent == 2  # one failed, two succeeded
    assert send_one.await_count == 3  # all attempted


@pytest.mark.asyncio
async def test_send_parts_empty_text_sends_nothing() -> None:
    send_one = AsyncMock()
    assert await send_reply_parts("", send_one) == 0
    send_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_parts_delays_between_but_not_after_last() -> None:
    send_one = AsyncMock()
    with patch(
        "noctusai_lib.domain.chatbot.delivery.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        await send_reply_parts("a\n\nb\n\nc", send_one, delay_seconds=0.6)
    assert sleep.await_count == 2  # 3 parts → 2 gaps, none after the last
    assert all(c.args[0] == 0.6 for c in sleep.await_args_list)


@pytest.mark.asyncio
async def test_send_parts_split_disabled_sends_one_message() -> None:
    send_one = AsyncMock()
    sent = await send_reply_parts(
        "a\n\nb", send_one, split=False, delay_seconds=0.0
    )
    assert sent == 1
    assert send_one.await_args_list[0].args[0] == "a\n\nb"


# --- send_reply_parts_sync ---------------------------------------------

def test_send_parts_sync_one_per_part_in_order() -> None:
    send_one = MagicMock()
    sent = send_reply_parts_sync("a\n\nb\n\nc", send_one, delay_seconds=0.0)
    assert sent == 3
    assert [c.args[0] for c in send_one.call_args_list] == ["a", "b", "c"]


def test_send_parts_sync_continues_after_failure() -> None:
    send_one = MagicMock(side_effect=[Exception("fail"), None, None])
    sent = send_reply_parts_sync("a\n\nb\n\nc", send_one, delay_seconds=0.0)
    assert sent == 2
    assert send_one.call_count == 3


def test_send_parts_sync_delays_between_but_not_after_last() -> None:
    send_one = MagicMock()
    with patch("noctusai_lib.domain.chatbot.delivery.time.sleep") as sleep:
        send_reply_parts_sync("a\n\nb\n\nc", send_one, delay_seconds=0.6)
    assert sleep.call_count == 2
    assert all(c.args[0] == 0.6 for c in sleep.call_args_list)

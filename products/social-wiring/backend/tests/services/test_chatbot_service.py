"""Unit tests for the generalized chatbot service + file registry.

The OpenAI tool-calling loop is exercised via integration smoke (real
API call) in ``scripts/smoke_real_apis.py``; here we cover the parts
that don't need a live OpenAI key:

- Memory key shape (web session vs WhatsApp phone JID)
- History load/reset round-trip
- File registry register/get/forget round-trip
- ``prepare_upload_from_file_request`` validation (invalid code,
  missing file_id, file_not_found)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.services.chatbot_service import ChatbotService, MEMORY_PREFIX
from app.services.whatsapp_intake_service import WhatsAppIntakeService


class _FakeRedis:
    """Minimal in-memory stand-in for the ``redis.Redis`` API we use."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    # ── strings ──
    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, value: str, ex: int | None = None):  # noqa: ARG002
        self.kv[key] = value

    def delete(self, key: str):
        self.kv.pop(key, None)
        self.lists.pop(key, None)

    def expire(self, key: str, seconds: int):  # noqa: ARG002
        return True

    def ping(self):
        return True

    # ── lists ──
    def rpush(self, key: str, value: str):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key: str, start: int, end: int):
        items = self.lists.get(key, [])
        # Redis end is inclusive; mimic that
        return items[start : end + 1 if end != -1 else None]

    def ltrim(self, key: str, start: int, end: int):
        items = self.lists.get(key, [])
        if end == -1:
            self.lists[key] = items[start:]
        else:
            self.lists[key] = items[start : end + 1]


@pytest.fixture
def fake_redis():
    return _FakeRedis()


@pytest.fixture
def intake(fake_redis):
    return WhatsAppIntakeService(
        waha_base_url="",
        waha_api_key="",
        waha_session="default",
        redis_client=fake_redis,
        authorized_numbers=["+5511974693365"],
        crm_service=None,
        admin_supabase=MagicMock(),
        youtube_service=MagicMock(),
        upload_dir=Path("/tmp"),
        org_id=UUID("00000000-0000-4000-8000-000000000001"),
    )


class TestChatbotMemoryKey:
    def test_web_session_keeps_prefix(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            session_id="web:abc123",
            model="gpt-4o-mini",
            api_key="noop",
        )
        assert bot._memory_key() == f"{MEMORY_PREFIX}web:abc123"

    def test_whatsapp_phone_strips_jid_suffix(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            session_id="5511974693365@c.us",
            model="gpt-4o-mini",
            api_key="noop",
        )
        assert bot._memory_key() == f"{MEMORY_PREFIX}5511974693365"

    def test_legacy_phone_kwarg_still_works(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            phone="5511974693365@c.us",
            model="gpt-4o-mini",
            api_key="noop",
        )
        assert bot._memory_key().endswith("5511974693365")

    def test_session_id_required(self, fake_redis, intake):
        with pytest.raises(ValueError):
            ChatbotService(
                redis_client=fake_redis,
                intake_service=intake,
                api_key="noop",
            )


class TestChatbotHistory:
    def test_load_empty_history(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            session_id="web:abc",
            api_key="noop",
        )
        assert bot.load_history() == []

    def test_history_round_trip(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            session_id="web:abc",
            api_key="noop",
        )
        bot._append_memory("inbound", "ola")
        bot._append_memory("outbound", "oi")
        history = bot.load_history()
        assert history == [
            {"role": "user", "content": "ola"},
            {"role": "assistant", "content": "oi"},
        ]

    def test_reset_clears_memory(self, fake_redis, intake):
        bot = ChatbotService(
            redis_client=fake_redis,
            intake_service=intake,
            session_id="web:abc",
            api_key="noop",
        )
        bot._append_memory("inbound", "ola")
        bot.reset_history()
        assert bot.load_history() == []


class TestFileRegistry:
    def test_register_get_forget(self, intake):
        intake.register_uploaded_file(
            file_id="stg-aaa",
            local_path="/tmp/uploads/staging-aaa__video.mp4",
            file_name="video.mp4",
            file_size_bytes=245_000_000,
        )
        info = intake.get_uploaded_file("stg-aaa")
        assert info is not None
        assert info["file_name"] == "video.mp4"
        assert info["file_size_bytes"] == 245_000_000
        intake.forget_uploaded_file("stg-aaa")
        assert intake.get_uploaded_file("stg-aaa") is None

    def test_get_missing_returns_none(self, intake):
        assert intake.get_uploaded_file("stg-missing") is None


class TestPrepareUploadFromFileValidation:
    @pytest.mark.asyncio
    async def test_invalid_product_code(self, intake):
        result = await intake.prepare_upload_from_file_request(
            "web:test",
            product_code="bad",
            file_id="stg-aaa",
        )
        assert result == {
            "ok": False,
            "error": "invalid_product_code",
            "product_code": "BAD",
        }

    @pytest.mark.asyncio
    async def test_missing_file_id(self, intake):
        result = await intake.prepare_upload_from_file_request(
            "web:test",
            product_code="ONE5555",
            file_id="",
        )
        assert result == {"ok": False, "error": "missing_file_id"}

    @pytest.mark.asyncio
    async def test_file_not_found(self, intake):
        result = await intake.prepare_upload_from_file_request(
            "web:test",
            product_code="ONE5555",
            file_id="stg-missing",
        )
        assert result == {
            "ok": False,
            "error": "file_not_found",
            "file_id": "stg-missing",
        }

    @pytest.mark.asyncio
    async def test_happy_path_no_crm(self, intake):
        intake.register_uploaded_file(
            file_id="stg-aaa",
            local_path="/tmp/uploads/staging-aaa__video.mp4",
            file_name="video.mp4",
            file_size_bytes=100,
        )
        result = await intake.prepare_upload_from_file_request(
            "web:test",
            product_code="ONE5555",
            file_id="stg-aaa",
            manual_title="Manual title",
        )
        assert result["ok"] is True
        assert result["state"] == "awaiting_confirmation"
        assert result["file_id"] == "stg-aaa"
        assert result["file_name"] == "video.mp4"
        assert result["title"] == "Manual title"

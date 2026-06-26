"""Unit tests for WhatsAppIntakeService auth + chat-gate logic (migration 016).

Tests are deliberately thin: they instantiate the service with a stub Redis
client (never pings) and assert only the is_authorized / is_chat_bound / _strip_jid_suffix
logic.  No network, no DB, no WAHA calls.

Coverage:
  - _strip_jid_suffix — all three JID suffix forms.
  - is_authorized with empty authorized_numbers (allow-all semantic).
  - is_authorized with a non-empty list (existing whitelist logic preserved).
  - is_chat_bound with empty bound_chats (all chats).
  - is_chat_bound with a non-empty list (exact + normalized matching).
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.whatsapp_intake_service import WhatsAppIntakeService


def _make_intake(
    *,
    authorized_numbers: list[str] | None = None,
    bound_chats: list[dict] | None = None,
) -> WhatsAppIntakeService:
    """Construct a WhatsAppIntakeService with stubs for every non-auth dep."""
    redis_stub = MagicMock()
    redis_stub.get.return_value = None
    redis_stub.ping.return_value = True
    return WhatsAppIntakeService(
        waha_base_url="https://waha.example.com",
        waha_api_key="test-key",
        waha_session="default",
        redis_client=redis_stub,
        authorized_numbers=authorized_numbers or [],
        crm_service=None,
        admin_supabase=MagicMock(),
        youtube_service=None,
        upload_dir="/tmp/uploads",
        org_id=uuid4(),
        connection_id=uuid4(),
        bound_chats=bound_chats,
    )


# ─── _strip_jid_suffix ───────────────────────────────────────────────────────

class TestStripJidSuffix:
    def test_strips_c_us(self):
        assert WhatsAppIntakeService._strip_jid_suffix("5511999887766@c.us") == "5511999887766"

    def test_strips_s_whatsapp_net(self):
        assert WhatsAppIntakeService._strip_jid_suffix("5511999887766@s.whatsapp.net") == "5511999887766"

    def test_strips_lid(self):
        assert WhatsAppIntakeService._strip_jid_suffix("33613018058989@lid") == "33613018058989"

    def test_bare_digits_unchanged(self):
        assert WhatsAppIntakeService._strip_jid_suffix("5511999887766") == "5511999887766"


# ─── is_authorized ───────────────────────────────────────────────────────────

class TestIsAuthorized:
    def test_empty_authorized_numbers_allows_all(self):
        """Per-connection default: empty list = allow all senders."""
        svc = _make_intake(authorized_numbers=[])
        assert svc.is_authorized("5511999887766@c.us") is True
        assert svc.is_authorized("+5521988776655") is True
        assert svc.is_authorized("random@lid") is True
        assert svc.is_authorized("") is True  # even empty sender passes

    def test_non_empty_whitelist_allows_listed_c_us(self):
        svc = _make_intake(authorized_numbers=["+5511999887766"])
        assert svc.is_authorized("5511999887766@c.us") is True

    def test_non_empty_whitelist_allows_listed_s_whatsapp_net(self):
        svc = _make_intake(authorized_numbers=["+5511999887766"])
        assert svc.is_authorized("5511999887766@s.whatsapp.net") is True

    def test_non_empty_whitelist_blocks_unlisted(self):
        svc = _make_intake(authorized_numbers=["+5511999887766"])
        assert svc.is_authorized("5521988776655@c.us") is False

    def test_non_empty_whitelist_allows_direct_plus_form(self):
        svc = _make_intake(authorized_numbers=["+5511999887766"])
        assert svc.is_authorized("+5511999887766") is True

    def test_lid_literal_hit(self):
        svc = _make_intake(authorized_numbers=["33613018058989@lid"])
        assert svc.is_authorized("33613018058989@lid") is True

    def test_empty_sender_denied_when_whitelist_set(self):
        svc = _make_intake(authorized_numbers=["+5511999887766"])
        assert svc.is_authorized("") is False

    def test_empty_sender_allowed_when_allow_all(self):
        svc = _make_intake(authorized_numbers=[])
        assert svc.is_authorized("") is True


# ─── is_chat_bound ───────────────────────────────────────────────────────────

class TestIsChatBound:
    def test_no_bound_chats_allows_everything(self):
        """Empty bound_chats list (or None) = listen to all chats."""
        svc = _make_intake(bound_chats=[])
        assert svc.is_chat_bound("5511999887766@c.us") is True
        assert svc.is_chat_bound("12027986300@g.us") is True
        assert svc.is_chat_bound("") is True

    def test_none_bound_chats_allows_everything(self):
        svc = _make_intake(bound_chats=None)
        assert svc.is_chat_bound("5511999887766@c.us") is True

    def test_exact_raw_jid_matches(self):
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766@c.us", "label": ""}])
        assert svc.is_chat_bound("5511999887766@c.us") is True

    def test_normalized_bare_digits_match_when_config_has_full_jid(self):
        """Operator configured full JID; WAHA sends bare digits — must match."""
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766@c.us", "label": ""}])
        assert svc.is_chat_bound("5511999887766") is True

    def test_full_jid_matches_when_config_has_bare_digits(self):
        """Operator configured bare digits; WAHA sends full JID — must match."""
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766", "label": ""}])
        assert svc.is_chat_bound("5511999887766@c.us") is True

    def test_unlisted_chat_blocked(self):
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766@c.us", "label": ""}])
        assert svc.is_chat_bound("5521988776655@c.us") is False

    def test_empty_chat_id_always_passes(self):
        """Empty chat_id is non-meaningful; the gate lets it through."""
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766@c.us", "label": ""}])
        assert svc.is_chat_bound("") is True

    def test_multiple_bound_chats_any_match_passes(self):
        svc = _make_intake(bound_chats=[
            {"chat_id": "5511999887766@c.us", "label": "Vendas"},
            {"chat_id": "5521988776655@c.us", "label": "Suporte"},
        ])
        assert svc.is_chat_bound("5511999887766@c.us") is True
        assert svc.is_chat_bound("5521988776655@c.us") is True
        assert svc.is_chat_bound("5541977665544@c.us") is False

    def test_s_whatsapp_net_suffix_normalized(self):
        svc = _make_intake(bound_chats=[{"chat_id": "5511999887766@s.whatsapp.net", "label": ""}])
        assert svc.is_chat_bound("5511999887766@c.us") is True  # strip → same digits

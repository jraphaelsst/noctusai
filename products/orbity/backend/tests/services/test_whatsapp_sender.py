"""RealWhatsAppSender + org WAHA client resolution (community-style, refuse-not-fake)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.whatsapp import FakeWahaClient, WahaClient
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_lib.testing import MockSupabaseClient

from app.services.whatsapp_sender import (
    RealWhatsAppSender,
    WhatsAppNotConnected,
    WhatsAppSendError,
    chat_id_for,
    resolve_org_waha_client,
)

ORG = str(uuid.uuid4())


class PinnedClient:
    """Stand-in for the prod schema-pinned admin client: `.schema(x)` keeps the
    same seeded tables (the bare MockSupabaseClient.schema() starts empty)."""

    def __init__(self, inner):
        self._inner = inner

    def schema(self, _name):
        return self

    def table(self, name):
        return self._inner.table(name)


def _settings(**over):
    base = dict(
        encryption_key="", waha_base_url="", waha_api_key="", waha_session="default",
        waha_external_base_url="", whatsapp_allow_fake=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestChatId:
    def test_digits_plus_c_us(self):
        assert chat_id_for("(11) 99999-8888") == "5511999998888@c.us"

    def test_already_normalised(self):
        assert chat_id_for("5511999998888") == "5511999998888@c.us"

    def test_junk_is_none(self):
        assert chat_id_for("abc") is None
        assert chat_id_for(None) is None


class TestResolveOrgClient:
    def test_unconfigured_org_refuses_with_none(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("whatsapp_connections", [])
        assert resolve_org_waha_client(org_id=ORG, admin_client=db, settings=_settings()) is None

    def test_fake_only_under_explicit_allow_fake(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("whatsapp_connections", [])
        client = resolve_org_waha_client(
            org_id=ORG, admin_client=db, settings=_settings(whatsapp_allow_fake=True)
        )
        assert isinstance(client, FakeWahaClient)

    def test_static_settings_fallback_builds_real_client(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("whatsapp_connections", [])
        client = resolve_org_waha_client(
            org_id=ORG, admin_client=db,
            settings=_settings(waha_base_url="http://waha:3000", waha_api_key="k", waha_session="s1"),
        )
        assert isinstance(client, WahaClient) and client.session == "s1"

    def test_saved_connection_wins_over_static_and_decrypts_key(self):
        key = Fernet.generate_key().decode()
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("whatsapp_connections", [{
            "id": str(uuid.uuid4()), "org_id": ORG, "user_id": str(uuid.uuid4()),
            "label": "Linha 1", "base_url": "http://org-waha:3000", "session_name": "org-session",
            "encrypted_api_key": Fernet(key.encode()).encrypt(b"secret-key").decode(),
            "webhook_url": "http://x/hook", "webhook_token": "tok",
            "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-01T00:00:00+00:00",
        }])
        client = resolve_org_waha_client(
            org_id=uuid.UUID(ORG), admin_client=PinnedClient(db),
            settings=_settings(encryption_key=key, waha_base_url="http://static:3000"),
        )
        assert isinstance(client, WahaClient) and client.session == "org-session"
        assert "org-waha" in str(client.base_url)

    def test_missing_encryption_key_ignores_saved_connections_without_crashing(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("whatsapp_connections", [])
        # encryption_key "" => EncryptionNotConfigured handled, falls to static (empty) => None
        assert resolve_org_waha_client(org_id=ORG, admin_client=db, settings=_settings()) is None


class TestRealWhatsAppSender:
    def _sender(self, client):
        return RealWhatsAppSender(
            lambda: MockSupabaseClient(schema="orbity"), _settings(),
            resolve_client=lambda **kw: client,
        )

    def test_sends_text_to_c_us_chat_id(self):
        waha = FakeWahaClient()
        self._sender(waha).send("(11) 99999-8888", "Olá!", ORG)
        assert waha.sent_messages[0]["chatId"] == "5511999998888@c.us"
        assert waha.sent_messages[0]["text"] == "Olá!"

    def test_unconfigured_org_raises_not_connected_never_fake_success(self):
        with pytest.raises(WhatsAppNotConnected) as exc:
            self._sender(None).send("5511999998888", "Oi", ORG)
        assert "WhatsApp não conectado" in str(exc.value)

    def test_invalid_phone_raises_send_error(self):
        with pytest.raises(WhatsAppSendError):
            self._sender(FakeWahaClient()).send("abc", "Oi", ORG)

    def test_transport_failure_maps_to_ptbr_error_without_leaking_details(self):
        class Boom:
            def send_text_to_phone_sync(self, phone, text):
                err = RuntimeError("http://secret-host/api?apiKey=ZZZ")
                err.response = SimpleNamespace(status_code=502)
                raise err

        with pytest.raises(WhatsAppSendError) as exc:
            self._sender(Boom()).send("5511999998888", "Oi", ORG)
        assert "HTTP 502" in str(exc.value) and "secret" not in str(exc.value)

    def test_resolves_ninth_digit_variant_without_rewriting_input(self):
        waha = FakeWahaClient()
        waha.registered_numbers = {"551199998888"}
        self._sender(waha).send("5511999998888", "Oi", ORG)
        assert waha.sent_messages[0]["chatId"] == "551199998888@c.us"

    def test_number_not_on_whatsapp_maps_to_ptbr_error(self):
        waha = FakeWahaClient()
        waha.registered_numbers = set()
        with pytest.raises(WhatsAppSendError) as exc:
            self._sender(waha).send("5511999998888", "Oi", ORG)
        assert "não está no WhatsApp" in str(exc.value) and "9º dígito" in str(exc.value)

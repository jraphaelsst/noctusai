"""Tests for `app.dependencies.resolve_community_waha_client` — Slice C
(user decision 2026-09-17): prefers the org's stored WAHA connection
row over the static `community_waha_*` settings.

`admin_client` is the DI seam (`KB § PATTERNS/backend/di-test-seam.md`)
`resolve_community_waha_client` exposes — a `MockSupabaseClient` passed
directly, never a patch of `get_admin_client` itself.
"""
from __future__ import annotations

from uuid import uuid4

from cryptography.fernet import Fernet
from noctusai_lib.integrations.whatsapp import FakeWahaClient, WahaClient
from noctusai_lib.testing import MockSupabaseClient

from app.config import settings
from app.dependencies import resolve_community_waha_client

ORG_ID = uuid4()


def _connection_row(*, fernet: Fernet, base_url="https://waha.community.example", api_key="stored-key"):
    return {
        "id": str(uuid4()),
        "org_id": str(ORG_ID),
        "user_id": "00000000-0000-0000-0000-000000000001",
        "label": "linha 1",
        "base_url": base_url,
        "session_name": "default",
        "encrypted_api_key": fernet.encrypt(api_key.encode("utf-8")).decode("ascii"),
        "webhook_url": None,
        "webhook_token": "tok-1",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def test_falls_back_to_static_settings_when_no_connection_stored(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())  # self-patch-ok: configuration value, not a guard
    # NOTE: `build_whatsapp_connection_store`'s internal `_table()` calls
    # `client.schema(schema)` on every read, and `MockSupabaseClient.
    # schema(...)` constructs a FRESH instance each time (dropping any
    # `set_table_data`-seeded builder cache) — so the seed data must flow
    # through the constructor's `data=` list (propagated via `self._data`
    # to every scoped child), never `set_table_data` after construction.
    mock_sb = MockSupabaseClient(data=[])

    client = resolve_community_waha_client(org_id=ORG_ID, admin_client=mock_sb)
    assert isinstance(client, FakeWahaClient)  # settings.community_waha_base_url is "" in tests


def test_falls_back_when_encryption_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", "")  # self-patch-ok: configuration value (unset -> EncryptionNotConfigured), not a guard
    mock_sb = MockSupabaseClient()

    client = resolve_community_waha_client(org_id=ORG_ID, admin_client=mock_sb)
    assert isinstance(client, FakeWahaClient)


def test_prefers_the_orgs_stored_connection_row(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "encryption_key", key.decode())  # self-patch-ok: configuration value, not a guard
    fernet = Fernet(key)

    mock_sb = MockSupabaseClient(
        data=[_connection_row(fernet=fernet, base_url="https://waha.community.example", api_key="stored-key")],
    )

    client = resolve_community_waha_client(org_id=ORG_ID, admin_client=mock_sb)
    assert isinstance(client, WahaClient)
    assert client.base_url == "https://waha.community.example"
    assert client.api_key == "stored-key"
    assert client.session == "default"


def test_other_orgs_connection_row_is_invisible(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "encryption_key", key.decode())  # self-patch-ok: configuration value, not a guard
    fernet = Fernet(key)

    other_org_row = _connection_row(fernet=fernet)
    other_org_row["org_id"] = str(uuid4())
    mock_sb = MockSupabaseClient(data=[other_org_row])

    client = resolve_community_waha_client(org_id=ORG_ID, admin_client=mock_sb)
    assert isinstance(client, FakeWahaClient)

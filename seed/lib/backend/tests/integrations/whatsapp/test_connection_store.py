"""Tests for `noctusai_lib.integrations.whatsapp.connection_store`.

The lifted (`community uses social-wiring's mechanisms`, Slice A)
multi-session, org-scoped WAHA connection store. Exercises CRUD against
a faithful in-test Supabase query-builder double supporting
`.schema(...).table(...)` (the store's real access pattern) — NOT a
monkeypatch of our own code, an injected external-substrate stand-in
mirroring `seed/lib/backend/tests/test_token_store.py`'s own double.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.security.api_keys import EncryptionNotConfigured
from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.integrations.whatsapp.connection_store import (
    WhatsAppConnectionStore,
    WhatsAppConnectionStoreError,
    build_whatsapp_connection_store,
    resolve_by_webhook_token,
    whatsapp_connections_table_ddl,
)


# ---------------------------------------------------------------------------
# Minimal faithful Supabase substrate double (external IO stand-in)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())

    def execute(self):
        if self._op == "select":
            return _Resp([dict(r) for r in self._rows if self._matches(r)])
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", "2026-09-17T00:00:00+00:00")
            row.setdefault("updated_at", "2026-09-17T00:00:00+00:00")
            self._rows.append(row)
            return _Resp([row])
        if self._op == "update":
            matched = [r for r in self._rows if self._matches(r)]
            for row in matched:
                row.update(self._payload)
            return _Resp([dict(r) for r in matched])
        if self._op == "delete":
            removed = [r for r in self._rows if self._matches(r)]
            self._rows[:] = [r for r in self._rows if not self._matches(r)]
            return _Resp([dict(r) for r in removed])
        return _Resp([])


class _SchemaHandle:
    def __init__(self, tables: dict[str, list]):
        self._tables = tables

    def table(self, name):
        rows = self._tables.setdefault(name, [])
        return _Query(rows)


class _FakeSupabase:
    def __init__(self):
        self._schemas: dict[str, dict[str, list]] = {}

    def schema(self, name):
        tables = self._schemas.setdefault(name, {})
        return _SchemaHandle(tables)


ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
USER_A = "33333333-3333-3333-3333-333333333333"


def _store(client=None, **kw) -> WhatsAppConnectionStore:
    key = generate_key().decode()
    client = client or _FakeSupabase()
    return build_whatsapp_connection_store(
        client, encryption_key=key, schema="social_wiring", **kw
    )


class TestBuildWhatsAppConnectionStore:
    def test_missing_key_raises_encryption_not_configured(self):
        with pytest.raises(EncryptionNotConfigured):
            build_whatsapp_connection_store(
                _FakeSupabase(), encryption_key=None, schema="social_wiring"
            )


class TestCreateConnection:
    def test_create_encrypts_api_key_and_returns_record(self):
        store = _store()
        record = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="Atendimento",
            base_url="https://waha.example.com", api_key="secret-key",
            webhook_token="tok-1",
        )
        assert record.label == "Atendimento"
        assert record.base_url == "https://waha.example.com"
        assert record.session_name == "default"
        assert record.api_key is None  # never on the create-return path
        assert record.webhook_token == "tok-1"

    def test_base_url_trailing_slash_stripped(self):
        store = _store()
        record = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com/",
            api_key="k",
        )
        assert record.base_url == "https://x.com"

    def test_extra_fields_written_but_not_surfaced_without_extension(self):
        store = _store()
        record = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com",
            api_key="k", extra_fields={"marca_id": "some-marca"},
        )
        assert record.extra == {}  # no record_extension configured


class TestListAndGetConnection:
    def test_list_scoped_to_org(self):
        store = _store()
        store.create_connection(org_id=ORG_A, user_id=USER_A, label="A", base_url="https://x.com", api_key="k")
        store.create_connection(org_id=ORG_B, user_id=USER_A, label="B", base_url="https://x.com", api_key="k")
        records = store.list_connections(org_id=ORG_A)
        assert len(records) == 1
        assert records[0].label == "A"

    def test_get_connection_decrypt_false_hides_key(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="A", base_url="https://x.com", api_key="secret")
        fetched = store.get_connection(connection_id=created.id, org_id=ORG_A, decrypt=False)
        assert fetched.api_key is None

    def test_get_connection_decrypt_true_reveals_key(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="A", base_url="https://x.com", api_key="secret")
        fetched = store.get_connection(connection_id=created.id, org_id=ORG_A, decrypt=True)
        assert fetched.api_key == "secret"

    def test_get_connection_wrong_org_returns_none(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="A", base_url="https://x.com", api_key="secret")
        assert store.get_connection(connection_id=created.id, org_id=ORG_B) is None

    def test_get_connection_missing_returns_none(self):
        store = _store()
        assert store.get_connection(connection_id="nonexistent", org_id=ORG_A) is None


class TestUpdateConnection:
    def test_update_label(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="Old", base_url="https://x.com", api_key="k")
        updated = store.update_connection(connection_id=created.id, org_id=ORG_A, label="New")
        assert updated.label == "New"

    def test_update_webhook_url_unset_keeps_current(self):
        store = _store()
        created = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k",
            webhook_url="https://old-hook",
        )
        updated = store.update_connection(connection_id=created.id, org_id=ORG_A, label="L2")
        assert updated.webhook_url == "https://old-hook"

    def test_update_webhook_url_explicit_none_clears(self):
        store = _store()
        created = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k",
            webhook_url="https://old-hook",
        )
        updated = store.update_connection(connection_id=created.id, org_id=ORG_A, webhook_url=None)
        assert updated.webhook_url is None

    def test_update_missing_connection_returns_none(self):
        store = _store()
        assert store.update_connection(connection_id="nope", org_id=ORG_A, label="x") is None

    def test_update_api_key_re_encrypts(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="old-key")
        store.update_connection(connection_id=created.id, org_id=ORG_A, api_key="new-key")
        fetched = store.get_connection(connection_id=created.id, org_id=ORG_A, decrypt=True)
        assert fetched.api_key == "new-key"


class TestDeleteConnection:
    def test_delete_returns_true_then_false(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k")
        assert store.delete_connection(connection_id=created.id, org_id=ORG_A) is True
        assert store.delete_connection(connection_id=created.id, org_id=ORG_A) is False

    def test_delete_wrong_org_is_noop(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k")
        assert store.delete_connection(connection_id=created.id, org_id=ORG_B) is False
        assert store.get_connection(connection_id=created.id, org_id=ORG_A) is not None


class TestWebhookTokenResolution:
    def test_resolve_by_webhook_token_finds_connection(self):
        store = _store()
        created = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k",
            webhook_token="opaque-token-123",
        )
        found = resolve_by_webhook_token(store, "opaque-token-123")
        assert found is not None
        assert found.id == created.id

    def test_resolve_by_webhook_token_unknown_returns_none(self):
        store = _store()
        assert resolve_by_webhook_token(store, "does-not-exist") is None


class TestRecordExtensionHook:
    def test_extension_hook_folds_product_columns_into_extra(self):
        def _extension(row):
            return {
                "auto_reply_enabled": bool(row.get("auto_reply_enabled", False)),
                "marca_id": row.get("marca_id"),
            }

        store = _store(record_extension=_extension)
        created = store.create_connection(
            org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k",
            extra_fields={"auto_reply_enabled": True, "marca_id": "m-1"},
        )
        assert created.extra == {"auto_reply_enabled": True, "marca_id": "m-1"}
        fetched = store.get_connection(connection_id=created.id, org_id=ORG_A)
        assert fetched.extra == {"auto_reply_enabled": True, "marca_id": "m-1"}


class TestDecryptFailure:
    def test_tampered_ciphertext_raises_store_error_not_silent_none(self):
        store = _store()
        created = store.create_connection(org_id=ORG_A, user_id=USER_A, label="L", base_url="https://x.com", api_key="k")
        # Corrupt the encrypted value directly on the underlying fake row.
        rows = store._client._schemas["social_wiring"]["whatsapp_connections"]
        rows[0]["encrypted_api_key"] = "not-a-valid-fernet-token"
        with pytest.raises(WhatsAppConnectionStoreError):
            store.get_connection(connection_id=created.id, org_id=ORG_A, decrypt=True)


class TestWhatsappConnectionsTableDdl:
    def test_contains_org_scoped_rls_and_service_role_bypass(self):
        ddl = whatsapp_connections_table_ddl("social_wiring")
        assert "CREATE TABLE social_wiring.whatsapp_connections" in ddl
        assert "org_id = current_org_id()" in ddl
        assert '"service_role_bypass"' in ddl
        assert "webhook_token" in ddl
        assert "UNIQUE (org_id, label)" in ddl

    def test_custom_table_name(self):
        ddl = whatsapp_connections_table_ddl("acme", table="wa_lines")
        assert "CREATE TABLE acme.wa_lines" in ddl

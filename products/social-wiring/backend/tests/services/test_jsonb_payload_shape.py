"""Parity tests: JSONB-column write path must pass dicts, not JSON strings.

Root cause of the double-encode bug:
    integration_account_service.py called json.dumps() around channel_info /
    metadata before handing them to the supabase-py client.  supabase-py
    serialises JSONB parameters itself, so the string was stored INSIDE the
    JSONB column (jsonb_typeof = 'string'), breaking SQL-side access such as
    ``metadata->>'channel_id'``.

These tests intercept the payload dict that the service hands to
SQLiteQuery.insert / SQLiteQuery.update and assert the relevant JSONB columns
carry Python dicts, NOT strings.  They FAIL against the pre-fix code (which
wraps those values in json.dumps) and PASS after the fix.

This is NOT a workaround — we are patching the SQLite adapter (external to
the service under test) to inspect the wire value, consistent with the
``patch.object`` external-service boundary rule.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, call
from uuid import uuid4, UUID

import pytest
from cryptography.fernet import Fernet

from app.services.integration_account_service import (
    IntegrationAccountService,
)
from app.sqlite_client import SQLiteClient, SQLiteQuery

_ORG = UUID("00000000-0000-4000-8000-aabbccddeeff")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_accounts (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    provider            TEXT NOT NULL CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n')),
    account_label       TEXT NOT NULL,
    encrypted_credential TEXT NOT NULL,
    metadata            TEXT NOT NULL DEFAULT '{}',
    is_default          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    marca_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'validated',
    channel_info        TEXT NOT NULL DEFAULT '{}',
    last_synced_at      TEXT,
    UNIQUE (org_id, provider, account_label)
);
"""


@pytest.fixture
def sqlite_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "ia_jsonb.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def svc(sqlite_db: SQLiteClient) -> IntegrationAccountService:
    key = Fernet.generate_key()
    return IntegrationAccountService(sqlite_db, fernet=Fernet(key))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _capture_insert_payloads(svc: IntegrationAccountService) -> list[dict]:
    """Return all payload dicts passed to SQLiteQuery.insert during a block.

    Usage::

        with _capture_insert_payloads(svc) as payloads:
            svc.create_account(...)
        assert isinstance(payloads[0]["metadata"], dict)
    """
    return _CapturingContext(svc, "insert")


def _capture_update_payloads(svc: IntegrationAccountService) -> list[dict]:
    return _CapturingContext(svc, "update")


class _CapturingContext:
    """Context manager that wraps SQLiteQuery.insert or .update to sniff payloads."""

    def __init__(self, svc: IntegrationAccountService, method: str):
        self._svc = svc
        self._method = method
        self.payloads: list[dict] = []
        self._patcher = None

    def __enter__(self) -> "_CapturingContext":
        original = getattr(SQLiteQuery, self._method)

        def _spy(query_self, payload, **kwargs):
            self.payloads.append(payload)
            return original(query_self, payload, **kwargs)

        self._patcher = patch.object(SQLiteQuery, self._method, _spy)  # self-patch-ok: SQLiteQuery is the DB-driver boundary; spy intercepts wire payloads to assert dict vs string — not neutering business logic
        self._patcher.start()
        return self

    def __exit__(self, *_):
        if self._patcher:
            self._patcher.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestJsonbColumnsAreNotDoubleEncoded:
    """create_account and update_* must hand dicts — not JSON strings — for
    the JSONB columns (metadata, channel_info)."""

    def test_create_account_metadata_is_dict_not_string(self, svc):
        meta = {"channel_id": "UC_X", "channel_title": "My Channel"}
        with _CapturingContext(svc, "insert") as ctx:
            svc.create_account(
                org_id=_ORG,
                provider="youtube",
                account_label="Parity Test",
                credential_dict={"access_token": "tok"},
                metadata=meta,
            )
        assert ctx.payloads, "insert was never called"
        payload = ctx.payloads[0]
        assert "metadata" in payload, "metadata key missing from insert payload"
        assert isinstance(payload["metadata"], dict), (
            f"metadata must be a dict for JSONB; got {type(payload['metadata'])!r}: "
            f"{payload['metadata']!r}"
        )
        # Value round-trip sanity
        assert payload["metadata"]["channel_id"] == "UC_X"

    def test_update_account_metadata_is_dict_not_string(self, svc):
        acct = svc.create_account(
            org_id=_ORG,
            provider="youtube",
            account_label="Update Test",
            credential_dict={"access_token": "tok"},
            metadata={"channel_id": "UC_OLD"},
        )
        with _CapturingContext(svc, "update") as ctx:
            svc.update_account(
                account_id=acct.id,
                org_id=_ORG,
                metadata={"channel_id": "UC_NEW"},
            )
        assert ctx.payloads, "update was never called"
        payload = ctx.payloads[0]
        assert "metadata" in payload, "metadata key missing from update payload"
        assert isinstance(payload["metadata"], dict), (
            f"metadata must be a dict for JSONB; got {type(payload['metadata'])!r}: "
            f"{payload['metadata']!r}"
        )

    def test_update_channel_info_channel_info_is_dict_not_string(self, svc):
        acct = svc.create_account(
            org_id=_ORG,
            provider="youtube",
            account_label="Channel Info Test",
            credential_dict={"access_token": "tok"},
        )
        channel_info = {"channel_id": "UC_999", "title": "Test", "subscriber_count": 42}
        with _CapturingContext(svc, "update") as ctx:
            svc.update_channel_info(
                account_id=acct.id,
                org_id=_ORG,
                channel_info=channel_info,
                status="validated",
                last_synced_at=datetime.now(timezone.utc),
            )
        assert ctx.payloads, "update was never called"
        payload = ctx.payloads[0]
        assert "channel_info" in payload, "channel_info key missing from update payload"
        assert isinstance(payload["channel_info"], dict), (
            f"channel_info must be a dict for JSONB; got {type(payload['channel_info'])!r}: "
            f"{payload['channel_info']!r}"
        )

    def test_update_credential_metadata_merge_is_dict_not_string(self, svc):
        acct = svc.create_account(
            org_id=_ORG,
            provider="youtube",
            account_label="Cred Refresh Test",
            credential_dict={"access_token": "old_tok"},
            metadata={"channel_id": "UC_M"},
        )
        new_cred = {"access_token": "new_tok", "expires_in": 3600}
        with _CapturingContext(svc, "update") as ctx:
            svc.update_credential(
                account_id=acct.id,
                org_id=_ORG,
                credential_dict=new_cred,
                metadata={"expires_at": "2026-01-01T00:00:00Z"},
            )
        assert ctx.payloads, "update was never called"
        payload = ctx.payloads[0]
        assert "metadata" in payload, "metadata key missing from update_credential payload"
        assert isinstance(payload["metadata"], dict), (
            f"metadata must be a dict for JSONB (update_credential); "
            f"got {type(payload['metadata'])!r}: {payload['metadata']!r}"
        )
        # Ensure merge happened (existing channel_id + new expires_at both present)
        assert payload["metadata"]["channel_id"] == "UC_M"
        assert "expires_at" in payload["metadata"]

"""Tests for ContactService.upsert_whatsapp_contact.

Exercises:
- New contact is inserted with source='whatsapp', email=None.
- Existing contact (same phone): lids are unioned without duplicates.
- Existing contact: nome is overwritten only when phone-like.
- Existing contact: whatsapp_jid is set only when currently NULL.
- Existing contact: telefone is set only when currently NULL.

Uses MockSupabaseClient (no live DB).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_mock_table(existing: dict | None, updated: dict | None = None):
    """Build a minimal MockSupabaseClient-style `table()` chain.

    `existing`  — what `.select().eq().eq().limit().execute()` returns
    `updated`   — what `.update().eq().eq().execute()` returns (defaults to existing)
    """
    if updated is None:
        updated = existing

    mock_db = MagicMock()

    # select chain → returns existing row or empty
    select_result = MagicMock()
    select_result.data = [existing] if existing else []

    select_builder = MagicMock()
    select_builder.eq.return_value = select_builder
    select_builder.limit.return_value = select_builder
    select_builder.execute.return_value = select_result

    # update chain → returns updated row
    update_result = MagicMock()
    update_result.data = [updated] if updated else []

    update_builder = MagicMock()
    update_builder.eq.return_value = update_builder
    update_builder.execute.return_value = update_result

    # insert chain → returns newly-inserted row
    insert_result = MagicMock()
    insert_result.data = []  # will be overridden per test

    insert_builder = MagicMock()
    insert_builder.execute.return_value = insert_result

    table_mock = MagicMock()
    table_mock.select.return_value = select_builder
    table_mock.update.return_value = update_builder
    table_mock.insert.return_value = insert_builder

    mock_db.table.return_value = table_mock

    return mock_db, table_mock, insert_builder, insert_result, update_builder, update_result


# ── tests ─────────────────────────────────────────────────────────────────────


def test_upsert_inserts_new_contact_with_whatsapp_source():
    from app.modules.email_marketing.services.contact_service import ContactService

    new_row = {
        "id": "aaaaaaaa-0000-4000-8000-000000000001",
        "org_id": "org1",
        "source": "whatsapp",
        "email": None,
        "nome": "João Raphael",
        "telefone": "5511974693365",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": ["33613018058989@lid"],
        "whatsapp_jid": "5511974693365@c.us",
    }
    mock_db, table_mock, insert_builder, insert_result, _, _ = _make_mock_table(
        existing=None
    )
    insert_result.data = [new_row]

    svc = ContactService(mock_db, "org1")
    result = svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=["33613018058989@lid"],
        name="João Raphael",
        jid="5511974693365@c.us",
    )

    # insert was called
    table_mock.insert.assert_called_once()
    insert_kwargs = table_mock.insert.call_args.args[0]
    assert insert_kwargs["source"] == "whatsapp"
    assert insert_kwargs["email"] is None
    assert insert_kwargs["whatsapp_phone"] == "5511974693365"
    assert insert_kwargs["whatsapp_lids"] == ["33613018058989@lid"]
    assert result["nome"] == "João Raphael"


def test_upsert_existing_contact_unions_lids():
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": ["33613018058989@lid"],
        "whatsapp_jid": "5511974693365@c.us",
        "telefone": "5511974693365",
        "nome": "João",
    }
    updated = dict(existing, whatsapp_lids=["33613018058989@lid", "1099562024960@lid"])
    mock_db, table_mock, _, _, update_builder, update_result = _make_mock_table(
        existing=existing, updated=updated
    )

    svc = ContactService(mock_db, "org1")
    result = svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=["1099562024960@lid"],  # new LID to union
        name="João",
        jid=None,
    )

    # update was called; insert was NOT called
    table_mock.update.assert_called_once()
    table_mock.insert.assert_not_called()
    update_payload = table_mock.update.call_args.args[0]
    assert "1099562024960@lid" in update_payload["whatsapp_lids"]
    assert "33613018058989@lid" in update_payload["whatsapp_lids"]


def test_upsert_does_not_duplicate_existing_lids():
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": ["33613018058989@lid"],
        "whatsapp_jid": "5511974693365@c.us",
        "telefone": None,
        "nome": "5511974693365",  # phone-like, would be replaced
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=["33613018058989@lid"],  # same LID already present
        name="New Name",
        jid=None,
    )

    update_payload = table_mock.update.call_args.args[0]
    # LID should appear only once (order-preserving dedup)
    assert update_payload["whatsapp_lids"].count("33613018058989@lid") == 1


def test_upsert_overwrites_phone_like_nome():
    """Nome that looks like a phone number is replaced by WAHA name."""
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": [],
        "whatsapp_jid": None,
        "telefone": None,
        "nome": "5511974693365",  # phone-like
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=[],
        name="João Raphael",
        jid="5511974693365@c.us",
    )

    update_payload = table_mock.update.call_args.args[0]
    assert update_payload["nome"] == "João Raphael"


def test_upsert_does_not_overwrite_real_nome():
    """A real human name (not phone-like) is never overwritten."""
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": [],
        "whatsapp_jid": None,
        "telefone": None,
        "nome": "Maria Josefina",  # real name
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=[],
        name="WhatsApp Name",
        jid=None,
    )

    update_payload = table_mock.update.call_args.args[0]
    assert "nome" not in update_payload  # not overwritten


def test_upsert_sets_whatsapp_jid_when_null():
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": [],
        "whatsapp_jid": None,
        "telefone": None,
        "nome": "5511974693365",
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=[],
        name=None,
        jid="5511974693365@c.us",
    )

    update_payload = table_mock.update.call_args.args[0]
    assert update_payload["whatsapp_jid"] == "5511974693365@c.us"


def test_upsert_does_not_overwrite_existing_whatsapp_jid():
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": [],
        "whatsapp_jid": "5511974693365@c.us",  # already set
        "telefone": None,
        "nome": "5511974693365",
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=[],
        name=None,
        jid="new_different@c.us",
    )

    update_payload = table_mock.update.call_args.args[0]
    assert "whatsapp_jid" not in update_payload


def test_upsert_sets_telefone_when_null():
    from app.modules.email_marketing.services.contact_service import ContactService

    existing = {
        "id": "aaa",
        "org_id": "org1",
        "whatsapp_phone": "5511974693365",
        "whatsapp_lids": [],
        "whatsapp_jid": None,
        "telefone": None,
        "nome": "Name",
    }
    mock_db, table_mock, _, _, _, _ = _make_mock_table(existing=existing)

    svc = ContactService(mock_db, "org1")
    svc.upsert_whatsapp_contact(
        phone="5511974693365",
        lids=[],
        name=None,
        jid=None,
    )

    update_payload = table_mock.update.call_args.args[0]
    assert update_payload["telefone"] == "5511974693365"

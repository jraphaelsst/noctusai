"""Tests for the WhatsApp identity resolver + lids-map builder.

Exercises:
- resolve_identity with @lid input → phone + name + lids collected
- resolve_identity with phone-form input → phone + name + LID from contact record
- resolve_identity is fail-soft on WAHA error (returns partial result)
- build_lids_map_from_list → {lid_jid: phone_digits} dict

Uses FakeWahaClient (no httpx) and asyncio.run (not get_event_loop).
"""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from app.services.whatsapp_identity import (
    ResolvedIdentity,
    build_lids_map_from_list,
    resolve_identity,
)


# ── resolve_identity — @lid input ─────────────────────────────────────────────


def test_resolve_identity_lid_path_returns_phone_and_name():
    """@lid → get_lid_phone → phone; get_contact(lid) → name."""
    client = FakeWahaClient()
    client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"
    client.fake_contacts["33613018058989@lid"] = {
        "id": "33613018058989@lid",
        "pushname": "João Raphael",
    }
    # No phone-JID contact → lid-from-phone branch returns {}
    client.fake_contacts["5511974693365@c.us"] = {}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "33613018058989@lid")
    )

    assert result.phone == "5511974693365"
    assert result.jid == "5511974693365@c.us"
    assert "33613018058989@lid" in result.lids
    assert result.name == "João Raphael"


def test_resolve_identity_lid_path_picks_up_paired_lid_from_phone_contact():
    """When the phone-form contact record includes a `lid` field, it's added to lids."""
    client = FakeWahaClient()
    client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"
    client.fake_contacts["33613018058989@lid"] = {"pushname": "Test User"}
    client.fake_contacts["5511974693365@c.us"] = {
        "id": "5511974693365@c.us",
        "name": "Test User Full",
        "lid": "9999999@lid",  # second LID for same human
    }

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "33613018058989@lid")
    )

    assert result.phone == "5511974693365"
    assert "33613018058989@lid" in result.lids
    assert "9999999@lid" in result.lids


def test_resolve_identity_lid_path_prefers_phone_contact_name_when_lid_has_no_name():
    """Name falls back to phone-contact name when LID contact has no name."""
    client = FakeWahaClient()
    client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"
    client.fake_contacts["33613018058989@lid"] = {}  # no name on LID contact
    client.fake_contacts["5511974693365@c.us"] = {"name": "From Phone Form"}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "33613018058989@lid")
    )

    assert result.name == "From Phone Form"


def test_resolve_identity_lid_no_phone_mapped_gives_partial():
    """When get_lid_phone returns None, phone/jid stay None but lids is set."""
    client = FakeWahaClient()
    # No mapping seeded — fake returns None
    client.fake_contacts["unknownlid@lid"] = {"pushname": "Anon"}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "unknownlid@lid")
    )

    assert result.phone is None
    assert result.jid is None
    assert "unknownlid@lid" in result.lids
    assert result.name == "Anon"


# ── resolve_identity — phone-form input ───────────────────────────────────────


def test_resolve_identity_phone_cus_path_returns_phone_and_name():
    """@c.us → phone digits; get_contact returns name + paired LID."""
    client = FakeWahaClient()
    client.fake_contacts["5511974693365@c.us"] = {
        "id": "5511974693365@c.us",
        "name": "João Raphael",
        "lid": "33613018058989@lid",
    }

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "5511974693365@c.us")
    )

    assert result.phone == "5511974693365"
    assert result.jid == "5511974693365@c.us"
    assert result.name == "João Raphael"
    assert result.lids == ["33613018058989@lid"]


def test_resolve_identity_phone_whatsapp_net_path():
    """@s.whatsapp.net suffix is treated as phone-form input."""
    client = FakeWahaClient()
    client.fake_contacts["5511974693365@c.us"] = {"name": "Net User"}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "5511974693365@s.whatsapp.net")
    )

    assert result.phone == "5511974693365"
    assert result.jid == "5511974693365@c.us"
    assert result.name == "Net User"


def test_resolve_identity_phone_no_contact_gives_partial():
    """Phone-form with no WAHA contact → phone/jid set, name is None."""
    client = FakeWahaClient()
    # fake_contacts is empty, so get_contact returns {}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "5511111111111@c.us")
    )

    assert result.phone == "5511111111111"
    assert result.jid == "5511111111111@c.us"
    assert result.name is None
    assert result.lids == []


# ── resolve_identity — fail-soft ──────────────────────────────────────────────


def test_resolve_identity_survives_get_contact_exception():
    """WAHA error in get_contact → returns partial result, does not raise."""
    from unittest.mock import AsyncMock, MagicMock

    client = FakeWahaClient()
    client.get_contact = AsyncMock(side_effect=RuntimeError("WAHA down"))
    # Seed the phone mapping so the LID path can still produce phone
    client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "33613018058989@lid")
    )

    # Should not raise; should still have phone from get_lid_phone
    assert result.phone == "5511974693365"
    # name may be None since get_contact failed
    # lids should have the input lid
    assert "33613018058989@lid" in result.lids


def test_resolve_identity_survives_get_lid_phone_exception():
    """WAHA error in get_lid_phone → returns partial result."""
    from unittest.mock import AsyncMock

    client = FakeWahaClient()
    client.get_lid_phone = AsyncMock(side_effect=RuntimeError("timeout"))
    client.fake_contacts["33613018058989@lid"] = {"pushname": "Anon"}

    result: ResolvedIdentity = asyncio.run(
        resolve_identity(client, "33613018058989@lid")
    )

    # Should not raise; phone will be None since get_lid_phone failed
    assert result.phone is None
    assert "33613018058989@lid" in result.lids
    assert result.name == "Anon"


# ── build_lids_map_from_list ──────────────────────────────────────────────────


def test_build_lids_map_from_list_maps_lid_to_phone_digits():
    lids_list = [
        {"lid": "33613018058989@lid", "pn": "5511974693365@c.us"},
        {"lid": "1099562024960@lid", "pn": "5511974693365@c.us"},
    ]
    result = build_lids_map_from_list(lids_list)

    assert result["33613018058989@lid"] == "5511974693365"
    assert result["1099562024960@lid"] == "5511974693365"


def test_build_lids_map_from_list_empty_on_missing_fields():
    """Entries with no lid or pn are skipped."""
    lids_list = [
        {"lid": "", "pn": "5511@c.us"},
        {"pn": "5511@c.us"},  # no lid key
        {"lid": "somelidvalue@lid"},  # no pn key
    ]
    result = build_lids_map_from_list(lids_list)

    # Only complete entries make it in; partial ones are skipped
    assert result == {}


def test_build_lids_map_from_list_empty_input():
    assert build_lids_map_from_list([]) == {}

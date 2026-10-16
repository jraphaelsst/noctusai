"""Orbity's host side of the billing-reminders organ: contact, payment link + PIX, the veto, the WhatsApp line.

Collaborators swap through the organ's own DI seams (``resolve_client=`` -> the seed ``FakeWahaClient``); nothing is patched.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.domain.finance.reminders import (
    ensure_default_rules,
    preview_reminders,
    run_reminders_for_org,
    update_settings,
)
from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.testing import MockSupabaseClient

from app.billing import FINANCE_CFG, SCHEMA
from app.services.billing_reminders import (
    SKIP_CHARGE_CANCELLED,
    SKIP_CLIENT_INACTIVE,
    build_reminder_ports,
    load_charge_and_client,
    resolve_contact,
    skip_reason,
)

ORG = "00000000-0000-0000-0000-000000000abc"
OTHER_ORG = "00000000-0000-0000-0000-000000000def"
CLIENT = "c1000000-0000-4000-8000-000000000001"
ENTRY = "e1000000-0000-4000-8000-000000000001"
CHARGE = "b1000000-0000-4000-8000-000000000001"
TODAY = date(2026, 10, 20)


def _client(**over):
    return {"id": CLIENT, "org_id": ORG, "name": "Studio Acme", "legal_name": "Acme Serviços LTDA", "phone": "(11) 98888-7777",
            "active": True, "inactivated_at": None, **over}


def _charge(**over):
    return {"id": CHARGE, "org_id": ORG, "entry_id": ENTRY, "client_id": CLIENT, "invoice_url": "https://pay.example/inv_1",
            "pix_payload": "00020126PIXCODE", "preserved_after_deactivation": False, "gateway_cancel_status": None, **over}


def _entry(**over):
    return {"id": ENTRY, "org_id": ORG, "direction": "receivable", "status": "open", "description": "Gestão de tráfego",
            "competence_month": "2026-10-01", "due_date": "2026-10-23", "amount_cents": 150_000, "settled_cents": 0,
            "counterparty_name": "Acme", "reminders_opt_out": False, **over}


def _db(*, client=None, charge=None, entry=None):
    db = MockSupabaseClient(schema=SCHEMA)
    db.set_table_data("clients", [client] if client else [])
    db.set_table_data("billing_charges", [charge] if charge else [])
    db.set_table_data("fin_entries", [entry] if entry else [])
    for table in ("fin_reminder_settings", "fin_reminder_rules", "fin_reminder_log"):
        db.set_table_data(table, [])
    return db


def _scope(db, org=ORG):
    return Scope(db, FINANCE_CFG, org)


class TestContact:
    def test_the_client_and_the_charge_feed_every_template_variable(self):
        s = _scope(_db(client=_client(), charge=_charge(), entry=_entry()))
        c = resolve_contact(s, _entry())
        assert (c.nome, c.nome_fantasia, c.razao_social) == ("Studio Acme", "Studio Acme", "Acme Serviços LTDA")
        assert c.phone == "(11) 98888-7777"
        assert (c.link_pagamento, c.pix_copia_cola) == ("https://pay.example/inv_1", "00020126PIXCODE")

    def test_a_charge_without_a_gateway_link_still_has_a_contact_but_no_link(self):
        s = _scope(_db(client=_client(), charge=_charge(invoice_url=None, pix_payload=None), entry=_entry()))
        c = resolve_contact(s, _entry())
        assert c.phone and c.link_pagamento is None and c.pix_copia_cola is None

    def test_a_hand_keyed_receivable_falls_back_to_the_counterparty_with_no_phone(self):
        s = _scope(_db(entry=_entry()))
        c = resolve_contact(s, _entry())
        assert c.nome == "Acme" and c.phone is None
        assert resolve_contact(s, _entry(counterparty_name=None)) is None

    def test_another_orgs_client_is_never_read(self):
        s = _scope(_db(client=_client(org_id=OTHER_ORG), charge=_charge(), entry=_entry()))
        assert load_charge_and_client(s, _entry())[1] is None


class TestVeto:
    @pytest.mark.parametrize("client_over,charge_over,expected", [
        ({}, {}, None),
        ({"active": False, "inactivated_at": "2026-09-01T00:00:00+00:00"}, {}, SKIP_CLIENT_INACTIVE),
        ({"active": False, "inactivated_at": "2026-09-01T00:00:00+00:00"}, {"preserved_after_deactivation": True}, None),
        ({}, {"gateway_cancel_status": "pending"}, SKIP_CHARGE_CANCELLED),
        ({}, {"gateway_cancel_status": "done"}, SKIP_CHARGE_CANCELLED),
        ({}, {"gateway_cancel_status": "failed"}, None),
        ({"active": False, "inactivated_at": "2026-09-01T00:00:00+00:00"}, {"preserved_after_deactivation": True, "gateway_cancel_status": "done"}, SKIP_CHARGE_CANCELLED),
    ])
    def test_inactivated_unless_preserved_and_cancelled_charges_are_vetoed(self, client_over, charge_over, expected):
        s = _scope(_db(client=_client(**client_over), charge=_charge(**charge_over), entry=_entry()))
        assert skip_reason(s, _entry()) == expected

    def test_a_receivable_with_no_charge_row_is_not_vetoed(self):
        assert skip_reason(_scope(_db(entry=_entry())), _entry()) is None


class TestEndToEndThroughTheOrgan:
    """Rules + selection + dedup + send, with the seed Fake WAHA client as the org's line."""

    def _ports(self, line):
        return build_reminder_ports(resolve_client=lambda org_id: line)

    def _enabled(self, db):
        s = _scope(db)
        update_settings(s, {"enabled": True})
        ensure_default_rules(s)
        return s

    def test_off_by_default_nothing_is_planned_or_sent(self):
        db = _db(client=_client(), charge=_charge(), entry=_entry(due_date="2026-10-20"))
        line = FakeWahaClient()
        s = _scope(db)
        ensure_default_rules(s)
        assert preview_reminders(s, self._ports(line), on=TODAY).planned == []
        assert run_reminders_for_org(s, self._ports(line), on=TODAY)["sent"] == 0 and line.sent_messages == []

    def test_the_due_day_reminder_carries_name_amount_link_and_pix(self):
        db = _db(client=_client(), charge=_charge(), entry=_entry(due_date="2026-10-20"))
        line = FakeWahaClient()
        s = self._enabled(db)
        assert run_reminders_for_org(s, self._ports(line), on=TODAY)["sent"] == 1
        (sent,) = line.sent_messages
        assert "5511988887777@c.us" in sent["chatId"]
        for needle in ("Acme", "1.500,00", "https://pay.example/inv_1", "00020126PIXCODE"):
            assert needle in sent["text"], needle
        assert run_reminders_for_org(s, self._ports(line), on=TODAY)["sent"] == 0  # dedup ledger
        assert len(line.sent_messages) == 1

    def test_the_ninth_digit_is_resolved_before_sending(self):
        """The client's phone has the 9; WhatsApp has it registered without -> the message goes to the real chat."""
        db = _db(client=_client(phone="11988887777"), charge=_charge(), entry=_entry(due_date="2026-10-20"))
        line = FakeWahaClient()
        line.registered_numbers = {"551188887777"}
        s = self._enabled(db)
        assert run_reminders_for_org(s, self._ports(line), on=TODAY)["sent"] == 1
        assert line.sent_messages[0]["chatId"] == "551188887777@c.us"

    def test_an_inactivated_client_gets_nothing_unless_the_charge_was_kept(self):
        inactive = {"active": False, "inactivated_at": "2026-09-01T00:00:00+00:00"}
        line = FakeWahaClient()
        s = self._enabled(_db(client=_client(**inactive), charge=_charge(), entry=_entry(due_date="2026-10-20")))
        plan = preview_reminders(s, self._ports(line), on=TODAY)
        assert plan.planned == [] and {k.reason for k in plan.skipped} == {"blocked_by_host"}
        kept = self._enabled(_db(client=_client(**inactive), charge=_charge(preserved_after_deactivation=True), entry=_entry(due_date="2026-10-20")))
        assert len(preview_reminders(kept, self._ports(line), on=TODAY).planned) == 1

    def test_no_connected_line_is_a_loud_failed_row_not_a_silent_skip(self):
        db = _db(client=_client(), charge=_charge(), entry=_entry(due_date="2026-10-20"))
        s = self._enabled(db)
        out = run_reminders_for_org(s, self._ports(None), on=TODAY)
        assert out["sent"] == 0 and out["failed"] == 1
        (row,) = db.table("fin_reminder_log")._data
        assert row["status"] == "failed" and "sem linha de WhatsApp" in row["last_error"]

    def test_an_org_with_no_saved_connection_has_no_line_and_no_fleet_fallback(self):
        """The line resolver reads ONLY the org's own saved connections (never the static WAHA_* number)."""
        from cryptography.fernet import Fernet
        from noctusai_lib.domain.finance.reminders import make_waha_client_resolver
        from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store

        db = _db()
        db.set_table_data("whatsapp_connections", [])

        class Pinned:
            def schema(self, _):
                return self

            def table(self, name):
                return db.table(name)

        store = build_whatsapp_connection_store(Pinned(), encryption_key=Fernet.generate_key().decode(), schema="orbity")
        assert make_waha_client_resolver(store)(ORG) is None

    def test_a_missing_encryption_key_is_no_usable_line_not_a_crash(self, client):
        from app.services.billing_reminders import _org_waha_client

        assert _org_waha_client(ORG) is None  # tests run without ENCRYPTION_KEY

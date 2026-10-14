"""The parties link (`fin_entries.party_id`) and the payable booking seam (`book_payable`) -- closes
the parties-finance link remediation. Mounted only when `FinanceConfig.with_parties`; `counterparty_*` stays a snapshot."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import FakeFinanceBooking, FinanceBooking, FinanceConfig, finance_migration, make_finance_booking
from noctusai_lib.domain.finance import entries
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.types import EntrySource, values
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

from .conftest import ORG_A, ORG_B, SCHEMA

PARTY = "33333333-3333-4333-8333-333333333333"
WITH = FinanceConfig(schema=SCHEMA, with_parties=True)
PAY = dict(
    source="purchasing", source_ref="rcpt-1", description="Compra #1", counterparty_name="Forn", counterparty_doc=None,
    amount_cents=5000, competence_month=date(2026, 10, 14), due_date=date(2026, 11, 13), category_hint="Mercadorias / insumos para revenda",
)


@pytest.fixture
def party_db():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = {**parse_sql(parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA), source_label="parties"),
                 **parse_sql(finance_migration(WITH, SCHEMA), source_label="finance")}
    _schema_cache.set_cache_for_tests({**base, **generated})
    db = MockSupabaseClient(validate_schema=True, schema=SCHEMA)
    db.table("pty_parties").insert({"id": PARTY, "org_id": ORG_A, "kind": "PJ", "legal_name": "Forn"}).execute()
    yield db
    _schema_cache.set_cache_for_tests(base)


def test_the_generator_adds_party_id_and_the_composite_fk_only_when_parties_are_mounted():
    with_sql = finance_migration(WITH, SCHEMA)
    without = finance_migration(FinanceConfig(schema=SCHEMA), SCHEMA)
    assert "ADD COLUMN IF NOT EXISTS party_id UUID" in with_sql
    assert "FOREIGN KEY (party_id, org_id) REFERENCES finx.pty_parties(id, org_id)" in with_sql
    assert "party_id" not in without and "pty_parties" not in without
    assert "'purchasing'" in without  # the source vocabulary is re-stated for tables created before it existed
    assert values(EntrySource)[-1] == "purchasing"


def test_book_payable_creates_a_linked_payable_and_is_idempotent(party_db):
    booking = make_finance_booking("supabase", db=party_db, cfg=WITH)
    first = booking.book_payable(ORG_A, party_id=PARTY, **PAY)
    again = booking.book_payable(ORG_A, party_id=PARTY, **PAY)
    s = Scope(party_db, WITH, ORG_A)
    assert first == again and len(s.rows("entries")) == 1
    e = s.find("entries", first)
    assert e["direction"] == "payable" and e["source"] == "purchasing" and e["party_id"] == PARTY and e["amount_cents"] == 5000
    assert s.find("categories", e["category_id"])["name"] == "Mercadorias / insumos para revenda"
    assert isinstance(booking, FinanceBooking) and isinstance(FakeFinanceBooking(), FinanceBooking)


def test_book_payable_without_parties_mounted_drops_the_link_instead_of_writing_a_missing_column(party_db):
    booking = make_finance_booking("supabase", db=party_db, cfg=FinanceConfig(schema=SCHEMA))
    entry_id = booking.book_payable(ORG_A, party_id=PARTY, **PAY)
    assert Scope(party_db, WITH, ORG_A).find("entries", entry_id).get("party_id") is None


def test_a_party_of_another_org_is_refused(party_db):
    party_db.table("pty_parties").insert({"id": "44444444-4444-4444-8444-444444444444", "org_id": ORG_B, "kind": "PJ", "legal_name": "X"}).execute()
    s = Scope(party_db, WITH, ORG_A)
    with pytest.raises(FinanceError) as exc:
        entries.create_entry(s, {"direction": "payable", "description": "x", "amount_cents": 10, "due_date": date(2026, 11, 1),
                                 "party_id": "44444444-4444-4444-8444-444444444444"})
    assert exc.value.status_code == 422 and exc.value.code == "referencia_invalida"


def test_a_party_id_without_the_parties_organ_is_a_422(party_db):
    s = Scope(party_db, FinanceConfig(schema=SCHEMA), ORG_A)
    with pytest.raises(FinanceError) as exc:
        entries.create_entry(s, {"direction": "payable", "description": "x", "amount_cents": 10, "due_date": date(2026, 11, 1), "party_id": PARTY})
    assert exc.value.code == "parceiros_indisponivel"


def test_an_entry_can_be_linked_and_relinked_through_update(party_db):
    s = Scope(party_db, WITH, ORG_A)
    [e] = entries.create_entry(s, {"direction": "payable", "description": "x", "amount_cents": 10, "due_date": date(2026, 11, 1)})
    out = entries.update_entry(s, e["id"], {"party_id": PARTY})
    assert out["party_id"] == PARTY and s.find("entries", e["id"])["party_id"] == PARTY
    assert entries.update_entry(s, e["id"], {"party_id": None})["party_id"] is None


def test_the_fake_booking_records_payables_under_the_same_idempotency_key():
    fake = FakeFinanceBooking()
    a = fake.book_payable(ORG_A, party_id=PARTY, **PAY)
    assert a == fake.book_payable(ORG_A, party_id=PARTY, **PAY) and fake.entries[(ORG_A, "purchasing", "rcpt-1")]["direction"] == "payable"

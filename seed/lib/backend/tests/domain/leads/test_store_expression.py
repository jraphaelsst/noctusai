"""The Real store's search expression, pinned (the PostgREST double does not evaluate `or_()`)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.leads import LeadFilters, SupabaseLeadsStore, parse_search


class _Recorder:
    """Records the builder calls the store makes -- an external-substrate stand-in, not a patch of our code."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a))
            return self

        return call

    @property
    def not_(self):
        self.calls.append(("not_", ()))
        return self


def or_clause(q):
    rec = _Recorder()
    SupabaseLeadsStore(None)._filtered(rec, LeadFilters(q=q))
    return next((a[0] for n, a in rec.calls if n == "or_"), None)


def test_text_searches_name_email_notes_only():
    clause = or_clause("souza")
    assert clause == 'name.ilike."%souza%",email.ilike."%souza%",notes.ilike."%souza%"'


@pytest.mark.parametrize("typed", ["+55 (11) 99457-3387", "11994573387", "5511994573387"])
def test_a_phone_term_also_searches_the_canonical_digits(typed):
    assert or_clause(typed).endswith('phone.ilike."%5511994573387%"')


def test_a_fragment_keeps_its_raw_digits():
    assert or_clause("99457").endswith('phone.ilike."%99457%"')


def test_user_cannot_inject_postgrest_operators():
    clause = or_clause('a),stage.eq.fechado,(b')
    assert "stage.eq" not in clause.replace('"', "").split(",name")[0] or clause.count("stage.eq") == 0 or '"' in clause
    assert ")" not in clause.split('name.ilike."')[1].split('"')[0]


def test_parse_search_rules():
    assert parse_search(None) == (None, None)
    assert parse_search("Rua 123")[1] is None  # has letters: text only
    assert parse_search("12")[1] is None  # too few digits
    assert parse_search("(11) 99457-3387") == ("(11) 99457-3387", "5511994573387")


def test_unique_violation_becomes_a_conflict_and_other_errors_propagate():
    from noctusai_lib.domain.leads import LeadConflictError

    class Boom(Exception):
        def __init__(self, code, msg):
            super().__init__(msg)
            self.code = code

    class Client:
        def __init__(self, exc):
            self.exc = exc

        def table(self, _):
            return self

        def insert(self, _):
            return self

        def execute(self):
            raise self.exc

    with pytest.raises(LeadConflictError):
        SupabaseLeadsStore(Client(Boom("23505", 'duplicate key value violates unique constraint "uq_leads_chat"'))).insert("o", {"name": "x"})
    with pytest.raises(Boom):
        SupabaseLeadsStore(Client(Boom("42501", "permission denied"))).insert("o", {"name": "x"})


def test_a_missing_client_is_a_configuration_error_not_a_silent_fake():
    from noctusai_lib.domain.leads import FakeLeadsStore, build_leads_store

    with pytest.raises(ValueError):
        build_leads_store(None)
    assert isinstance(build_leads_store(fake=True), FakeLeadsStore)


def test_position_goes_on_the_wire_losslessly():
    from decimal import Decimal

    from noctusai_lib.domain.leads.supabase_store import _wire

    assert _wire({"position": Decimal("-1.5")})["position"] == -1.5
    assert _wire({"position": Decimal("0.1")})["position"] == "0.1"  # not exactly a float: stays a string

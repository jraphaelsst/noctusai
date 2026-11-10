"""`noctusai_lib.security.oauth.state_store` -- single-use, provider-bound, expiring OAuth state."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.security.oauth import (
    FakeOAuthStateStore,
    SupabaseOAuthStateStore,
    make_oauth_state_store,
)


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    """Faithful PostgREST double for the chain the store calls (insert / delete + eq|lt filters)."""

    def __init__(self, rows):
        self._rows, self._op, self._payload, self._eq, self._lt = rows, None, None, {}, {}

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def lt(self, col, val):
        self._lt[col] = val
        return self

    def _match(self, r):
        return all(r.get(k) == v for k, v in self._eq.items()) and all(str(r.get(k)) < v for k, v in self._lt.items())

    def execute(self):
        if self._op == "insert":
            self._rows.append(dict(self._payload))
            return _Resp([dict(self._payload)])
        gone = [r for r in self._rows if self._match(r)]
        self._rows[:] = [r for r in self._rows if not self._match(r)]
        return _Resp(gone)


class _Client:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _Query(self.tables.setdefault(name, []))


def _issue(store, **kw):
    args = dict(provider="google", org_id="o1", user_id="u1", redirect_uri="https://x/cb", code_verifier="V" * 43)
    args.update(kw)
    return store.issue(**args)


@pytest.fixture(params=["fake", "real"])
def store(request):
    if request.param == "fake":
        return FakeOAuthStateStore()
    return SupabaseOAuthStateStore(_Client(), generate_key())


def test_a_state_is_consumed_exactly_once(store):
    state = _issue(store)
    rec = store.consume(state, provider="google")
    assert (rec.org_id, rec.user_id, rec.redirect_uri, rec.code_verifier) == ("o1", "u1", "https://x/cb", "V" * 43)
    assert store.consume(state, provider="google") is None


def test_unknown_state_and_other_provider_are_refused(store):
    assert store.consume("never-issued", provider="google") is None
    state = _issue(store)
    assert store.consume(state, provider="meta") is None
    assert store.consume(state, provider="google") is None  # the wrong-provider attempt also burned it


def test_states_are_unguessable_and_distinct(store):
    a, b = _issue(store), _issue(store)
    assert a != b and len(a) >= 40


def test_expired_state_is_refused():
    clock = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    fake = FakeOAuthStateStore(now=lambda: clock["t"])
    state = _issue(fake, ttl_seconds=60)
    clock["t"] += timedelta(seconds=61)
    assert fake.consume(state, provider="google") is None


def test_real_store_keeps_only_the_hash_and_an_encrypted_verifier():
    client = _Client()
    real = SupabaseOAuthStateStore(client, generate_key())
    state = _issue(real, code_verifier="SECRET-VERIFIER")
    (row,) = client.tables["oauth_states"]
    assert state not in row.values() and "SECRET-VERIFIER" not in row.values()
    assert row["state_hash"] != state and row["encrypted_code_verifier"] != "SECRET-VERIFIER"


def test_real_store_refuses_an_expired_row_and_a_wrong_key():
    client = _Client()
    real = SupabaseOAuthStateStore(client, generate_key())
    state = _issue(real, ttl_seconds=-5)
    assert real.consume(state, provider="google") is None
    state2 = _issue(real)
    assert SupabaseOAuthStateStore(client, generate_key()).consume(state2, provider="google") is None


def test_factory_picks_real_only_with_client_and_key():
    assert isinstance(make_oauth_state_store(), FakeOAuthStateStore)
    assert isinstance(make_oauth_state_store(client=_Client(), fernet_key=generate_key()), SupabaseOAuthStateStore)

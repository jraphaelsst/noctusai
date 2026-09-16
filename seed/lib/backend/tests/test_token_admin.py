"""Tests for `noctusai_lib.api.auth.session.token_admin`.

The Real adapter runs against an in-test double of the supabase-py
query-builder surface it calls (external substrate stand-in — the same
convention as `test_app_config.py`), never a patch of our own code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from noctusai_lib.api.auth.session import (
    FakeProductTokenAdmin,
    SupabaseProductTokenAdmin,
    build_api_token_row,
    hash_token,
    make_product_token_admin,
    mint_token_secret,
)

EXPIRES = datetime.now(timezone.utc) + timedelta(days=90)


class _Resp:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, db, name):
        self._db, self._name = db, name
        self._op, self._payload, self._filters = "select", None, {}

    def select(self, _cols):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = self._db.setdefault(self._name, [])
        match = [r for r in rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._op == "insert":
            rows.append(dict(self._payload))
            return _Resp([self._payload])
        if self._op == "update":
            for r in match:
                r.update(self._payload)
            return _Resp(match)
        return _Resp(match)


class _Client:
    def __init__(self):
        self.db: dict = {}
        self.schemas: list[str] = []

    def schema(self, name):
        self.schemas.append(name)
        client = self

        class _Scoped:
            def table(self, table):
                return _Table(client.db, f"{name}.{table}")

        return _Scoped()


class TestHelpers:
    def test_minted_secret_shape(self):
        raw, prefix = mint_token_secret()
        assert raw.startswith("pk_") and len(raw) == 67
        assert prefix == raw[:11]

    def test_row_stores_only_the_digest(self):
        raw, _ = mint_token_secret()
        row = build_api_token_row(
            token_id=uuid4(), raw_secret=raw, org_id=uuid4(), label="x",
            scopes=["a"], expires_at=EXPIRES, created_at=datetime.now(timezone.utc),
            issuer="agents",
        )
        assert raw not in str(row)
        assert row["token_hash"] == hash_token(raw)
        assert row["issuer"] == "agents"

    def test_row_omits_issuer_when_unset(self):
        raw, _ = mint_token_secret()
        row = build_api_token_row(
            token_id=uuid4(), raw_secret=raw, org_id=uuid4(), label="x",
            scopes=[], expires_at=EXPIRES, created_at=datetime.now(timezone.utc),
        )
        assert "issuer" not in row


class TestSupabaseProductTokenAdmin:
    def test_mint_find_revoke_round_trip_in_the_target_schema(self):
        client = _Client()
        admin = SupabaseProductTokenAdmin(client)
        org, agent = uuid4(), uuid4()
        minted = admin.mint(
            "academia_de_reciclagem", org_id=org, label="agents", scopes=["academia:read"],
            expires_at=EXPIRES, principal_agent_id=agent, issuer="agents",
        )
        assert set(client.schemas) == {"academia_de_reciclagem"}
        found = admin.find_by_secret("academia_de_reciclagem", minted.secret)
        assert found is not None
        assert found.id == minted.info.id
        assert found.principal_agent_id == agent
        assert found.issuer == "agents"
        assert found.revoked_at is None

        assert admin.revoke("academia_de_reciclagem", found.id, org_id=org) is True
        assert admin.find_by_secret("academia_de_reciclagem", minted.secret).revoked_at is not None

    def test_revoke_is_org_scoped(self):
        client = _Client()
        admin = SupabaseProductTokenAdmin(client)
        minted = admin.mint(
            "social_wiring", org_id=uuid4(), label="x", scopes=[], expires_at=EXPIRES,
        )
        assert admin.revoke("social_wiring", minted.info.id, org_id=uuid4()) is False

    def test_unknown_secret_is_none(self):
        assert SupabaseProductTokenAdmin(_Client()).find_by_secret("s", "pk_nope") is None


class TestFakeAndFactory:
    def test_factory_selects(self):
        assert isinstance(make_product_token_admin(), FakeProductTokenAdmin)
        assert isinstance(make_product_token_admin(_Client()), SupabaseProductTokenAdmin)

    def test_fake_seed_and_find(self):
        fake = FakeProductTokenAdmin()
        org = uuid4()
        info = fake.seed("s", "pk_existing", org_id=org, expires_at=EXPIRES, scopes=["a"])
        assert fake.find_by_secret("s", "pk_existing") == info
        assert fake.revoke("s", info.id, org_id=org) is True

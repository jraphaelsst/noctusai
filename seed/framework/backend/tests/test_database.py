"""``DatabaseModule.get_admin_client()`` must never leak ambient schema
state across callers.

🔴 THE REPRODUCED OUTAGE
-------------------------
``supabase.Client.schema(name)`` mutates the client's shared ``postgrest``
session IN PLACE and returns that same object — it is not an independent,
scoped client (verified against supabase-py 2.9.1 below). ``DatabaseModule``
caches ONE admin client per process, so a caller that does
``get_admin_client().schema("other_schema").table(...)`` (a real need —
minting a product token into ANOTHER product's schema) permanently
repoints the cached client. The NEXT caller that does a bare
``get_admin_client().table(...)`` — trusting the schema the module was
constructed for — silently hits the wrong schema instead. This is exactly
what took ``GET /api/agents`` down in prod with
``PGRST205: Could not find the table 'academia_de_reciclagem.
app_integration_config'``.

These tests pin the mechanism against a REAL ``supabase.Client`` (built
fully offline — construction never touches the network, only ``.execute()``
would) so the regression is proven against the actual library shape, not
just a hand-rolled fake of it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from noctusai_seed.database import DatabaseModule, _SchemaPinnedAdminClient


def _settings() -> SimpleNamespace:
    """Enough attributes for `DatabaseModule.get_client()` to build a real,
    offline `supabase.Client` — a JWT-*shaped* key satisfies the library's
    own format check without needing a live project."""
    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon.key.value",
        supabase_service_role_key="service.role.value",
    )


class TestClientDotSchemaReallyIsSharedMutableState:
    """Confirms the library behaviour the whole fix depends on — if a
    future supabase-py version changes this, these fail LOUDLY instead of
    the fix silently doing nothing."""

    def test_schema_mutates_and_returns_the_same_postgrest_object(self):
        db = DatabaseModule(_settings(), schema="agents")
        raw = db.get_client()
        before = raw.postgrest
        after = raw.schema("academia_de_reciclagem")
        assert after is before
        assert raw.options.schema == "academia_de_reciclagem"


class TestThePoisoningShapeIsDead:
    """The regression: a deliberate cross-schema call through
    `get_admin_client()` must not leak into the NEXT bare `.table()` call —
    on the SAME cached client, through a DIFFERENT `get_admin_client()`
    call, exactly like `SupabaseProductTokenAdmin` (mint into another
    product) followed later by `agents`' own `app_integration_config`
    read."""

    def test_a_cross_schema_call_does_not_poison_the_next_bare_table_call(self):
        db = DatabaseModule(_settings(), schema="agents")

        # A deliberate one-off cross-schema call — the token-mint shape.
        db.get_admin_client().schema("academia_de_reciclagem").table("api_tokens")

        # The NEXT caller never asked for a schema at all — the exact
        # `_LazyAgentsTable.table()` / `PgInteressadosStore` shape.
        admin = db.get_admin_client()
        builder = admin.table("app_integration_config")

        assert admin._pinned().options.schema == "agents"
        # A request builder carries no public schema attribute; assert via
        # the underlying client's pinned state instead — the builder was
        # built from a postgrest client we just proved is schema="agents".
        assert builder is not None

    def test_survives_repeated_interleaving(self):
        """Several rounds of cross-schema-then-bare, matching a process
        that serves both kinds of request concurrently."""
        db = DatabaseModule(_settings(), schema="agents")
        for _ in range(3):
            db.get_admin_client().schema("social_wiring").table("api_tokens")
            admin = db.get_admin_client()
            admin.table("app_integration_config")
            assert admin._pinned().options.schema == "agents"

    def test_get_admin_client_caches_one_underlying_raw_client(self):
        """Two wrapper instances must share the SAME underlying client —
        otherwise the cache is defeated and every call pays connection
        setup cost again."""
        db = DatabaseModule(_settings(), schema="agents")
        first = db.get_admin_client()
        second = db.get_admin_client()
        assert first is not second  # a fresh wrapper is fine, it's stateless
        assert first._client is second._client  # the cached raw client is shared


class TestPassThroughBehaviour:
    """Everything that is not `.table()`/`.rpc()`/`.from_()`/`.schema()`
    must reach the real client untouched — this is a thin delegate, not a
    new client shape."""

    def test_isinstance_style_attribute_access_passes_through(self):
        db = DatabaseModule(_settings(), schema="agents")
        admin = db.get_admin_client()
        assert admin.auth is admin._client.auth
        assert admin.supabase_url == "https://example.supabase.co"

    def test_schema_escape_hatch_still_returns_a_usable_postgrest_client(self):
        db = DatabaseModule(_settings(), schema="agents")
        admin = db.get_admin_client()
        postgrest = admin.schema("academia_de_reciclagem")
        assert postgrest.table("api_tokens") is not None

    def test_rpc_re_pins_like_table_does(self):
        db = DatabaseModule(_settings(), schema="agents")
        admin = db.get_admin_client()
        admin.schema("social_wiring").table("api_tokens")
        admin.rpc("some_function", {"x": 1})
        assert admin._pinned().options.schema == "agents"

    def test_from_re_pins_like_table_does(self):
        db = DatabaseModule(_settings(), schema="agents")
        admin = db.get_admin_client()
        admin.schema("social_wiring").table("api_tokens")
        admin.from_("app_integration_config")
        assert admin._pinned().options.schema == "agents"


class TestDirectWrapperUnit:
    """The wrapper's own contract, isolated from `DatabaseModule` — a
    recording fake stands in for the supabase client so re-pin COUNT is
    directly observable (the `DatabaseModule` tests above prove it against
    the real library; these prove exactly how many times it fires)."""

    class _FakeClient:
        def __init__(self):
            self.postgrest = self.__class__._Postgrest()
            self.schema_calls = 0

        class _Postgrest:
            def __init__(self):
                self.schema_name = None

            def table(self, name):
                return ("table", self.schema_name, name)

            def from_(self, name):
                return ("from_", self.schema_name, name)

            def rpc(self, fn, params=None):
                return ("rpc", self.schema_name, fn, params)

        def schema(self, name):
            self.schema_calls += 1
            self.postgrest.schema_name = name
            return self.postgrest

        def table(self, name):
            return self.postgrest.table(name)

        def from_(self, name):
            return self.postgrest.from_(name)

        def rpc(self, fn, params=None):
            return self.postgrest.rpc(fn, params)

    def test_table_pins_before_delegating(self):
        raw = self._FakeClient()
        wrapped = _SchemaPinnedAdminClient(raw, "agents")
        result = wrapped.table("app_integration_config")
        assert result == ("table", "agents", "app_integration_config")

    def test_schema_other_does_not_change_the_wrapper_s_own_schema(self):
        raw = self._FakeClient()
        wrapped = _SchemaPinnedAdminClient(raw, "agents")
        wrapped.schema("academia_de_reciclagem").table("api_tokens")
        # the wrapper still re-pins to ITS OWN schema on the next bare call
        result = wrapped.table("app_integration_config")
        assert result == ("table", "agents", "app_integration_config")

    def test_rpc_and_from_also_pin(self):
        raw = self._FakeClient()
        wrapped = _SchemaPinnedAdminClient(raw, "mailing")
        raw.schema("other")  # simulate poisoning from an unrelated caller
        assert wrapped.rpc("fn", {"a": 1}) == ("rpc", "mailing", "fn", {"a": 1})
        raw.schema("other")
        assert wrapped.from_("t") == ("from_", "mailing", "t")

    def test_getattr_passes_through_unknown_attributes(self):
        raw = self._FakeClient()
        raw.auth = object()
        wrapped = _SchemaPinnedAdminClient(raw, "agents")
        assert wrapped.auth is raw.auth

    def test_missing_attribute_raises_like_a_normal_object(self):
        raw = self._FakeClient()
        wrapped = _SchemaPinnedAdminClient(raw, "agents")
        with pytest.raises(AttributeError):
            wrapped.definitely_not_a_real_attribute

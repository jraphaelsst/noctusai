"""`_LazyAgentsTable` — the exact call site the prod outage traced to.

``GET /api/agents`` returned 500 (``PGRST205: Could not find the table
'academia_de_reciclagem.app_integration_config'``) because the admin client
`_LazyAgentsTable.table()` reads through is a per-process cache, and
`SupabaseProductTokenAdmin` (minting/looking up a `pk_*` token into
`academia_de_reciclagem` or `social_wiring`) mutates that SAME cached
client's ambient schema via `client.schema(other)` — a real supabase-py
behaviour, not a bug in that class. The seed-level fix
(`noctusai_seed.database._SchemaPinnedAdminClient`) closes this for every
`get_admin_client()` caller fleet-wide; this test pins the belt-and-braces
half living in THIS module — `_LazyAgentsTable.table()` explicitly asks
for the `agents` schema rather than trusting ambient state, so even a
future caller that reaches the admin client through something OTHER than
`DatabaseModule.get_admin_client()` cannot resurrect this outage here.

DI-only — no monkeypatching of our own code: `app.dependencies._db` is the
product's own `DatabaseModule` instance, and its cache slot (`_admin`) is
plain object state, the same seam the class's own docstring names
("nothing is built at import, and a test that swaps the database module's
client is honoured").
"""
from __future__ import annotations

import app.dependencies as deps
from app.credentials.resolver import _LazyAgentsTable


class _FakePoisonableClient:
    """Stands in for `supabase.Client`: `.schema()` mutates ambient state
    and returns `self` (matching the real library's `.schema()` returning
    the same postgrest client back, not a scoped copy)."""

    def __init__(self, initial_schema: str) -> None:
        self.schema_name = initial_schema
        self.schema_calls: list[str] = []

    def schema(self, name: str) -> "_FakePoisonableClient":
        self.schema_calls.append(name)
        self.schema_name = name
        return self

    def table(self, name: str) -> tuple[str, str]:
        return (self.schema_name, name)


def _install_fake_admin_client(monkeypatch, fake: _FakePoisonableClient) -> None:
    """The DI seam: swap the `DatabaseModule`'s own cache slot, not a
    function. `get_admin_client()` still runs unmodified and wraps
    whatever raw client the cache holds."""
    monkeypatch.setattr(deps._db, "_admin", fake, raising=False)


class TestLazyAgentsTablePinsItsOwnSchema:
    def test_targets_agents_even_when_the_cached_client_arrives_poisoned(
        self, monkeypatch
    ):
        # Simulate the exact prod sequence: a prior `SupabaseProductTokenAdmin`
        # call already repointed the shared cached admin client.
        fake = _FakePoisonableClient(initial_schema="academia_de_reciclagem")
        _install_fake_admin_client(monkeypatch, fake)

        result = _LazyAgentsTable().table("app_integration_config")

        assert result == ("agents", "app_integration_config")

    def test_still_targets_agents_when_the_cache_arrives_clean(self, monkeypatch):
        fake = _FakePoisonableClient(initial_schema="agents")
        _install_fake_admin_client(monkeypatch, fake)

        result = _LazyAgentsTable().table("app_integration_config")

        assert result == ("agents", "app_integration_config")
        # exactly one explicit pin — not relying on the client already
        # happening to be correct
        assert fake.schema_calls == ["agents"]

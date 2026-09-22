"""
Database client factories for NoctusAI products.

Every product needs:
  - A client targeting its own schema (for product tables)
  - A client targeting the public schema (for core platform tables)
  - An admin client (service role, bypasses RLS)

Usage::

    from noctusai_seed import create_database_module

    db = create_database_module(settings, schema="mailing")

    # In routers/services:
    client = db.get_client(token)       # user-authenticated
    admin = db.get_admin_client()        # service role
    core = db.get_core_client()          # public schema
"""
from typing import Any, Optional
from supabase import Client
from noctusai_lib.integrations.database import make_supabase_client

__all__ = ["DatabaseModule", "create_database_module"]


class _SchemaPinnedAdminClient:
    """Wraps a cached admin :class:`~supabase.Client` and re-pins ITS OWN
    schema on every ``.table()`` / ``.rpc()`` / ``.from_()`` access.

    🔴 WHY THIS EXISTS — A REPRODUCED PRODUCTION OUTAGE (agents, 2026-09-22)
    -------------------------------------------------------------------
    ``supabase.Client.schema(name)`` does NOT return an independent client —
    it MUTATES the shared ``client.postgrest`` session in place (sets
    ``Accept-Profile``/``Content-Profile``) and returns that same object
    (verified on supabase-py 2.9.1: ``c.schema("x") is c.postgrest`` →
    ``True``). ``DatabaseModule.get_admin_client()`` caches ONE admin client
    per process, so any caller that does ``get_admin_client().schema(
    "other_schema").table(...)`` (a real, legitimate need — e.g. minting a
    product token into ANOTHER product's schema, see
    ``noctusai_lib.api.auth.session.token_admin.SupabaseProductTokenAdmin``)
    permanently repoints the cached client. Every LATER caller in the same
    process that does a bare ``get_admin_client().table(...)`` — trusting
    the schema the client was constructed with — silently hits the WRONG
    schema instead. In prod this surfaced as
    ``PGRST205: Could not find the table 'academia_de_reciclagem.
    app_integration_config'`` on ``GET /api/agents`` — the ``agents``
    schema's own config table, reached through a client a token-mint call
    had repointed to ``academia_de_reciclagem`` moments earlier. The same
    shape was independently live in academia-de-reciclagem
    (``app/interessados/pg.py`` / ``app/knowledge/pg.py`` call bare
    ``self._admin.table(...)`` while ``app/dependencies.py``'s
    ``_AgentsSchemaClient`` repoints the SAME cached admin client to the
    ``agents`` schema to read the §D approval-signing ring) — fixed here,
    at the one place both paths share, rather than patched twice.

    This wrapper closes it at the root: ``DatabaseModule.get_admin_client()``
    returns this instead of the raw client, so a bare ``.table()``/``.rpc()``/
    ``.from_()`` call ALWAYS re-pins to the schema this ``DatabaseModule``
    was constructed for first — no caller can be poisoned by another
    caller's mutation of the shared underlying client, no matter what order
    requests interleave in.

    ``.schema(other)`` keeps working for a deliberate one-off cross-schema
    call — it is passed straight through to the underlying client (mutating
    it, exactly as before) and returns the real ``postgrest`` client so the
    caller's immediate ``.table(...)``/``.rpc(...)`` chain lands on
    ``other``. That mutation no longer survives past the one call: the next
    access through THIS wrapper re-pins back to its own schema before
    touching the client at all.

    Every other attribute (``.auth``, ``.storage``, …) passes through
    unchanged via ``__getattr__`` — this is a thin delegate, not a new
    client shape.
    """

    #: ``__weakref__`` is NOT optional here: a raw ``supabase.Client`` is
    #: weak-referenceable, so consumers key ``weakref.WeakKeyDictionary``
    #: caches on it (social-wiring's ``certidoes/deps.py::storage_for`` and
    #: five sibling ``deps.py`` modules). A ``__slots__`` class without it
    #: raises ``TypeError: cannot create weak reference`` — which took
    #: ``GET /api/certidoes/consultas`` + ``/fila-tjsp`` to 500 in prod on
    #: 2026-09-22, minutes after this wrapper shipped. A wrapper must keep
    #: every capability of what it wraps, weak-referenceability included.
    __slots__ = ("_client", "_schema", "__weakref__")

    def __init__(self, client: Client, schema: str) -> None:
        self._client = client
        self._schema = schema

    def _pinned(self) -> Client:
        """Re-pin the underlying client to this wrapper's schema and
        return it. Idempotent — ``Client.schema()`` itself only mutates
        when the requested schema differs from the current one."""
        self._client.schema(self._schema)
        return self._client

    def table(self, table_name: str):
        return self._pinned().table(table_name)

    def from_(self, table_name: str):
        return self._pinned().from_(table_name)

    def rpc(self, fn: str, params: Optional[dict] = None):
        return self._pinned().rpc(fn, params)

    def schema(self, other_schema: str):
        """Deliberate cross-schema escape hatch — mutates the underlying
        client to ``other_schema`` for this ONE call and returns its
        ``postgrest`` client, exactly like the unwrapped
        ``supabase.Client.schema()`` would. Never re-pinned back to
        ``self._schema`` automatically: the caller is expected to finish
        its ``.table(...)``/``.rpc(...)`` chain immediately, the same way
        callers already do against the raw client today."""
        return self._client.schema(other_schema)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class DatabaseModule:
    """Encapsulates database client factories for a product schema."""

    def __init__(self, settings, schema: str):
        self._settings = settings
        self._schema = schema
        self._admin: Optional[Client] = None
        self._admin_pinned: Optional["_SchemaPinnedAdminClient"] = None

    @property
    def schema(self) -> str:
        """Public accessor for the product schema this module targets."""
        return self._schema

    def get_client(self, access_token: Optional[str] = None) -> Client:
        """Create a Supabase client targeting the product schema.

        Args:
            access_token: If provided, authenticates as this user (respects RLS).
                          If None, uses service role (admin access).
        """
        return make_supabase_client(
            url=self._settings.supabase_url,
            anon_key=self._settings.supabase_anon_key,
            service_role_key=self._settings.supabase_service_role_key,
            schema=self._schema,
            access_token=access_token,
        )

    def get_core_client(self) -> Client:
        """Create a Supabase client targeting the public schema.

        Used for platform-level tables (notifications, noctus_users, etc.).
        """
        return make_supabase_client(
            url=self._settings.supabase_url,
            anon_key=self._settings.supabase_anon_key,
            service_role_key=self._settings.supabase_service_role_key,
            schema="public",
        )

    def get_admin_client(self) -> "_SchemaPinnedAdminClient":
        """Get a cached admin client (service role, bypasses RLS).

        Returned wrapped in :class:`_SchemaPinnedAdminClient` — see its
        docstring. BOTH the raw client and its wrapper are cached, so every
        caller gets the SAME wrapper object: consumers key
        ``weakref.WeakKeyDictionary`` caches on this client (social-wiring's
        ``modules/*/deps.py``), and a fresh wrapper per call would miss that
        cache every time and let each entry be collected immediately.
        Behaves like a :class:`~supabase.Client` for every method a caller
        actually uses (``.table()``/``.rpc()``/``.from_()``/``.schema()``
        plus passthrough of everything else) — no consumer needs to change.
        """
        if self._admin is None:
            self._admin = self.get_client()
        if self._admin_pinned is None:
            self._admin_pinned = _SchemaPinnedAdminClient(self._admin, self._schema)
        return self._admin_pinned


def create_database_module(settings, schema: str) -> DatabaseModule:
    """Factory to create database module for a product.

    Args:
        settings: Product settings instance (must have supabase_url, etc.)
        schema: Database schema name (e.g. "mailing", "erp", "therapy")
    """
    return DatabaseModule(settings, schema)

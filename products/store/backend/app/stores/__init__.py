"""Data-access seams for the store: Protocol + Supabase (Real) implementations.

The services depend on these Protocols, never on a Supabase client — so the
suite drives the real service logic against the in-memory Fakes in
`tests/support/fakes.py` (stateful, so idempotency / counters / versioning are
exercised for real, not asserted off a stateless mock). The Real stores are
thin and shape-tested against `MockSupabaseClient`.

All access is through the ADMIN (service-role) client: the store tables have
`service_role_bypass` only, no browser-role policy.
"""
from app.stores.protocols import PedidoStore, SettingsStore, VersionConflict
from app.stores.supabase import SupabasePedidoStore, SupabaseSettingsStore

__all__ = [
    "PedidoStore",
    "SettingsStore",
    "SupabasePedidoStore",
    "SupabaseSettingsStore",
    "VersionConflict",
]

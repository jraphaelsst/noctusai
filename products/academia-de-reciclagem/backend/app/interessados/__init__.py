"""academia-de-reciclagem interessados data layer -- public "receber
futuras comunicacoes" signup (see
`products/academia-de-reciclagem/projects/interessados-CONTRACT.md`).

Exports the `InteressadosStore` Protocol, both concrete implementations,
and the `build_interessados_store` factory the routers consume via
`app.dependencies.get_interessados_store`.
"""
from __future__ import annotations

from app.interessados.fake import FakeInteressadosStore
from app.interessados.pg import PgInteressadosStore
from app.interessados.store import InteressadosStore

__all__ = [
    "InteressadosStore",
    "FakeInteressadosStore",
    "PgInteressadosStore",
    "build_interessados_store",
]


def build_interessados_store(settings) -> InteressadosStore:
    """Return the configured `InteressadosStore` for this process.

    Mirrors `app.knowledge.get_knowledge_store`'s own prod/dev decision
    (see that function's docstring for the full rationale): `sqlite` ->
    the Fake, `supabase` (default) -> the real store over an
    admin-client-scoped `academia_de_reciclagem` schema, and an
    unconfigured prod raises rather than silently falling back to the
    Fake.
    """
    from noctusai_seed import create_database_module

    backend = getattr(settings, "database_backend", "supabase")

    if backend == "sqlite":
        return FakeInteressadosStore()

    if backend != "supabase":
        raise RuntimeError(
            f"build_interessados_store: unknown database_backend {backend!r} -- "
            "expected 'supabase' or 'sqlite'"
        )

    if not getattr(settings, "supabase_url", None) or not getattr(
        settings, "supabase_service_role_key", None
    ):
        raise RuntimeError(
            "build_interessados_store: database_backend='supabase' but "
            "supabase_url/supabase_service_role_key are not configured -- "
            "refusing to silently fall back to an in-memory store"
        )

    db = create_database_module(settings, schema="academia_de_reciclagem")
    return PgInteressadosStore(db.get_admin_client())

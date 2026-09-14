"""academia-de-reciclagem knowledge data layer — contract §A.

Exports the `KnowledgeStore` Protocol + `Provenance`, the error taxonomy,
both concrete implementations, and the `get_knowledge_store` factory A2 and
the (future) B-routes slice consume.
"""
from __future__ import annotations

from app.knowledge.errors import AssertionUsed, Conflict, Invalid, KnowledgeStoreError, NotFound
from app.knowledge.fake import FakeKnowledgeStore
from app.knowledge.pg import PgKnowledgeStore
from app.knowledge.store import KnowledgeStore, Provenance

__all__ = [
    "KnowledgeStore",
    "Provenance",
    "KnowledgeStoreError",
    "NotFound",
    "Conflict",
    "Invalid",
    "AssertionUsed",
    "FakeKnowledgeStore",
    "PgKnowledgeStore",
    "get_knowledge_store",
]


def get_knowledge_store(settings) -> KnowledgeStore:
    """Return the configured `KnowledgeStore` for this process.

    Mirrors how `noctusai_seed.database`/`select_get_current_user` decide
    prod vs. dev today: `settings.database_backend` defaults to
    `"supabase"` (real Postgres via PostgREST) and is set to `"sqlite"`
    only as an explicit, `debug`-gated local-dev opt-in
    (`noctusai_seed.config.validate_database_backend` refuses `sqlite` in a
    prod-shaped env, so this factory never has to re-check that itself).

    An unconfigured prod (`database_backend == "supabase"` but no
    `supabase_url`/`supabase_service_role_key`) raises — it never silently
    falls back to the Fake, which would look like a working knowledge
    base and quietly discard every write.
    """
    from noctusai_seed import create_database_module

    backend = getattr(settings, "database_backend", "supabase")

    if backend == "sqlite":
        return FakeKnowledgeStore()

    if backend != "supabase":
        raise RuntimeError(
            f"get_knowledge_store: unknown database_backend {backend!r} — "
            "expected 'supabase' or 'sqlite'"
        )

    if not getattr(settings, "supabase_url", None) or not getattr(settings, "supabase_service_role_key", None):
        raise RuntimeError(
            "get_knowledge_store: database_backend='supabase' but "
            "supabase_url/supabase_service_role_key are not configured — "
            "refusing to silently fall back to an in-memory store"
        )

    db = create_database_module(settings, schema="academia_de_reciclagem")
    return PgKnowledgeStore(db.get_admin_client())

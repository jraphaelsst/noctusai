"""Persistence wiring for IgIg domain data.

**Supabase is production.** IgIg is a standard noc product: domain data lives
in the `igig` Postgres schema, reached through the seed's
``create_database_module()`` clients, with RLS as the real tenant boundary.
The `noctusai_lib.integrations.persistence` seam sits in between so
repositories never speak PostgREST directly — and so tests can run against a
genuine SQLite database instead of a mock.

Two request scopes, deliberately distinct:

* :func:`get_repositorios` — authenticated routers. The caller is
  authenticated by ``get_current_user_org`` and the client is the SERVICE-ROLE
  one: the ``igig`` schema is service-role only (migration 044 revokes every
  browser grant and policy), so a user-token client could read nothing. The
  tenant boundary is the explicit ``org_id`` on every repository call.
* :func:`get_repositorios_admin` — same client, for the public approval portal,
  whose caller is the agency's client and has no noc account (and therefore no
  org to scope by). Security there is the token itself; see
  ``app/routers/esteira_router.py``. Kept as its own dependency so a route
  that opts out of the session says so in its signature.

`org_id` is passed explicitly on every repository call -- with the schema
closed to the browser that is THE tenant boundary, not defence-in-depth.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends
from noctusai_lib.integrations.persistence import RecordStore, get_record_store

from app.database import get_admin_client
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios

logger = logging.getLogger(__name__)

__all__ = [
    "get_repositorios",
    "get_repositorios_admin",
    "make_store",
    "sqlite_migrations",
    "aplicar_schema_sqlite",
]

_SQLITE_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "sqlite"


def make_store() -> RecordStore:
    """Build a Supabase-backed store on the service-role client.

    The ``igig`` schema is closed to the browser (migration 044), so there is
    no user-token variant: callers authenticate at the router and scope every
    query by ``org_id``.
    """
    return get_record_store(supabase_client=get_admin_client())


def get_repositorios(auth: tuple = Depends(get_current_user_org)) -> Repositorios:
    """Repository set on the service-role client; ``auth`` gates the route."""
    return Repositorios(make_store())


def get_repositorios_admin() -> Repositorios:
    """Repository set for the public portal (no noc session).

    Kept as its own dependency rather than a flag so that a route opting out
    of the session has to say so explicitly in its signature, where a reviewer sees it.
    """
    return Repositorios(make_store())


# ── SQLite — tests only ─────────────────────────────────────────────
def sqlite_migrations() -> list[Path]:
    """Every SQLite migration, in filename order.

    Each file mirrors its canonical Postgres counterpart (`006` ↔ `006`), and
    `tests/test_schema_parity.py` fails if the two sets drift.
    """
    if not _SQLITE_MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(f"SQLite migrations dir missing at {_SQLITE_MIGRATIONS_DIR}")
    arquivos = sorted(_SQLITE_MIGRATIONS_DIR.glob("*.sql"))
    if not arquivos:
        raise FileNotFoundError(f"no SQLite migrations found in {_SQLITE_MIGRATIONS_DIR}")
    return arquivos


def aplicar_schema_sqlite(store: RecordStore) -> None:
    """Apply the SQLite mirrors to a test store.

    Tests run against `SqliteRecordStore` rather than a mock: real SQL, real
    constraints, real FKs — closer to production than `MockSupabaseClient`,
    while staying hermetic. Production never calls this (a Supabase-backed
    store has no ``executescript``, so it is a no-op there by construction).
    """
    executescript = getattr(store, "executescript", None)
    if executescript is None:
        return
    for arquivo in sqlite_migrations():
        executescript(arquivo.read_text(encoding="utf-8"))

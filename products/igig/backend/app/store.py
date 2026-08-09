"""Persistence wiring for IgIg domain data.

**Supabase is production.** IgIg is a standard noc product: domain data lives
in the `igig` Postgres schema, reached through the seed's
``create_database_module()`` clients, with RLS as the real tenant boundary.
The `noctusai_lib.integrations.persistence` seam sits in between so
repositories never speak PostgREST directly — and so tests can run against a
genuine SQLite database instead of a mock.

Two request scopes, deliberately distinct:

* :func:`get_repositorios` — USER-scoped. Built from the caller's JWT, so
  every query runs under RLS. This is what authenticated routers use.
* :func:`get_repositorios_admin` — SERVICE-ROLE, RLS bypassed. ONLY for the
  public approval portal, whose caller is the agency's client and has no noc
  account (and therefore no org to scope by). Security there is the token
  itself; see ``app/routers/esteira_router.py``. Mirrors the split Orbity
  already uses for the same surface.

`org_id` is still passed explicitly on every repository call. On the Postgres
path that is defence-in-depth behind RLS — it means a service-role client used
by the portal still cannot read across tenants.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends
from noctusai_lib.integrations.persistence import RecordStore, get_record_store

from app.database import get_admin_client, get_supabase_client
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


def make_store(token: str | None = None, *, admin: bool = False) -> RecordStore:
    """Build a Supabase-backed store.

    ``admin=True`` returns a service-role client (RLS bypassed) — reserved for
    the public portal. Otherwise the client is bound to ``token`` so RLS
    applies, which is the whole point of passing the user's JWT down.
    """
    client = get_admin_client() if admin else get_supabase_client(token)
    return get_record_store(supabase_client=client)


def get_repositorios(auth: tuple = Depends(get_current_user_org)) -> Repositorios:
    """Repository set bound to the caller's RLS-scoped client."""
    _user, token, _raw_org = auth
    return Repositorios(make_store(token))


def get_repositorios_admin() -> Repositorios:
    """Repository set on the service-role client — public portal ONLY.

    Kept as its own dependency rather than a flag so that a route opting out
    of RLS has to say so explicitly in its signature, where a reviewer sees it.
    """
    return Repositorios(make_store(admin=True))


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

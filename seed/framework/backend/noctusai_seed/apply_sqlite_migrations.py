"""Pre-seeded SQLite local-dev backend bootstrap — parallel to Postgres.

WHY
---
The seed promises "a scaffolded product runs end-to-end on day one".
``dev_auth.py`` shipped the *identity* half (a synthesized dev user),
but anything past ``/landing`` that touches an RLS-bound table still
needs a real DB row the dev identity resolves against. Without this,
a scaffolded product still requires a provisioned Supabase project to
exercise any data path in dev. This module is the *datastore* half:
it materializes a local SQLite file with the minimal identity-mirror
tables + the bootstrap rows the already-shipped ``_DevUser``
(``dev_auth.py``) expects, so the dev user is not 403'd.

DESIGN — a PARALLEL implementation, never a modification of the
Postgres path. Mirrors the "no monkey-patching, in production OR
tests" rule and ``dev_auth.py``: the Supabase/Postgres code stays
byte-for-byte untouched; this activates ONLY under the same
double-gate (``DATABASE_BACKEND=sqlite`` AND ``debug`` — enforced by
the ``validate_database_backend`` validator in ``config.py``, which
fails loud if ``sqlite`` is requested in a production-shaped env).

WHAT IT CREATES
---------------
A minimal mirror of the Supabase auth surface the seed reads:

  * ``auth_users``          — id, email, encrypted_password,
                              raw_app_meta_data, raw_user_meta_data,
                              created_at (mirrors ``auth.users``)
  * ``orgs``                — id, name, created_at
  * ``user_org_membership`` — user_id, org_id, role

plus the idempotent bootstrap rows (``INSERT OR IGNORE`` / upsert so
every run is safe): the dev org (``settings.local_dev_org_id`` or the
fixed sentinel), the dev user (``settings.local_dev_user_id`` /
``dev@noctusai.local`` / bcrypt("noctus-dev")), and the owner
membership binding them. The IDs match the ``_DevUser`` sentinels in
``dev_auth.py`` exactly so the synthesized identity resolves.

NOT AN IO SEAM
--------------
Pure bootstrap logic over the ``sqlite3`` stdlib — exempt from the
Protocol+Fake+Real adapter shape (a Fake here would exercise the same
code as the Real; the seed-fake-real exemption test). DDL reuses the
seed-lib SQL prelude where dialect-compatible; SQLite-incompatible
Postgres constructs (``gen_random_uuid()``, RLS policies, schemas) are
deliberately NOT replayed — the dev path bypasses JWT/RLS entirely
(``dev_auth.py`` synthesizes the user), so the mirror only needs the
rows, not the policy machinery.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Well-known dev identity sentinels — MUST stay in lockstep with
# `noctusai_seed.dev_auth._DevUser` defaults (dev_auth.py:124,129) and
# the frontend `auth.ts` synthetic-session sentinels.
_DEV_USER_ID_FALLBACK = "00000000-0000-0000-0000-0000000000de"
_DEV_ORG_ID_FALLBACK = "00000000-0000-0000-0000-0000000000a0"
_DEV_USER_EMAIL = "dev@noctusai.local"
_DEV_PASSWORD = "noctus-dev"  # local-dev only; never a real credential
_DEV_ORG_NAME = "NoctusAI Local Dev Org"

# Identity-mirror schema. Deliberately dialect-minimal: no
# `gen_random_uuid()` (Postgres-only), no RLS, no schemas — the dev
# path bypasses JWT/RLS so the mirror only carries the rows the
# seed's downstream resolvers read off the user/org.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    encrypted_password TEXT NOT NULL,
    raw_app_meta_data TEXT NOT NULL DEFAULT '{}',
    raw_user_meta_data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orgs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_org_membership (
    user_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    PRIMARY KEY (user_id, org_id)
);
"""


def _bcrypt_hash(password: str) -> str:
    """bcrypt the dev password. Local-dev only — the dev-auth path
    never actually verifies this (it synthesizes the user), but the
    column mirrors ``auth.users.encrypted_password`` so the row shape
    is faithful for any product code that reads it."""
    import bcrypt

    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def resolve_sqlite_path(settings, *, base_dir: Optional[Path] = None) -> Path:
    """Resolve the absolute SQLite file path from settings.

    ``settings.sqlite_db_path`` may be relative (default
    ``noctus-dev.sqlite3``); it resolves against ``base_dir`` (cwd by
    default) so the same config works from any product backend.
    """
    raw = getattr(settings, "sqlite_db_path", "noctus-dev.sqlite3")
    p = Path(raw)
    if p.is_absolute():
        return p
    return (base_dir or Path.cwd()) / p


def apply_sqlite_migrations(
    settings,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    """Create (idempotently) the local-dev SQLite file + bootstrap rows.

    Safe to call on EVERY boot: schema uses ``CREATE TABLE IF NOT
    EXISTS``; bootstrap rows use ``INSERT OR IGNORE`` + an explicit
    metadata refresh, so re-running never duplicates or drifts.

    Args:
        settings: product settings — read for ``database_backend``
            (must be ``"sqlite"``; raises otherwise — fail loud, no
            silent no-op), ``sqlite_db_path``, and the optional
            ``local_dev_user_id`` / ``local_dev_org_id`` pins.
        base_dir: directory relative paths resolve against (cwd
            default).

    Returns:
        The absolute path to the SQLite file.

    Raises:
        RuntimeError: if called when ``database_backend`` is not
            ``"sqlite"`` — refusing to silently materialize a dev DB
            in a non-sqlite env (silent side-effect = silent error).
    """
    backend = getattr(settings, "database_backend", "supabase")
    if backend != "sqlite":
        raise RuntimeError(
            "apply_sqlite_migrations() called but DATABASE_BACKEND is "
            f"{backend!r}, not 'sqlite'. Refusing to materialize a dev "
            "SQLite DB outside the sqlite backend (silent side-effect)."
        )

    db_path = resolve_sqlite_path(settings, base_dir=base_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    user_id = (
        getattr(settings, "local_dev_user_id", "") or _DEV_USER_ID_FALLBACK
    )
    org_id = (
        getattr(settings, "local_dev_org_id", "") or _DEV_ORG_ID_FALLBACK
    )
    app_meta = json.dumps({"provider": "seed-dev-auth"})
    user_meta = json.dumps({"org_id": org_id, "role": "owner"})

    logger.warning(
        "[SEED DEV DB] SQLite local-dev backend ACTIVE at %s — dev user "
        "%s (org=%s). This MUST be off in production.",
        db_path,
        _DEV_USER_EMAIL,
        org_id,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA_SQL)
        # Idempotent bootstrap. INSERT OR IGNORE makes re-runs no-ops on
        # the keyed rows; the follow-up UPDATEs keep metadata/role fresh
        # if the IDs were re-pinned via config between runs.
        conn.execute(
            "INSERT OR IGNORE INTO orgs (id, name) VALUES (?, ?)",
            (org_id, _DEV_ORG_NAME),
        )
        conn.execute(
            "INSERT OR IGNORE INTO auth_users "
            "(id, email, encrypted_password, raw_app_meta_data, "
            " raw_user_meta_data) VALUES (?, ?, ?, ?, ?)",
            (user_id, _DEV_USER_EMAIL, _bcrypt_hash(_DEV_PASSWORD),
             app_meta, user_meta),
        )
        conn.execute(
            "UPDATE auth_users SET raw_app_meta_data = ?, "
            "raw_user_meta_data = ? WHERE id = ?",
            (app_meta, user_meta, user_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_org_membership "
            "(user_id, org_id, role) VALUES (?, ?, 'owner')",
            (user_id, org_id),
        )
        conn.execute(
            "UPDATE user_org_membership SET role = 'owner' "
            "WHERE user_id = ? AND org_id = ?",
            (user_id, org_id),
        )
        conn.commit()
    finally:
        conn.close()

    return db_path

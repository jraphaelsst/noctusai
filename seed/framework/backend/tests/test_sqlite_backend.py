"""Tests for the pre-seeded SQLite local-dev backend.

The SQLite backend is a PARALLEL implementation, double-gated, hard-off
in production (same discipline as `dev_auth.py`). These pin:
  (a) the `DATABASE_BACKEND` config validator (allowed values + prod
      refusal — sqlite can NEVER activate in a non-debug env),
  (b) `apply_sqlite_migrations` creates the identity-mirror tables +
      bootstrap rows whose IDs match the `_DevUser` sentinels exactly,
  (c) idempotency — re-running never duplicates or drifts,
  (d) the Postgres/Supabase default path is unchanged,
  (e) `select_get_current_user` selection logic.
"""

from __future__ import annotations

import sqlite3

import pytest

from noctusai_seed.apply_sqlite_migrations import (
    _DEV_ORG_ID_FALLBACK,
    _DEV_USER_EMAIL,
    _DEV_USER_ID_FALLBACK,
    apply_sqlite_migrations,
)
from noctusai_seed.config import ProductSettings
from noctusai_seed.dev_auth import select_get_current_user


class _Settings:
    """Minimal settings stand-in (mirrors test_dev_auth._Settings)."""

    def __init__(
        self,
        *,
        database_backend="sqlite",
        seed_dev_auth=True,
        debug=True,
        sqlite_db_path="noctus-dev.sqlite3",
        local_dev_user_id="",
        local_dev_org_id="",
    ):
        self.database_backend = database_backend
        self.seed_dev_auth = seed_dev_auth
        self.debug = debug
        self.sqlite_db_path = sqlite_db_path
        self.local_dev_user_id = local_dev_user_id
        self.local_dev_org_id = local_dev_org_id


# ── (a) config validator ──────────────────────────────────────────────


class TestDatabaseBackendValidator:
    def test_default_is_supabase(self):
        s = ProductSettings(_env_file=None)
        assert s.database_backend == "supabase"

    def test_sqlite_allowed_in_debug(self):
        s = ProductSettings(_env_file=None, database_backend="sqlite", debug=True)
        assert s.database_backend == "sqlite"

    def test_sqlite_refused_in_production(self):
        # sqlite in a non-debug (production-shaped) env must fail loud.
        with pytest.raises(Exception, match="SECURITY ERROR"):
            ProductSettings(_env_file=None, database_backend="sqlite", debug=False)

    def test_unknown_value_rejected(self):
        with pytest.raises(Exception, match="must be one of"):
            ProductSettings(_env_file=None, database_backend="mysql", debug=True)


# ── (b)+(c) migrations: bootstrap rows + idempotency ──────────────────


class TestApplySqliteMigrations:
    def test_creates_tables_and_bootstrap_rows(self, tmp_path):
        s = _Settings(sqlite_db_path=str(tmp_path / "dev.sqlite3"))
        db = apply_sqlite_migrations(s)
        assert db.exists()

        conn = sqlite3.connect(str(db))
        try:
            user = conn.execute(
                "SELECT id, email FROM auth_users"
            ).fetchall()
            org = conn.execute("SELECT id FROM orgs").fetchall()
            mem = conn.execute(
                "SELECT user_id, org_id, role FROM user_org_membership"
            ).fetchall()
        finally:
            conn.close()

        # IDs must match the _DevUser sentinels (dev_auth.py) exactly so
        # the synthesized identity resolves against these rows.
        assert user == [(_DEV_USER_ID_FALLBACK, _DEV_USER_EMAIL)]
        assert org == [(_DEV_ORG_ID_FALLBACK,)]
        assert mem == [
            (_DEV_USER_ID_FALLBACK, _DEV_ORG_ID_FALLBACK, "owner")
        ]

    def test_idempotent_across_runs(self, tmp_path):
        s = _Settings(sqlite_db_path=str(tmp_path / "dev.sqlite3"))
        apply_sqlite_migrations(s)
        apply_sqlite_migrations(s)
        db = apply_sqlite_migrations(s)  # 3 runs

        conn = sqlite3.connect(str(db))
        try:
            n_users = conn.execute(
                "SELECT COUNT(*) FROM auth_users"
            ).fetchone()[0]
            n_orgs = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
            n_mem = conn.execute(
                "SELECT COUNT(*) FROM user_org_membership"
            ).fetchone()[0]
        finally:
            conn.close()
        assert (n_users, n_orgs, n_mem) == (1, 1, 1)

    def test_config_pins_override_sentinels(self, tmp_path):
        s = _Settings(
            sqlite_db_path=str(tmp_path / "dev.sqlite3"),
            local_dev_user_id="cfg-user",
            local_dev_org_id="cfg-org",
        )
        db = apply_sqlite_migrations(s)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT user_id, org_id FROM user_org_membership"
            ).fetchone()
        finally:
            conn.close()
        assert row == ("cfg-user", "cfg-org")

    def test_refuses_when_backend_not_sqlite(self, tmp_path):
        # No silent side-effect: refuse to materialize a dev DB unless
        # DATABASE_BACKEND=sqlite.
        s = _Settings(
            database_backend="supabase",
            sqlite_db_path=str(tmp_path / "dev.sqlite3"),
        )
        with pytest.raises(RuntimeError, match="not 'sqlite'"):
            apply_sqlite_migrations(s)


# ── (e) selector ──────────────────────────────────────────────────────


class TestSelectGetCurrentUser:
    def test_prod_path_returned_when_supabase(self):
        sentinel = object()
        s = _Settings(database_backend="supabase")
        assert select_get_current_user(s, sentinel) is sentinel

    def test_prod_path_returned_when_sqlite_but_dev_auth_off(self):
        # sqlite alone is NOT enough — the dev-auth double-gate must
        # also be on, else selecting the dev path is a silent backdoor.
        sentinel = object()
        s = _Settings(database_backend="sqlite", seed_dev_auth=False, debug=True)
        assert select_get_current_user(s, sentinel) is sentinel

    def test_dev_path_selected_when_sqlite_and_dev_auth_on(self):
        sentinel = object()
        s = _Settings(database_backend="sqlite", seed_dev_auth=True, debug=True)
        chosen = select_get_current_user(s, sentinel)
        # Not the prod sentinel — the dev-auth dependency was selected.
        assert chosen is not sentinel
        assert callable(chosen)

"""Shared fixtures for the n8n module test suite.

``app/main.py`` deliberately does NOT register the n8n module yet (a
peer branch is live in that file concurrently; the tech-lead wires
``MODULES`` at integration time — see the module docstring on
``app/modules/n8n/__init__.py``). This conftest mounts the three n8n
routers onto the shared ``app.main.app`` object IN-MEMORY at test-
collection time (``app.include_router(...)``) — this touches nothing
on disk, never edits ``main.py``, and is exactly what the tech-lead's
real wiring step will do at integration.

Every n8n route depends on the account service / admin-client-probe /
folders service / n8n-client-factory through DI seams
(``app.modules.n8n.services.account_resolver`` /
``app.modules.n8n.services.folders_service``). Rather than exercising
``MockSupabaseClient``'s generic chain-stub API for the arbitrary
queries those seams issue, this suite overrides all four seams to
point at a REAL, ephemeral SQLite-backed store per test (mirrors
``tests/services/test_integration_account_service.py``'s own
pattern — a real SQLite client catches actual write→read propagation
that a hand-mocked chain can silently paper over) plus a persistent
``FakeN8nClient`` instance so state (a tag just created, a workflow
just renamed) survives across the several client calls one test
makes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from app.main import app as _app
from app.modules.n8n.routers import folders as _folders_router_mod
from app.modules.n8n.routers import settings as _settings_router_mod
from app.modules.n8n.routers import workflows as _workflows_router_mod
from app.modules.n8n.services.account_resolver import (
    get_account_service,
    get_admin_client_dep,
    get_n8n_client_factory,
)
from app.modules.n8n.services.folders_service import FoldersService, get_folders_service
from app.services.integration_account_service import IntegrationAccountService
from app.sqlite_client import SQLiteClient

# ── mount the n8n routers onto the shared app object once, at import
# (collection) time — BEFORE any test's `client` fixture builds a
# TestClient around `app`. Idempotent-by-construction: this module is
# only ever imported once per pytest process (module caching).
_app.include_router(_workflows_router_mod.router)
_app.include_router(_settings_router_mod.router)
_app.include_router(_folders_router_mod.router)


_OTHER_ORG = UUID("00000000-0000-4000-8000-00000000a002")

# Matches MockUser(org_id="test-org-123")'s coerce_org_uuid(...) output —
# the `client` fixture (tests/conftest.py) always authenticates as this
# org. `coerce_org_uuid` (app/dependencies.py) derives a deterministic
# UUID via `uuid.uuid5(uuid.NAMESPACE_OID, "test-org-123")` for the
# non-UUID fixture org id — n8n fixtures seed THIS exact org so the
# authenticated `client` fixture and this suite's sqlite-backed
# services agree on "the caller's org".
_CALLER_ORG = UUID("48ab962b-ec86-517e-9e42-7b581f622377")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS integration_accounts (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    provider            TEXT NOT NULL,
    account_label       TEXT NOT NULL,
    encrypted_credential TEXT NOT NULL,
    metadata            TEXT NOT NULL DEFAULT '{}',
    is_default          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    marca_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'validated',
    channel_info        TEXT NOT NULL DEFAULT '{}',
    last_synced_at      TEXT,
    UNIQUE (org_id, provider, account_label)
);

CREATE TABLE IF NOT EXISTS n8n_folders (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    parent_id   TEXT,
    name        TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS n8n_workflow_placement (
    -- `id` is NOT part of the documented Postgres shape (PK is the
    -- composite (account_id, workflow_id), per migration 024's
    -- documented columns) — it exists here ONLY because SQLiteClient's
    -- dev-mode `_prepare_payload` unconditionally injects an `id` on
    -- every `.insert()` regardless of table (`app/sqlite_client.py`);
    -- production talks to the real Supabase client, which has no such
    -- behavior. Test-harness compatibility column, not a schema claim.
    id          TEXT,
    org_id      TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    folder_id   TEXT,
    PRIMARY KEY (account_id, workflow_id)
);
"""


@pytest.fixture
def n8n_sqlite(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "n8n_module.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    return SQLiteClient(db_path)


@pytest.fixture
def n8n_fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def n8n_account_service(n8n_sqlite: SQLiteClient, n8n_fernet_key: str) -> IntegrationAccountService:
    return IntegrationAccountService(n8n_sqlite, fernet=Fernet(n8n_fernet_key.encode("utf-8")))


@pytest.fixture
def n8n_folders_svc(n8n_sqlite: SQLiteClient) -> FoldersService:
    return FoldersService(n8n_sqlite)


class _FixedN8nClientFactory:
    """Callable ``(base_url, api_key) -> N8nClient`` returning the SAME
    ``FakeN8nClient`` regardless of args, so state persists across the
    several calls one test/route makes. Records the args it was called
    with for assertions (e.g. "was the freshly-saved base_url used")."""

    def __init__(self, client):
        self.client = client
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, base_url: str, api_key: str):
        self.calls.append((base_url, api_key))
        return self.client


@pytest.fixture
def n8n_env(client, n8n_sqlite, n8n_account_service, n8n_folders_svc):
    """The composed n8n test environment: wires all four DI seams to
    the sqlite-backed services + a persistent FakeN8nClient, and tears
    the overrides down after the test. Yields a small namespace:
    ``.client`` (the authenticated AuthClient — same one every other
    product suite uses), ``.svc``, ``.folders_svc``, ``.fake_client``,
    ``.factory`` (the ``_FixedN8nClientFactory`` — inspect ``.calls``),
    plus ``CALLER_ORG`` / ``OTHER_ORG`` constants for cross-org tests.
    """
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake_client = FakeN8nClient()
    factory = _FixedN8nClientFactory(fake_client)

    _app.dependency_overrides[get_account_service] = lambda: n8n_account_service
    # Same underlying sqlite store `n8n_account_service` writes through —
    # `resolve_n8n_account`'s 403-vs-404 probe needs to see the same rows.
    _app.dependency_overrides[get_admin_client_dep] = lambda: n8n_sqlite
    _app.dependency_overrides[get_folders_service] = lambda: n8n_folders_svc
    _app.dependency_overrides[get_n8n_client_factory] = lambda: factory

    class _Env:
        pass

    env = _Env()
    env.client = client
    env.svc = n8n_account_service
    env.folders_svc = n8n_folders_svc
    env.fake_client = fake_client
    env.factory = factory
    env.CALLER_ORG = _CALLER_ORG
    env.OTHER_ORG = _OTHER_ORG

    yield env

    for dep in (
        get_account_service,
        get_admin_client_dep,
        get_folders_service,
        get_n8n_client_factory,
    ):
        _app.dependency_overrides.pop(dep, None)


def make_n8n_account(
    svc: IntegrationAccountService,
    *,
    org_id: UUID = _CALLER_ORG,
    label: str = "Primary n8n",
    base_url: str | None = "https://n8n.example.com",
    api_key: str | None = "test-api-key",
    tag: dict | None = None,
    is_default: bool = True,
):
    """Create + return an n8n ``IntegrationAccount`` seeded via the
    real service (Fernet round-trip exercised, same as production).
    ``base_url``/``api_key`` = ``None`` produces an INCOMPLETE
    credential (424 paths). ``tag`` (``{"id", "name"}``) seeds the
    configured client tag via ``channel_info``."""
    credential: dict = {}
    if base_url is not None:
        credential["base_url"] = base_url
    if api_key is not None:
        credential["api_key"] = api_key
    account = svc.create_account(
        org_id=org_id,
        provider="n8n",
        account_label=label,
        credential_dict=credential,
        metadata={},
        is_default=is_default,
    )
    if tag is not None:
        from datetime import datetime, timezone

        account = svc.update_channel_info(
            account_id=account.id,
            org_id=org_id,
            channel_info={"tag": tag},
            status="validated",
            last_synced_at=datetime.now(timezone.utc),
        )
    return account


AUTH_HEADERS = {"Authorization": "Bearer test-token-valid"}


def delete_with_body(auth_client, url: str, json: dict):
    """``httpx.Client.delete()`` (what ``AuthClient.delete`` forwards
    to) does NOT accept a ``json=``/body kwarg in this httpx version —
    only the generic ``.request()`` does. The two DELETE-with-body
    endpoints (unassign, delete-workflow) need this helper instead of
    ``auth_client.delete(url, json=...)``. Flagged as an interesting
    finding — the wire contract (DELETE + JSON body) is fine; it's
    httpx's Python convenience wrapper that's the footgun.
    """
    return auth_client.raw().request("DELETE", url, json=json, headers=AUTH_HEADERS)

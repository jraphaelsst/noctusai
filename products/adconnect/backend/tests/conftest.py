"""
Pytest configuration and shared fixtures for AdConnect backend tests.

AdConnect uses the seed framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.

-----------------------------------------------------------------------------
Auth fixture pattern (Phase 1 of `adconnect-test-conftest-distributor-binding`)
-----------------------------------------------------------------------------
The `client` fixture yields an `AuthClient` whose underlying
`MockSupabaseClient.auth.get_user` is a `MagicMock` returning a fixed
`MockUser`. The mock IGNORES the bearer-token bytes — JWTs minted by tests
via `_make_token(...)` are decorative; the binding controls resolution.

To exercise role-gated routes (admin endpoints, distributor-scoped reads),
tests rebind the user_metadata via `bind_adconnect_user(client, role=..., distributor_id=...)`
or one of the higher-level fixtures `as_admin` / `as_customer` / `as_admin_other_org`.
This replaces the byte-identical `_bind_user_metadata` helper that was
duplicated across `test_cart_router.py`, `test_orders_router.py`, and
`test_financial_router.py` before the absorption (recurrence rule, N=3+).

Constants:
- `ORG_ID_BRAND` — canonical brand-org UUID used by router tests + admin DEFAULT_ORG_ID.
- `OTHER_ORG_ID` — used by tests asserting cross-org isolation.
- `DIST_A_ID` / `DIST_B_ID` — canonical distributor UUIDs.

See `products/adconnect/projects/adconnect-test-conftest-distributor-binding/PROJECT.md`
for the full design.
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path

_LIB = _Path(__file__).resolve().parents[4] / "seed" / "lib" / "backend"
if str(_LIB) not in _sys.path:
    _sys.path.insert(0, str(_LIB))
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)

from typing import Any, Optional

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401 — re-exported for test imports
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
    bind_user_metadata,
)


# ---------------------------------------------------------------------------
# Canonical AdConnect test-data identifiers
# ---------------------------------------------------------------------------
# Mirrors the literal at `app/routers/admin.py:DEFAULT_ORG_ID` so role-gated
# routes that filter by `user["org_id"]` see the same UUID the seeded data
# carries.
ORG_ID_BRAND = "00000000-0000-0000-0000-000000000001"
OTHER_ORG_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
DIST_A_ID = "11111111-1111-1111-1111-111111111111"
DIST_B_ID = "22222222-2222-2222-2222-222222222222"

# ---------------------------------------------------------------------------
# CHECK-constraint manifest (opt-in, narrow adoption)
# ---------------------------------------------------------------------------
# Mirrors the CHECK constraints declared in `migrations/001_adconnect.sql` on
# the rewards tables. Wiring this manifest through `MockSupabaseClient(
# validate_schema_constraints=True, manifest=...)` makes the mock raise
# `MockCheckViolation` when production code writes a literal outside the
# allowed set — the test-time analog of the real DB's CHECK enforcement.
#
# Closes the ADCO-REWARDS-STATUS-CHECK class: a service inserted
# `status='success'` into `recompensas_acumuladas` (CHECK allows only
# `('acumulado', 'resgatado', 'expirado')`); tests passed because the mock
# was permissive; the real DB rejected at deploy.
#
# Narrow adoption: only the two rewards tables are listed here. Other
# adconnect tables (distributors / pedidos / sellout / regras_recompensa)
# keep their writes unvalidated until a follow-up extends the manifest.
ADCONNECT_CHECK_MANIFEST = {
    "recompensas_acumuladas": {
        "tipo": ("cashback", "pontos"),
        "status": ("acumulado", "resgatado", "expirado"),
    },
    "resgates_recompensa": {
        "metodo": (
            "credito_em_pedido",
            "credito_em_fatura",
            "reembolso_pix",
            "outro",
        ),
        "status": ("pendente", "aprovado", "recusado", "pago"),
    },
}


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


# ---------------------------------------------------------------------------
# AdConnect-specific user_metadata binder
# ---------------------------------------------------------------------------


def bind_adconnect_user(
    client_or_mock,
    *,
    role: str = "customer",
    distributor_id: Optional[str] = None,
    org_id: str = ORG_ID_BRAND,
    user_id: Optional[str] = None,
    email: str = "u@dist.com",
    extra: Optional[dict[str, Any]] = None,
) -> MockUserResponse:
    """Re-bind the mock's `auth.get_user` to an AdConnect-shaped MockUser.

    Thin wrapper over `noctusai_lib.testing.bind_user_metadata` (Phase 2
    seed-lib primitive) that maps AdConnect's product-specific vocabulary:

      - ``role`` (``customer`` / ``admin`` / ``owner``) → ``user_metadata.role``.
      - ``distributor_id`` → ``user_metadata.extra["distributor_id"]``;
        AdConnect routers read it via ``user.user_metadata["distributor_id"]``
        (post-canonical migration 2026-05-11; the pre-migration shape
        surfaced it as ``user["distributorId"]`` dict-key).
      - ``org_id`` defaults to `ORG_ID_BRAND` (the canonical test brand).

    Distributor-scoped routes 403 when ``distributor_id`` is None.
    Pass `OTHER_ORG_ID` to exercise cross-org isolation.

    Returns the underlying `MockUserResponse` (test code can access `.user`).
    """
    metadata: dict[str, Any] = {}
    if distributor_id is not None:
        metadata["distributor_id"] = distributor_id
    if extra:
        metadata.update(extra)
    return bind_user_metadata(
        client_or_mock,
        role=role,
        org_id=org_id,
        user_id=user_id or f"user-{distributor_id or 'admin'}",
        email=email,
        extra_metadata=metadata or None,
    )


# ---------------------------------------------------------------------------
# Base client fixture — role-agnostic default
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Default test client.

    Yields an `AuthClient` whose mock returns a default `MockUser` with no
    `role` and no `distributor_id`. Suitable for:
      - Framework / health / team tests (don't gate by AdConnect roles).
      - Tests that re-bind the user themselves via `bind_adconnect_user(...)`.

    Tests that need a pre-bound role-aware user use the higher-level
    fixtures `as_admin`, `as_customer`, `as_admin_other_org` below.
    """
    # AdConnect's product tables live in `adconnect.<table>` — bind the mock
    # to that schema so column-validation lookups resolve against the
    # canonical migrations/001_adconnect.sql tables.
    #
    # validate_schema=False mirrors the pre-Phase-1 standalone fixtures
    # (rewards/sellout). Several tables (e.g. `relatorios_sellout`) carry an
    # `org_id` column at runtime that the migration doesn't declare —
    # canonical schema-drift candidate, tracked by an `adconnect-schema-
    # drift-reconciliation` follow-up project (mirrors the ERP precedent
    # at `products/erp-imobiliario/backend/tests/conftest.py:28`). Flip to
    # True once reconciliation lands.
    # CHECK-constraint validation is OPT-IN (narrow adoption: only the two
    # rewards tables in `ADCONNECT_CHECK_MANIFEST`). Other tables / columns
    # are unaffected. Closes ADCO-REWARDS-STATUS-CHECK class — writes that
    # PostgreSQL would reject now raise `MockCheckViolation` at test time.
    mock_sb = MockSupabaseClient(
        validate_schema=False,
        schema="adconnect",
        validate_schema_constraints=True,
        manifest=ADCONNECT_CHECK_MANIFEST,
    )
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id=ORG_ID_BRAND)
    ))

    # Two patch layers:
    #   1. Framework-level (DatabaseModule classmethods) — covers any code
    #      path that resolves the client lazily.
    #   2. Module-level binding patches — `app.database` re-exports
    #      `_db.get_admin_client` etc as module attributes at import time.
    #      The router modules import the NAME (`from ..database import
    #      get_admin_client`) — to redirect those to the mock we have to
    #      patch the names on app.database itself AND on each router that
    #      already bound them locally.
    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb), \
         patch("app.database.get_supabase_client", lambda: mock_sb), \
         patch("app.database.get_core_client", lambda: mock_sb), \
         patch("app.database.get_admin_client", lambda: mock_sb):

        # Importing main triggers the router-module imports, each of which
        # binds `get_admin_client = app.database.get_admin_client`. We
        # override those bindings AFTER import.
        from app.main import app
        from app.routers import products as _products_router
        from app.routers import distributors as _distributors_router

        with patch.object(_products_router, "get_admin_client", lambda: mock_sb), \
             patch.object(_distributors_router, "get_admin_client", lambda: mock_sb):

            # Per-fixture re-bind of the seed's consent module to THIS test's
            # mock_sb. Idempotent — safe even though AdConnect doesn't register
            # consent features yet. See KB § PATTERNS/testing.md § Consent-guard
            # product conftest pattern.
            bind_consent_module_to_mock(mock_sb)

            tc = TestClient(app)
            ac = AuthClient(tc, mock_sb)
            # Expose the binder as a method on the AuthClient for callsite
            # ergonomics: `client.bind(role="admin", distributor_id=...)`.
            ac.bind = lambda **kw: bind_adconnect_user(ac, **kw)  # type: ignore[attr-defined]
            yield ac


# ---------------------------------------------------------------------------
# Pre-bound convenience fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def as_admin(client):
    """`client` pre-bound as a brand-admin user (no distributor)."""
    bind_adconnect_user(client, role="admin", distributor_id=None)
    return client


@pytest.fixture
def as_customer(client):
    """`client` pre-bound as a customer with `DIST_A_ID` distributor."""
    bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
    return client


@pytest.fixture
def as_customer_b(client):
    """`client` pre-bound as a customer with `DIST_B_ID` distributor."""
    bind_adconnect_user(client, role="customer", distributor_id=DIST_B_ID)
    return client


@pytest.fixture
def as_admin_other_org(client):
    """`client` pre-bound as admin in a different org (cross-org isolation tests)."""
    bind_adconnect_user(client, role="admin", distributor_id=None, org_id=OTHER_ORG_ID)
    return client

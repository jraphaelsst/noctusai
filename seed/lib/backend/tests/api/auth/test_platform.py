"""Boundary tests for `noctusai_lib.api.auth.platform`.

Per `KB § PATTERNS/compliance/auth-boundary-false-green.md`: every
dependency's unauthenticated case asserts a STRICT `== 401` (never
`in (401, 403|404|422)`) — a real FastAPI app + `TestClient` exercises
the actual `make_get_auth_context` 401 path, not a hand-rolled stand-in
for it.

Role matrix (4 actor classes x 3 dependencies):
  - platform_admin: `noctus_users.role == "admin"` — satisfies
    ONLY `require_platform_admin`.
  - agency_admin: org owner/admin/manager — satisfies ONLY
    `require_org_admin`.
  - curator: holds the `sample:generic-grant` permission grant —
    satisfies ONLY `require_permission`.
  - member: satisfies NONE of the three.
Proves platform-admin and org-admin are genuinely distinct actors
(no accidental cascade either direction) and that a permission grant
never leaks into role-based authorization.

Plus a dedicated cross-org test: an org A admin must not satisfy
`require_org_admin` for org B.

No monkey-patching of our own modules; DI seams throughout.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.platform import (
    require_org_admin,
    require_permission,
    require_platform_admin,
)
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    FakeSessionStore,
    make_get_auth_context,
)
from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.testing import MockSupabaseClient

_PERMISSION = "sample:generic-grant"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeCoreClient:
    """`.from_(name)` shim over `MockSupabaseClient` — mirrors the
    `deps.get_core_client()` contract `resolve_platform_admin_role` /
    `resolve_org_role` expect (a `public`-schema-scoped client)."""

    def __init__(self, rows):
        self._sb = MockSupabaseClient(rows, validate_schema=False, schema="public")

    def from_(self, name):
        return self._sb.from_(name)


def _noctus_users_row(user_id: UUID, *, role: str, org_role: str) -> dict:
    return {"id": str(user_id), "role": role, "org_role": org_role}


# ---------------------------------------------------------------------------
# App wiring — one route per dependency, real `make_get_auth_context`
# ---------------------------------------------------------------------------


def _build_app(*, core_rows, permission_repo, target_org_id: UUID | None = None):
    session_store = FakeSessionStore()
    api_token_resolver = FakeApiTokenResolver()
    get_auth_context = make_get_auth_context(
        session_store=session_store,
        api_token_resolver=api_token_resolver,
    )
    core_client = _FakeCoreClient(core_rows)

    dep_platform_admin = require_platform_admin(
        get_auth_context=get_auth_context,
        get_core_client=lambda: core_client,
    )

    if target_org_id is not None:
        async def _get_target_org_id() -> UUID:
            return target_org_id

        dep_org_admin = require_org_admin(
            get_auth_context=get_auth_context,
            get_core_client=lambda: core_client,
            get_target_org_id=_get_target_org_id,
        )
    else:
        dep_org_admin = require_org_admin(
            get_auth_context=get_auth_context,
            get_core_client=lambda: core_client,
        )

    dep_permission = require_permission(
        _PERMISSION,
        get_auth_context=get_auth_context,
        get_permission_repo=lambda: permission_repo,
    )

    app = FastAPI()

    @app.get("/platform-admin")
    async def _platform_admin_route(ctx: AuthContext = Depends(dep_platform_admin)):
        return {"ok": True}

    @app.get("/org-admin")
    async def _org_admin_route(ctx: AuthContext = Depends(dep_org_admin)):
        return {"ok": True}

    @app.get("/permission")
    async def _permission_route(ctx: AuthContext = Depends(dep_permission)):
        return {"ok": True}

    return app, session_store, api_token_resolver


def _cookie_for(session_store: FakeSessionStore, *, user_id: UUID, org_id: UUID) -> dict:
    session_id = _run(
        session_store.create(
            user_id=user_id,
            org_id=org_id,
            supabase_refresh_token="rt",
            ttl_seconds=60,
        )
    )
    return {"nai_session": session_id}


# ---------------------------------------------------------------------------
# Strict 401 — unauthenticated caller, every dependency
# ---------------------------------------------------------------------------


class TestUnauthenticatedIsStrict401:
    """No credential at all — asserts `== 401`, never `in (401, 403|404|422)`."""

    def _app(self):
        app, _store, _resolver = _build_app(core_rows=[], permission_repo=FakePermissionGrantRepository())
        return app

    def test_platform_admin_route_401(self):
        client = TestClient(self._app())
        resp = client.get("/platform-admin")
        assert resp.status_code == 401

    def test_org_admin_route_401(self):
        client = TestClient(self._app())
        resp = client.get("/org-admin")
        assert resp.status_code == 401

    def test_permission_route_401(self):
        client = TestClient(self._app())
        resp = client.get("/permission")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Role matrix — 4 actor classes x 3 dependencies
# ---------------------------------------------------------------------------


class TestRoleMatrix:
    def setup_method(self):
        self.org_a = uuid4()
        self.platform_admin_id = uuid4()
        self.curator_id = uuid4()
        self.agency_admin_id = uuid4()
        self.member_id = uuid4()

        self.core_rows = [
            _noctus_users_row(self.platform_admin_id, role="admin", org_role="member"),
            _noctus_users_row(self.curator_id, role="user", org_role="member"),
            _noctus_users_row(self.agency_admin_id, role="user", org_role="admin"),
            _noctus_users_row(self.member_id, role="user", org_role="member"),
        ]
        self.permission_repo = FakePermissionGrantRepository()
        self.permission_repo.grant(self.curator_id, _PERMISSION)

        self.app, self.session_store, _resolver = _build_app(
            core_rows=self.core_rows, permission_repo=self.permission_repo
        )
        self.client = TestClient(self.app)

    def _cookie(self, user_id: UUID) -> dict:
        return _cookie_for(self.session_store, user_id=user_id, org_id=self.org_a)

    # -- platform_admin actor -------------------------------------------------

    def test_platform_admin_allowed_on_platform_admin_route(self):
        resp = self.client.get("/platform-admin", cookies=self._cookie(self.platform_admin_id))
        assert resp.status_code == 200

    def test_platform_admin_denied_on_org_admin_route(self):
        resp = self.client.get("/org-admin", cookies=self._cookie(self.platform_admin_id))
        assert resp.status_code == 403

    def test_platform_admin_denied_on_permission_route(self):
        resp = self.client.get("/permission", cookies=self._cookie(self.platform_admin_id))
        assert resp.status_code == 403

    # -- curator actor ---------------------------------------------------------

    def test_curator_denied_on_platform_admin_route(self):
        resp = self.client.get("/platform-admin", cookies=self._cookie(self.curator_id))
        assert resp.status_code == 403

    def test_curator_denied_on_org_admin_route(self):
        resp = self.client.get("/org-admin", cookies=self._cookie(self.curator_id))
        assert resp.status_code == 403

    def test_curator_allowed_on_permission_route(self):
        resp = self.client.get("/permission", cookies=self._cookie(self.curator_id))
        assert resp.status_code == 200

    # -- agency_admin actor ------------------------------------------------

    def test_agency_admin_denied_on_platform_admin_route(self):
        """🔴 The load-bearing assertion: an agency's own org-admin must
        NEVER satisfy the platform-admin gate."""
        resp = self.client.get("/platform-admin", cookies=self._cookie(self.agency_admin_id))
        assert resp.status_code == 403

    def test_agency_admin_allowed_on_org_admin_route(self):
        resp = self.client.get("/org-admin", cookies=self._cookie(self.agency_admin_id))
        assert resp.status_code == 200

    def test_agency_admin_denied_on_permission_route(self):
        resp = self.client.get("/permission", cookies=self._cookie(self.agency_admin_id))
        assert resp.status_code == 403

    # -- member actor ------------------------------------------------------

    def test_member_denied_on_platform_admin_route(self):
        resp = self.client.get("/platform-admin", cookies=self._cookie(self.member_id))
        assert resp.status_code == 403

    def test_member_denied_on_org_admin_route(self):
        resp = self.client.get("/org-admin", cookies=self._cookie(self.member_id))
        assert resp.status_code == 403

    def test_member_denied_on_permission_route(self):
        resp = self.client.get("/permission", cookies=self._cookie(self.member_id))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Cross-org — an org A admin must not satisfy require_org_admin for org B
# ---------------------------------------------------------------------------


class TestCrossOrgDenied:
    def test_org_a_admin_denied_for_org_b(self):
        org_a = uuid4()
        org_b = uuid4()
        admin_id = uuid4()
        core_rows = [_noctus_users_row(admin_id, role="user", org_role="owner")]

        app, session_store, _resolver = _build_app(
            core_rows=core_rows,
            permission_repo=FakePermissionGrantRepository(),
            target_org_id=org_b,  # the route operates on org B
        )
        client = TestClient(app)
        cookie = _cookie_for(session_store, user_id=admin_id, org_id=org_a)

        resp = client.get("/org-admin", cookies=cookie)

        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "cross_org_denied"

    def test_org_a_admin_allowed_for_own_org(self):
        org_a = uuid4()
        admin_id = uuid4()
        core_rows = [_noctus_users_row(admin_id, role="user", org_role="owner")]

        app, session_store, _resolver = _build_app(
            core_rows=core_rows,
            permission_repo=FakePermissionGrantRepository(),
            target_org_id=org_a,  # the route operates on the caller's OWN org
        )
        client = TestClient(app)
        cookie = _cookie_for(session_store, user_id=admin_id, org_id=org_a)

        resp = client.get("/org-admin", cookies=cookie)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# require_permission — a product (non-user) token has no user_id
# ---------------------------------------------------------------------------


class TestRequirePermissionProductTokenDenied:
    def test_product_token_has_no_user_id_denied(self):
        permission_repo = FakePermissionGrantRepository()
        app, _store, resolver = _build_app(core_rows=[], permission_repo=permission_repo)
        org_id = uuid4()
        resolver.register("pk_live_zzz", org_id=org_id, scopes=[])
        client = TestClient(app)

        resp = client.get("/permission", headers={"Authorization": "Bearer pk_live_zzz"})

        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "permission_denied"

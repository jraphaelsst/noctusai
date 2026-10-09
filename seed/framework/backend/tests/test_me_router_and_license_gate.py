"""Round 2 — ``/api/me/access`` and the license gate on a
real seed-mounted route. Fakes injected (``FakeLicenseChecker`` + a MockSupabase
core client) — no patching of our own code. Strict status codes."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate
from noctusai_lib.primitives.exceptions import http_exception_handler
from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.me_router import create_me_router

HOME = "00000000-0000-0000-0000-00000000000a"
TARGET = "00000000-0000-0000-0000-00000000000b"
ADMIN = "aaaaaaaa-0000-0000-0000-000000000001"
USER = "uuuuuuuu-0000-0000-0000-000000000002"

TOKENS = {"tok-admin": ADMIN, "tok-user": USER}


def _make(users, checker=None, slug="igig"):
    core = MockSupabaseClient()
    core.set_table_data("noctus_users", users)
    core.set_table_data("organizations", [{"id": HOME, "nome": "Casa"}, {"id": TARGET, "nome": "Cliente B"}])

    async def get_current_user(authorization: Optional[str] = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token ausente")
        uid = TOKENS.get(authorization[7:])
        if uid is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return SimpleNamespace(id=uid, user_metadata={}), authorization[7:]

    deps = SimpleNamespace(
        get_core_client=lambda: core,
        get_current_user=get_current_user,
        get_current_user_ungated=get_current_user,
    )
    configure_license_gate(slug, checker or FakeLicenseChecker(allow_all=False, licensed={(HOME, slug)}))
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(create_me_router(deps))

    guarded = make_get_current_user_org(
        get_current_user, lambda u: None, get_admin_client_fn=lambda: core
    )

    @app.get("/api/things")
    async def things(auth=Depends(guarded)):
        return {"org_id": auth[2]}

    @app.get("/api/public/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    yield
    configure_license_gate(None)


H_ADMIN = {"Authorization": "Bearer tok-admin"}
H_USER = {"Authorization": "Bearer tok-user"}
ADMIN_ROW = {"id": ADMIN, "org_id": HOME, "org_role": "admin", "role": "admin"}
USER_ROW = {"id": USER, "org_id": HOME, "org_role": "member", "role": "user"}


class TestAuthBoundary:
    def test_unauthenticated_is_401(self):
        assert _make([USER_ROW]).get("/api/me/access").status_code == 401

    def test_me_context_is_gone(self):
        # /api/me/context only fed the removed act-as banner (2026-10-07).
        assert _make([USER_ROW]).get("/api/me/context", headers=H_USER).status_code == 404


class TestMeAccess:
    def test_licensed_user_has_access(self):
        body = _make([USER_ROW]).get("/api/me/access", headers=H_USER).json()
        assert body["has_access"] is True
        assert body["product_slug"] == "igig"
        assert body["org"] == {"id": HOME, "nome": "Casa"}
        sel = body["org_selection"]
        assert (sel["available"], sel["required"], sel["acting"]) == (False, False, False)
        assert sel["org_role"] == "member"

    def test_unlicensed_user_gets_200_has_access_false_not_403(self):
        c = _make([USER_ROW], checker=FakeLicenseChecker(allow_all=False))
        resp = c.get("/api/me/access", headers=H_USER)
        assert resp.status_code == 200
        assert resp.json()["has_access"] is False

    def test_superadmin_is_judged_on_the_home_org(self):
        # No staff override: a license held by another org grants nothing.
        c = _make([ADMIN_ROW], FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
        body = c.get("/api/me/access", headers=H_ADMIN).json()
        assert body["has_access"] is False
        assert body["org"] == {"id": HOME, "nome": "Casa"}


class TestGateOnAuthenticatedRoutes:
    def test_unlicensed_org_gets_flat_403_body(self):
        c = _make([USER_ROW], checker=FakeLicenseChecker(allow_all=False))
        resp = c.get("/api/things", headers=H_USER)
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Sua organização não tem acesso a este produto.",
                               "code": "org_sem_licenca"}

    def test_public_routes_untouched(self):
        c = _make([USER_ROW], checker=FakeLicenseChecker(allow_all=False))
        assert c.get("/api/public/ping").status_code == 200

    def test_superadmin_always_resolves_to_home(self):
        checker = FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig"), (TARGET, "igig")})
        assert _make([ADMIN_ROW], checker).get("/api/things", headers=H_ADMIN).json()["org_id"] == HOME

    def test_core_exempt(self):
        c = _make([USER_ROW], checker=FakeLicenseChecker(allow_all=False), slug="core")
        assert c.get("/api/things", headers=H_USER).status_code == 200


class TestProductDependenciesBaseDep:
    """`ProductDependencies.get_current_user` is gated by construction;
    `get_current_user_ungated` is the explicit exemption."""

    def _deps(self, users, checker):
        from noctusai_seed.dependencies import ProductDependencies

        core = MockSupabaseClient()
        core.set_table_data("noctus_users", users)
        db = SimpleNamespace(
            get_core_client=lambda: core,
            get_client=lambda: SimpleNamespace(
                auth=SimpleNamespace(get_user=lambda t: SimpleNamespace(user=SimpleNamespace(id=USER, user_metadata={})))
            ),
        )
        configure_license_gate("igig", checker, get_core_client=lambda: core)
        return ProductDependencies(db)

    @pytest.mark.asyncio
    async def test_gated_denies_unlicensed(self):
        deps = self._deps([USER_ROW], FakeLicenseChecker(allow_all=False))
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user("Bearer t")
        assert exc.value.status_code == 403 and exc.value.detail["code"] == "org_sem_licenca"

    @pytest.mark.asyncio
    async def test_gated_allows_licensed(self):
        deps = self._deps([USER_ROW], FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        assert (await deps.get_current_user("Bearer t"))[1] == "t"

    @pytest.mark.asyncio
    async def test_ungated_passes_regardless(self):
        deps = self._deps([USER_ROW], FakeLicenseChecker(allow_all=False))
        assert (await deps.get_current_user_ungated("Bearer t"))[1] == "t"

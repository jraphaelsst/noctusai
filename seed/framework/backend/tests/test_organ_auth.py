"""`make_organ_auth` -- admin is decided in the SELECTED org, never the home-org role."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.organ_auth import make_organ_auth
from noctusai_seed.organs import MountedOrgan, mount_finance, mount_organs

HOME, OTHER = "org-home", "org-b"


def _core(role="owner"):
    sb = MockSupabaseClient()
    sb.set_table_data("noctus_users", [{"id": "u1", "org_id": HOME, "org_role": role, "role": "user"}])
    return sb


def _app(selected_org: str, role="owner"):
    core = _core(role)

    async def auth(authorization: str | None = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no auth")
        return (SimpleNamespace(id="u1"), "tok", selected_org)

    deps = make_organ_auth(auth, lambda: core, context="Teste")
    app = FastAPI()

    @app.get("/who")
    async def who(a=Depends(deps.auth)):
        return {"org": a[2], "admin": a.is_admin}

    @app.put("/w")
    async def w(a=Depends(deps.admin)):
        return {"ok": True}

    return TestClient(app)


H = {"Authorization": "Bearer x"}


def test_home_owner_is_admin_in_home_org():
    c = _app(HOME)
    assert c.get("/who", headers=H).json() == {"org": HOME, "admin": True}
    assert c.put("/w", headers=H).status_code == 200


def test_home_owner_selecting_another_org_is_not_admin_there():
    c = _app(OTHER)
    assert c.get("/who", headers=H).json() == {"org": OTHER, "admin": False}  # reads stay masked
    assert c.put("/w", headers=H).status_code == 403


def test_plain_member_is_not_admin_and_unauthenticated_is_401():
    c = _app(HOME, role="member")
    assert c.put("/w", headers=H).status_code == 403
    assert c.put("/w").status_code == 401


def test_mounted_finance_masks_and_refuses_for_home_owner_in_other_org():
    core = _core("owner")

    async def auth(authorization: str | None = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no auth")
        return (SimpleNamespace(id="u1"), "tok", OTHER)

    organ = mount_finance(schema="erp", auth_dependency=auth, get_admin_client=lambda: object(),
                          get_core_client=lambda: core)
    app = FastAPI()
    for r in organ:
        app.include_router(r)
    c = TestClient(app)
    assert c.put("/api/finance/dre-settings", headers=H, json={"tax_regime": "mei"}).status_code == 403
    assert c.get("/api/finance/exports/dre.csv", headers=H).status_code == 403
    assert c.get("/api/finance/reports/dre", headers=H).status_code == 403


def test_prefix_rebases_upload_overrides():
    organ = mount_finance(schema="erp", auth_dependency=lambda: None, get_admin_client=lambda: object(),
                          get_core_client=lambda: object(), prefix="/api/fin")
    assert set(organ.max_body_path_overrides) == {"/api/fin/entries/*/attachments", "/api/fin/statements"}


def test_mount_organs_refuses_conflicting_overrides():
    a = MountedOrgan("a", (), {"/x": 1})
    b = MountedOrgan("b", (), {"/x": 2})
    with pytest.raises(ValueError, match="conflicting"):
        mount_organs([a, b])
    assert mount_organs([a, MountedOrgan("c", (), {"/x": 1})])[1] == {"/x": 1}


# -- B3 sweep: the shared seed helpers decide admin IN the selected org --------------------------------------

from noctusai_lib.api.auth.session.scopes import (  # noqa: E402
    is_org_admin,
    make_require_org_admin,
    require_org_admin_role,
    resolve_org_role,
)


def test_helpers_with_org_id_fail_closed_on_org_mismatch():
    core = _core("owner")
    assert is_org_admin(core, "u1") is True  # legacy HOME predicate unchanged
    assert is_org_admin(core, "u1", org_id=HOME) is True
    assert is_org_admin(core, "u1", org_id=OTHER) is False
    assert resolve_org_role(core, "u1", org_id=OTHER) is None
    require_org_admin_role(core, "u1", "X", org_id=HOME)
    with pytest.raises(HTTPException) as e:
        require_org_admin_role(core, "u1", "X", org_id=OTHER)
    assert e.value.status_code == 403


def test_make_require_org_admin_uses_selected_org():
    core = _core("owner")
    sel = {"org": OTHER}

    async def auth(authorization: str | None = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no auth")
        return (SimpleNamespace(id="u1"), "tok", sel["org"])

    app = FastAPI()

    @app.put("/w")
    async def w(a=Depends(make_require_org_admin(auth, lambda: core))):
        return {"ok": True}

    c = TestClient(app)
    assert c.put("/w").status_code == 401
    assert c.put("/w", headers=H).status_code == 403
    sel["org"] = HOME
    assert c.put("/w", headers=H).status_code == 200

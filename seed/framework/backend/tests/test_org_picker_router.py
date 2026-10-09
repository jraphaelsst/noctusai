"""Platform org picker -- ``/api/me/org-choices`` + ``/api/me/org-choice`` + the
effective-org resolution on a real seed auth dependency. Fakes only (FakeOrgSelectionStore,
FakeLicenseChecker, MockSupabaseClient); strict status codes; no patching of our own code."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.api.auth.org_selection import FakeOrgSelectionStore
from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate
from noctusai_lib.primitives.exceptions import http_exception_handler
from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.me_router import create_me_router

HOME = "00000000-0000-0000-0000-00000000000a"
CLIENT_A = "00000000-0000-0000-0000-00000000000b"
CLIENT_Z = "00000000-0000-0000-0000-00000000000c"
UNLICENSED = "00000000-0000-0000-0000-00000000000d"
STAFF = "aaaaaaaa-0000-0000-0000-000000000001"
OWNER = "bbbbbbbb-0000-0000-0000-000000000002"
SESSION = "11111111-1111-1111-1111-111111111111"
OTHER_SESSION = "22222222-2222-2222-2222-222222222222"
SLUG = "igig"


def _jwt(sub: str, *, aal: str = "aal2", session_id: str = SESSION) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'aal': aal, 'session_id': session_id})}.sig"


USERS = [
    {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "admin"},
    {"id": OWNER, "org_id": CLIENT_A, "org_role": "owner", "role": "user"},
]


def _make(*, ready=True, users=None):
    core = MockSupabaseClient()
    core.set_table_data("noctus_users", users or USERS)
    core.set_table_data("organizations", [
        {"id": HOME, "nome": "NoctusAI", "is_platform": True},
        {"id": CLIENT_A, "nome": "Zeta Imob", "is_platform": False},
        {"id": CLIENT_Z, "nome": "Alfa Imob", "is_platform": False},
        {"id": UNLICENSED, "nome": "Sem Licenca", "is_platform": False},
    ])
    licensed = {(HOME, SLUG), (CLIENT_A, SLUG), (CLIENT_Z, SLUG)}
    store = FakeOrgSelectionStore(
        ready={SLUG} if ready else set(), staff={STAFF}, licensed=licensed,
        orgs={HOME: "NoctusAI", CLIENT_A: "Zeta Imob", CLIENT_Z: "Alfa Imob"},
        home_orgs={STAFF: HOME},
    )

    async def get_current_user(authorization: Optional[str] = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token ausente")
        token = authorization[7:]
        try:
            sub = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["sub"]
        except Exception:
            raise HTTPException(status_code=401, detail="Token inválido")
        return SimpleNamespace(id=sub, user_metadata={}), token

    deps = SimpleNamespace(
        get_core_client=lambda: core,
        get_current_user=get_current_user,
        get_current_user_ungated=get_current_user,
    )
    configure_license_gate(
        SLUG, FakeLicenseChecker(allow_all=False, licensed=licensed),
        selection_store=store, db_schema="igig", get_core_client=lambda: core,
    )
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(create_me_router(deps))
    guarded = make_get_current_user_org(
        get_current_user, lambda u: None, get_admin_client_fn=lambda: core
    )

    @app.get("/api/things")
    async def things(auth=Depends(guarded)):
        return {"org_id": auth[2]}

    return TestClient(app), store


@pytest.fixture(autouse=True)
def _reset():
    yield
    configure_license_gate(None)


def _h(sub: str, **kw) -> dict:
    return {"Authorization": f"Bearer {_jwt(sub, **kw)}"}


class TestBoundary:
    def test_no_token_is_401_everywhere(self):
        c, _ = _make()
        assert c.get("/api/me/org-choices").status_code == 401
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_A}).status_code == 401
        assert c.delete("/api/me/org-choice").status_code == 401

    def test_non_staff_is_403_not_platform_staff_on_all_three(self):
        c, store = _make()
        h = _h(OWNER)
        for resp in (
            c.get("/api/me/org-choices", headers=h),
            c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=h),
            c.delete("/api/me/org-choice", headers=h),
        ):
            assert resp.status_code == 403
            assert resp.json()["code"] == "not_platform_staff"
        assert store.rows == []

    def test_org_owner_is_never_staff_even_with_admin_org_role(self):
        users = [{"id": OWNER, "org_id": CLIENT_A, "org_role": "admin", "role": "user"}]
        c, _ = _make(users=users)
        assert c.get("/api/me/org-choices", headers=_h(OWNER)).json()["code"] == "not_platform_staff"

    def test_admin_role_in_a_non_platform_org_is_not_staff(self):
        users = [{"id": OWNER, "org_id": CLIENT_A, "org_role": "owner", "role": "admin"}]
        c, _ = _make(users=users)
        assert c.get("/api/me/org-choices", headers=_h(OWNER)).status_code == 403

    def test_staff_without_aal2_is_403_mfa_required(self):
        c, _ = _make()
        resp = c.get("/api/me/org-choices", headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"

    def test_product_not_ready_is_409(self):
        c, _ = _make(ready=False)
        resp = c.get("/api/me/org-choices", headers=_h(STAFF))
        assert resp.status_code == 409
        assert resp.json()["code"] == "product_not_ready"
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF)).status_code == 409


class TestChoices:
    def test_home_first_then_by_name_only_licensed_and_no_store(self):
        c, _ = _make()
        resp = c.get("/api/me/org-choices", headers=_h(STAFF))
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store"
        assert resp.json()["orgs"] == [
            {"id": HOME, "nome": "NoctusAI", "is_home": True},
            {"id": CLIENT_Z, "nome": "Alfa Imob", "is_home": False},
            {"id": CLIENT_A, "nome": "Zeta Imob", "is_home": False},
        ]


class TestSelectionLifecycle:
    def test_access_before_any_choice_requires_one(self):
        c, _ = _make()
        sel = c.get("/api/me/access", headers=_h(STAFF)).json()["org_selection"]
        assert (sel["available"], sel["required"], sel["acting"], sel["mfa_required"]) == (True, True, False, False)
        assert sel["org"]["id"] == HOME and sel["home_org"]["id"] == HOME and sel["selection_id"] is None

    def test_put_then_access_acts_as_owner_in_the_target(self):
        c, store = _make()
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        assert resp.status_code == 200
        sel = resp.json()["org_selection"]
        assert (sel["available"], sel["required"], sel["acting"]) == (True, False, True)
        assert sel["org"] == {"id": CLIENT_A, "nome": "Zeta Imob"}
        assert sel["home_org"]["id"] == HOME
        assert sel["org_role"] == "owner"
        assert sel["selection_id"] == store.rows[0]["id"]
        # the SAME effective org now reaches a real auth dependency
        assert c.get("/api/things", headers=_h(STAFF)).json() == {"org_id": CLIENT_A}

    def test_choosing_the_home_org_is_a_selection_but_not_acting(self):
        c, _ = _make()
        sel = c.put("/api/me/org-choice", json={"org_id": HOME}, headers=_h(STAFF)).json()["org_selection"]
        assert (sel["required"], sel["acting"]) == (False, False)
        assert sel["org"]["id"] == HOME

    def test_unlicensed_target_is_403_org_sem_licenca(self):
        c, store = _make()
        resp = c.put("/api/me/org-choice", json={"org_id": UNLICENSED}, headers=_h(STAFF))
        assert resp.status_code == 403
        assert resp.json()["code"] == "org_sem_licenca"
        assert store.rows == []

    def test_unknown_body_field_is_422(self):
        c, _ = _make()
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_A, "role": "x"}, headers=_h(STAFF))
        assert resp.status_code == 422

    def test_swap_replaces_the_live_selection(self):
        c, store = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=_h(STAFF))
        assert [r["ended_by"] for r in store.rows] == ["replaced", None]
        assert c.get("/api/things", headers=_h(STAFF)).json() == {"org_id": CLIENT_Z}

    def test_delete_ends_it_and_the_picker_is_required_again(self):
        c, store = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        assert c.delete("/api/me/org-choice", headers=_h(STAFF)).status_code == 204
        assert store.rows[0]["ended_by"] == "exit"
        sel = c.get("/api/me/access", headers=_h(STAFF)).json()["org_selection"]
        assert sel["required"] is True and sel["acting"] is False

    def test_a_selection_from_another_login_is_ignored(self):
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        h2 = _h(STAFF, session_id=OTHER_SESSION)
        sel = c.get("/api/me/access", headers=h2).json()["org_selection"]
        assert (sel["required"], sel["acting"]) == (True, False)
        assert c.get("/api/things", headers=h2).json() == {"org_id": HOME}

    def test_existing_selection_without_aal2_resolves_home_and_flags_mfa(self):
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        h1 = _h(STAFF, aal="aal1")
        sel = c.get("/api/me/access", headers=h1).json()["org_selection"]
        assert (sel["mfa_required"], sel["acting"]) == (True, False)
        assert c.get("/api/things", headers=h1).json() == {"org_id": HOME}

    def test_lapsed_target_license_ignores_the_selection(self):
        c, store = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        store.licensed.discard((CLIENT_A, SLUG))  # same set the license checker reads
        sel = c.get("/api/me/access", headers=_h(STAFF)).json()["org_selection"]
        assert (sel["required"], sel["acting"]) == (True, False)
        assert c.get("/api/things", headers=_h(STAFF)).json() == {"org_id": HOME}

    def test_product_not_ready_hides_the_picker_and_resolves_home(self):
        c, _ = _make(ready=False)
        sel = c.get("/api/me/access", headers=_h(STAFF)).json()["org_selection"]
        assert (sel["available"], sel["required"]) == (False, False)


class TestIntentPin:
    def test_mismatching_pin_is_409_org_selection_changed(self):
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        resp = c.get("/api/things", headers={**_h(STAFF), "X-Noctus-Acting-Org": CLIENT_Z})
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_changed"

    def test_matching_pin_passes(self):
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        resp = c.get("/api/things", headers={**_h(STAFF), "X-Noctus-Acting-Org": CLIENT_A.upper()})
        assert resp.status_code == 200
        assert resp.json() == {"org_id": CLIENT_A}

    def test_pin_for_an_org_when_resolving_home_is_409(self):
        c, _ = _make()
        resp = c.get("/api/things", headers={**_h(STAFF), "X-Noctus-Acting-Org": CLIENT_A})
        assert resp.status_code == 409

    def test_non_staff_pin_is_ignored(self):
        c, _ = _make()
        resp = c.get("/api/things", headers={**_h(OWNER), "X-Noctus-Acting-Org": CLIENT_Z})
        assert resp.status_code == 200
        assert resp.json() == {"org_id": CLIENT_A}

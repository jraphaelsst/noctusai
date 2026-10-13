"""Platform org picker -- ``/api/me/org-choices`` + ``/api/me/org-choice`` + the
effective-org resolution on a real seed auth dependency. Fakes only (FakeOrgSelectionStore,
FakeLicenseChecker, MockSupabaseClient); strict status codes; no patching of our own code."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.testclient import TestClient

from noctusai_lib.api.auth import make_get_current_user, make_get_current_user_org
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


def _make(*, ready=True, users=None, mfa_optional=False, members=None):
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
        mfa_optional={SLUG} if mfa_optional else set(),
        members=members if members is not None else {
            STAFF: {HOME: "owner"}, OWNER: {CLIENT_A: "owner"},
        },
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

    base = make_get_current_user(lambda: SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda t: SimpleNamespace(user=SimpleNamespace(
            id=json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "==") )["sub"], user_metadata={})))))

    @app.post("/api/base-write")
    async def base_write(request: Request, auth=Depends(base)):
        actor = getattr(request.state, "audit_actor", None)
        return {"org_id": getattr(actor, "org_id", None), "role": getattr(actor, "role", None),
                "acting_org_id": getattr(actor, "acting_org_id", None),
                "tag": getattr(actor, "act_as_session_id", None)}

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

    def test_non_member_is_403_not_a_member_on_put_and_never_sees_foreign_orgs(self):
        c, store = _make()
        h = _h(OWNER)
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=h)
        assert resp.status_code == 403
        assert resp.json()["code"] == "not_a_member"
        listed = c.get("/api/me/org-choices", headers=h).json()["orgs"]
        assert [o["id"] for o in listed] == [CLIENT_A]  # only the orgs they belong to
        assert c.delete("/api/me/org-choice", headers=h).status_code == 204
        assert store.rows == []

    def test_org_owner_is_never_staff_even_with_admin_org_role(self):
        users = [{"id": OWNER, "org_id": CLIENT_A, "org_role": "admin", "role": "user"}]
        c, _ = _make(users=users)
        listed = c.get("/api/me/org-choices", headers=_h(OWNER)).json()["orgs"]
        assert [o["id"] for o in listed] == [CLIENT_A]
        assert c.put("/api/me/org-choice", json={"org_id": HOME}, headers=_h(OWNER)).json()["code"] == "not_a_member"

    def test_admin_role_in_a_non_platform_org_is_not_staff(self):
        users = [{"id": OWNER, "org_id": CLIENT_A, "org_role": "owner", "role": "admin"}]
        c, _ = _make(users=users)
        assert c.put("/api/me/org-choice", json={"org_id": HOME}, headers=_h(OWNER)).status_code == 403

    def test_staff_without_aal2_is_403_mfa_required(self):
        c, _ = _make()
        resp = c.get("/api/me/org-choices", headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 403
        assert resp.json()["code"] == "mfa_required"

    def test_product_without_mfa_requirement_lets_aal1_staff_pick_and_act(self):
        """products.org_picker_requires_mfa = false (core 073, owner 2026-10-09): no aal2 needed."""
        c, store = _make(mfa_optional=True)
        assert c.get("/api/me/org-choices", headers=_h(STAFF, aal="aal1")).status_code == 200
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 200
        sel = c.get("/api/me/access", headers=_h(STAFF, aal="aal1")).json()["org_selection"]
        assert (sel["acting"], sel["mfa_required"], sel["org"]["id"]) == (True, False, CLIENT_A)

    def test_requirement_restored_stops_an_aal1_selection_resolving(self):
        """Flipping the flag back (the revisit trigger) falls an aal1 session back to home."""
        c, store = _make(mfa_optional=True)
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF, aal="aal1")).status_code == 200
        store.mfa_optional.clear()
        sel = c.get("/api/me/access", headers=_h(STAFF, aal="aal1")).json()["org_selection"]
        assert (sel["acting"], sel["mfa_required"], sel["org"]["id"]) == (False, True, HOME)

    def test_product_not_ready_is_409(self):
        c, _ = _make(ready=False)
        resp = c.get("/api/me/org-choices", headers=_h(STAFF))
        assert resp.status_code == 409
        assert resp.json()["code"] == "product_not_ready"
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF)).status_code == 409


class TestChoices:
    def test_clients_by_name_then_home_last_only_licensed_and_no_store(self):
        c, _ = _make()
        resp = c.get("/api/me/org-choices", headers=_h(STAFF))
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store"
        assert resp.json()["orgs"] == [
            {"id": CLIENT_Z, "nome": "Alfa Imob", "is_home": False},
            {"id": CLIENT_A, "nome": "Zeta Imob", "is_home": False},
            {"id": HOME, "nome": "NoctusAI", "is_home": True},
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
        resp = c.get("/api/things", headers=h2)
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_required"

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
        resp = c.get("/api/things", headers=_h(STAFF))
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_required"

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

    def test_pin_for_an_org_whose_selection_ended_is_409_org_selection_changed(self):
        c, _ = _make()
        resp = c.get("/api/things", headers={**_h(STAFF), "X-Noctus-Acting-Org": CLIENT_A})
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_changed"

    def test_non_staff_pin_only_narrows(self):
        c, _ = _make()
        resp = c.get("/api/things", headers={**_h(OWNER), "X-Noctus-Acting-Org": CLIENT_Z})
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_changed"
        ok = c.get("/api/things", headers={**_h(OWNER), "X-Noctus-Acting-Org": CLIENT_A})
        assert ok.status_code == 200
        assert ok.json() == {"org_id": CLIENT_A}


class TestStaffEligibilityAndBody:
    def test_platform_admin_with_a_lesser_org_role_is_not_staff(self):
        users = [{"id": STAFF, "org_id": HOME, "org_role": "manager", "role": "admin"}]
        c, store = _make(users=users)
        store.staff.discard(STAFF)  # the real RPC derives staff from the profile (manager is not)
        # Not staff: a plain member of HOME -- sees only HOME, no aal2 asked, no switcher.
        resp = c.get("/api/me/org-choices", headers=_h(STAFF, aal="aal1"))
        assert [o["id"] for o in resp.json()["orgs"]] == [HOME]
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF)).json()["code"] == "not_a_member"
        assert c.get("/api/me/access", headers=_h(STAFF)).json()["org_selection"]["available"] is False

    def test_org_id_must_be_a_uuid(self):
        c, store = _make()
        resp = c.put("/api/me/org-choice", json={"org_id": "not-a-uuid"}, headers=_h(STAFF))
        assert resp.status_code == 422
        assert store.rows == []


class TestDeleteAll:
    def test_all_true_ends_every_products_selection_as_logout(self):
        c, store = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        store.rows.append({"id": "x", "user_id": STAFF, "slug": "other", "target": CLIENT_A,
                           "home": HOME, "session": SESSION, "ended_by": None})
        assert c.delete("/api/me/org-choice?all=true", headers=_h(STAFF)).status_code == 204
        assert [r["ended_by"] for r in store.rows] == ["logout", "logout"]

    def test_all_true_only_ever_ends_the_callers_own_selections(self):
        c, store = _make()
        store.rows.append({"id": "x", "user_id": STAFF, "slug": SLUG, "target": CLIENT_A,
                           "home": HOME, "session": SESSION, "ended_by": None})
        assert c.delete("/api/me/org-choice?all=true", headers=_h(OWNER)).status_code == 204
        assert store.rows[0]["ended_by"] is None  # a member cannot end the staff member's selection


class TestActingWritesAreClientVisible:
    """Every FastAPI write while acting -- including through the BASE auth dependency
    (no org lookup) -- carries org_id = target, role platform_support, home + selection tags."""

    def test_base_dep_stashes_the_acting_actor(self):
        c, store = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        body = c.post("/api/base-write", headers=_h(STAFF)).json()
        assert body == {"org_id": CLIENT_A, "role": "platform_support", "acting_org_id": HOME,
                        "tag": store.rows[0]["id"]}

    def test_base_dep_for_an_ordinary_user_has_no_acting_tags(self):
        c, _ = _make()
        body = c.post("/api/base-write", headers=_h(OWNER)).json()
        assert body["tag"] is None and body["role"] is None


class TestEveryEntryRequiresAChoice:
    """Owner decision 2026-10-12: staff never silently land in the home org. Without a
    live selection every GATED route refuses 409 org_selection_required; the ungated
    /api/me/* surface keeps answering so the picker can load."""

    def _required(self, resp) -> None:
        assert resp.status_code == 409
        assert resp.json()["code"] == "org_selection_required"

    def test_staff_without_selection_is_409_on_org_and_base_gated_routes(self):
        c, _ = _make()
        self._required(c.get("/api/things", headers=_h(STAFF)))
        self._required(c.post("/api/base-write", headers=_h(STAFF)))

    def test_me_access_still_answers_200_with_required_true(self):
        c, _ = _make()
        resp = c.get("/api/me/access", headers=_h(STAFF))
        assert resp.status_code == 200
        sel = resp.json()["org_selection"]
        assert (sel["available"], sel["required"], sel["selection_id"]) == (True, True, None)
        assert c.get("/api/me/org-choices", headers=_h(STAFF)).status_code == 200

    def test_with_a_selection_the_gated_route_resolves_the_target(self):
        c, _ = _make()
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=_h(STAFF)).status_code == 200
        resp = c.get("/api/things", headers=_h(STAFF))
        assert resp.status_code == 200
        assert resp.json() == {"org_id": CLIENT_Z}

    def test_choosing_home_explicitly_resolves_home(self):
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": HOME}, headers=_h(STAFF))
        resp = c.get("/api/things", headers=_h(STAFF))
        assert resp.status_code == 200
        assert resp.json() == {"org_id": HOME}

    def test_ending_the_selection_refuses_again(self):
        """The SPA entry handshake: DELETE on entry ends any selection left over."""
        c, _ = _make()
        c.put("/api/me/org-choice", json={"org_id": CLIENT_A}, headers=_h(STAFF))
        assert c.delete("/api/me/org-choice", headers=_h(STAFF)).status_code == 204
        self._required(c.get("/api/things", headers=_h(STAFF)))

    def test_non_staff_is_unaffected(self):
        c, _ = _make()
        resp = c.get("/api/things", headers=_h(OWNER))
        assert resp.status_code == 200
        assert resp.json() == {"org_id": CLIENT_A}
        assert c.post("/api/base-write", headers=_h(OWNER)).status_code == 200

    def test_non_ready_product_still_resolves_home(self):
        c, _ = _make(ready=False)
        resp = c.get("/api/things", headers=_h(STAFF))
        assert resp.status_code == 200
        assert resp.json() == {"org_id": HOME}

    def test_mfa_path_unchanged_aal1_staff_resolve_home(self):
        c, _ = _make()
        resp = c.get("/api/things", headers=_h(STAFF, aal="aal1"))
        assert resp.status_code == 200
        assert resp.json() == {"org_id": HOME}


MEMBER = "cccccccc-0000-0000-0000-000000000003"
MULTI = [{"id": MEMBER, "org_id": CLIENT_A, "org_role": "owner", "role": "user"}]
MULTI_MEMBERS = {MEMBER: {CLIENT_A: "owner", CLIENT_Z: "viewer"}}


class TestMemberPicker:
    """Multi-org S2 (owner decisions 2026-10-13): a regular member of >1 orgs uses the SAME
    picker endpoints -- no aal2, only their own (active, licensed) orgs, role = membership role."""

    def _c(self, **kw):
        return _make(users=MULTI, members={k: dict(v) for k, v in MULTI_MEMBERS.items()}, **kw)

    def test_choices_are_the_members_licensed_orgs_with_the_last_active_first_and_their_roles(self):
        c, _ = self._c()
        orgs = c.get("/api/me/org-choices", headers=_h(MEMBER, aal="aal1")).json()["orgs"]
        assert [(o["id"], o["is_home"], o["org_role"]) for o in orgs] == [
            (CLIENT_A, True, "owner"), (CLIENT_Z, False, "viewer")]

    def test_switching_needs_no_aal2_and_the_role_is_the_membership_role_in_the_target(self):
        c, store = self._c()
        h = _h(MEMBER, aal="aal1")
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=h)
        assert resp.status_code == 200
        sel = resp.json()["org_selection"]
        assert (sel["org"]["id"], sel["org_role"], sel["acting"], sel["available"]) == (
            CLIENT_Z, "viewer", False, True)
        assert store.last_active[MEMBER] == (CLIENT_Z, "viewer")
        # the gated route serves the selected org, not the (stale) profile org
        got = c.get("/api/things", headers={**h, "X-Noctus-Acting-Org": CLIENT_Z})
        assert got.json() == {"org_id": CLIENT_Z}

    def test_member_audit_actor_is_plain_not_platform_support(self):
        c, _ = self._c()
        h = _h(MEMBER, aal="aal1")
        c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=h)
        body = c.post("/api/base-write", headers=h).json()
        assert body["role"] is None and body["acting_org_id"] is None

    def test_a_member_cannot_select_an_unlicensed_member_org_nor_a_foreign_org(self):
        members = {MEMBER: {CLIENT_A: "owner", UNLICENSED: "viewer"}}
        c, store = _make(users=MULTI, members=members)
        h = _h(MEMBER, aal="aal1")
        r1 = c.put("/api/me/org-choice", json={"org_id": UNLICENSED}, headers=h)
        assert (r1.status_code, r1.json()["code"]) == (403, "org_sem_licenca")
        r2 = c.put("/api/me/org-choice", json={"org_id": HOME}, headers=h)
        assert (r2.status_code, r2.json()["code"]) == (403, "not_a_member")
        assert store.rows == []

    def test_ending_the_membership_ends_the_selection_on_the_next_request(self):
        c, store = self._c()
        h = _h(MEMBER, aal="aal1")
        c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=h)
        assert c.get("/api/things", headers=h).json() == {"org_id": CLIENT_Z}
        del store.members[MEMBER][CLIENT_Z]
        assert c.get("/api/things", headers=h).json() == {"org_id": CLIENT_A}

    def test_single_org_member_sees_no_picker_and_no_choice(self):
        c, _ = _make()  # OWNER: member of CLIENT_A only
        sel = c.get("/api/me/access", headers=_h(OWNER, aal="aal1")).json()["org_selection"]
        assert (sel["available"], sel["required"]) == (False, False)

    def test_multi_org_member_with_licensed_last_active_org_is_not_asked(self):
        c, _ = self._c()
        sel = c.get("/api/me/access", headers=_h(MEMBER, aal="aal1")).json()["org_selection"]
        assert (sel["available"], sel["required"]) == (True, False)
        assert c.get("/api/things", headers=_h(MEMBER, aal="aal1")).json() == {"org_id": CLIENT_A}

    def test_unlicensed_last_active_org_requires_a_choice_on_gated_routes_only(self):
        users = [{"id": MEMBER, "org_id": UNLICENSED, "org_role": "owner", "role": "user"}]
        members = {MEMBER: {UNLICENSED: "owner", CLIENT_Z: "viewer"}}
        c, _ = _make(users=users, members=members)
        h = _h(MEMBER, aal="aal1")
        gated = c.get("/api/things", headers=h)
        assert (gated.status_code, gated.json()["code"]) == (409, "org_selection_required")
        sel = c.get("/api/me/access", headers=h).json()
        assert (sel["has_access"], sel["org_selection"]["required"], sel["org_selection"]["available"]) == (
            False, True, True)
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=h).status_code == 200
        assert c.get("/api/things", headers=h).json() == {"org_id": CLIENT_Z}

    def test_product_not_ready_is_409_for_members_too(self):
        c, _ = self._c(ready=False)
        resp = c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}, headers=_h(MEMBER, aal="aal1"))
        assert (resp.status_code, resp.json()["code"]) == (409, "product_not_ready")

    def test_no_token_is_still_401_strict(self):
        c, _ = self._c()
        assert c.put("/api/me/org-choice", json={"org_id": CLIENT_Z}).status_code == 401
        assert c.get("/api/me/org-choices").status_code == 401
        assert c.get("/api/things").status_code == 401

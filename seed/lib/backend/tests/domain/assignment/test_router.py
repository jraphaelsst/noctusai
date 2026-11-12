"""The HTTP surface: strict 401 on EVERY route, 403 on admin writes, the owner-handoff rule, envelopes, org isolation."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.assignment import make_assignment_router
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import ADMIN, CARD1, CARD2, ORG_A, ORG_B, U1, U2, Env

TEAM = "abababab-abab-4bab-8bab-abababababab"


class Auth(tuple):
    """`(user, token, org_id)` + `.is_admin`, like `noctusai_seed.organ_auth.OrganAuth`."""

    is_admin: bool


def _auth(authorization: Optional[str] = Header(None)) -> Auth:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    who = authorization.split(" ", 1)[1]  # "<user>:<org>:<admin|member>"
    user, org, role = who.split(":")
    out = Auth((SimpleNamespace(id=user), "tok", org))
    out.is_admin = role == "admin"
    return out


def _admin(auth: Auth = Depends(_auth)) -> Auth:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def hdr(user: str = U1, org: str = ORG_A, role: str = "member") -> dict:
    return {"Authorization": f"Bearer {user}:{org}:{role}"}


ADM = hdr(ADMIN, role="admin")


@pytest.fixture
def api():
    env = Env()
    router = make_assignment_router(_auth, _admin, get_service=lambda: env.svc)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return SimpleNamespace(env=env, client=TestClient(app), router=router)


ROUTES = [
    ("get", "/api/assignment/settings", None),
    ("put", "/api/assignment/settings", {"strategy": "manual"}),
    ("get", "/api/assignment/teams", None),
    ("post", "/api/assignment/teams", {"name": "x"}),
    ("get", f"/api/assignment/teams/{TEAM}", None),
    ("patch", f"/api/assignment/teams/{TEAM}", {"name": "y"}),
    ("delete", f"/api/assignment/teams/{TEAM}", None),
    ("post", f"/api/assignment/teams/{TEAM}/members", {"user_id": U1}),
    ("patch", f"/api/assignment/teams/{TEAM}/members/{U1}", {"active": False}),
    ("delete", f"/api/assignment/teams/{TEAM}/members/{U1}", None),
    ("put", f"/api/assignment/teams/{TEAM}/order", {"order": [U1]}),
    ("get", "/api/assignment/rules", None),
    ("put", "/api/assignment/rules", {"kind": "source", "match_value": "x", "team_id": TEAM}),
    ("delete", f"/api/assignment/rules/{TEAM}", None),
    ("get", "/api/assignment/workload", None),
    ("get", "/api/assignment/events", None),
    ("get", f"/api/assignment/assignments/card/{CARD1}", None),
    ("post", "/api/assignment/assign", {"subject_kind": "card", "subject_id": CARD1}),
    ("post", "/api/assignment/close", {"subject_kind": "card", "subject_id": CARD1}),
    ("post", "/api/assignment/reassign", {"subject_kind": "card", "subject_id": CARD1, "to_user_id": U2}),
    ("post", "/api/assignment/unassign", {"subject_kind": "card", "subject_id": CARD1}),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m.upper()} {p.split('/api/assignment')[1][:34]}" for m, p, _ in ROUTES])
def test_every_route_is_unauthenticated_401_strictly(api, method, path, body):
    resp = getattr(api.client, method)(path, **({"json": body} if body is not None else {}))
    assert resp.status_code == 401


def test_the_router_declares_the_org_tier(api):
    assert api.router.access_tier == "org"


ADMIN_ONLY = [r for r in ROUTES if r[0] in ("put", "post", "patch", "delete") and not r[1].endswith(("/assign", "/close", "/reassign", "/unassign"))]


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY, ids=[f"{m.upper()} {p.split('/api/assignment')[1][:34]}" for m, p, _ in ADMIN_ONLY])
def test_configuration_writes_are_403_for_a_plain_member(api, method, path, body):
    resp = getattr(api.client, method)(path, headers=hdr(), **({"json": body} if body is not None else {}))
    assert resp.status_code == 403


def test_an_admin_configures_and_a_member_triggers_the_distribution_end_to_end(api):
    c = api.client
    team = c.post("/api/assignment/teams", json={"name": "Vendas"}, headers=ADM)
    assert team.status_code == 201
    tid = team.json()["data"]["id"]
    assert c.post(f"/api/assignment/teams/{tid}/members", json={"user_id": U1, "capacity": 5}, headers=ADM).status_code == 201
    assert c.put("/api/assignment/settings", json={"strategy": "round_robin", "keep_last": True}, headers=ADM).json()["data"]["strategy"] == "round_robin"
    out = c.post("/api/assignment/assign", json={"subject_kind": "card", "subject_id": CARD1, "source": "site"}, headers=hdr(U2))
    assert out.status_code == 200 and out.json()["data"]["user_id"] == U1
    assert c.get(f"/api/assignment/assignments/card/{CARD1}", headers=hdr(U2)).json()["data"]["user_id"] == U1
    ev = c.get("/api/assignment/events", params={"subject_kind": "card", "subject_id": CARD1}, headers=hdr(U2)).json()["data"]
    assert [e["event"] for e in ev] == ["assigned"]
    load = {r["user_id"]: r for r in c.get("/api/assignment/workload", headers=hdr(U2)).json()["data"]}
    assert load[U1]["open_count"] == 1
    assert c.post("/api/assignment/close", json={"subject_kind": "card", "subject_id": CARD1}, headers=hdr(U2)).json()["data"]["event"] == "closed"


def test_only_an_admin_or_the_current_owner_may_move_the_owner(api):
    c, env = api.client, api.env
    env.team("Vendas", [U1])
    c.post("/api/assignment/assign", json={"subject_kind": "card", "subject_id": CARD1}, headers=ADM)
    body = {"subject_kind": "card", "subject_id": CARD1, "to_user_id": U2}
    stranger = c.post("/api/assignment/reassign", json=body, headers=hdr(U2))
    assert stranger.status_code == 403 and stranger.json()["error"]["code"] == "sem_permissao"
    assert c.post("/api/assignment/unassign", json={"subject_kind": "card", "subject_id": CARD1}, headers=hdr(U2)).status_code == 403
    handoff = c.post("/api/assignment/reassign", json=body, headers=hdr(U1))  # the owner hands it off
    assert handoff.status_code == 200 and handoff.json()["data"]["user_id"] == U2
    assert c.post("/api/assignment/reassign", json={**body, "to_user_id": U1}, headers=ADM).status_code == 200
    never_owned = {"subject_kind": "card", "subject_id": CARD2, "to_user_id": U2}
    assert c.post("/api/assignment/reassign", json=never_owned, headers=hdr(U1)).status_code == 403  # no owner: admin only


def test_a_foreign_org_cannot_see_or_touch_a_team(api):
    team = api.env.team("Vendas", [U1])
    other = hdr(ADMIN, ORG_B, "admin")
    assert api.client.get(f"/api/assignment/teams/{team['id']}", headers=other).status_code == 404
    assert api.client.patch(f"/api/assignment/teams/{team['id']}", json={"name": "x"}, headers=other).status_code == 404
    assert api.client.get("/api/assignment/teams", headers=other).json()["data"] == []


def test_bodies_are_strict_unknown_fields_and_bad_ids_are_422(api):
    c = api.client
    assert c.post("/api/assignment/teams", json={"name": "x", "org_id": ORG_B}, headers=ADM).status_code == 422  # no body-supplied org
    assert c.post("/api/assignment/assign", json={"subject_kind": "card", "subject_id": "nope"}, headers=hdr()).status_code == 422
    assert c.post("/api/assignment/assign", json={"subject_kind": "BAD KIND", "subject_id": CARD1}, headers=hdr()).status_code == 422
    assert c.put("/api/assignment/settings", json={"strategy": "nope"}, headers=ADM).json()["error"]["code"] == "estrategia_invalida"


def test_an_assignment_that_does_not_exist_is_a_404_not_an_empty_200(api):
    assert api.client.get(f"/api/assignment/assignments/card/{CARD1}", headers=hdr()).status_code == 404

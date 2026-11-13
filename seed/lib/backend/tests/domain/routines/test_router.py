"""routines_router -- strict 401, org-admin only, reasons on flips, trigger + one-step approval."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.editorial import FakeEditorialStore
from noctusai_lib.domain.routines import (
    FakeRoutineStore,
    RoutineService,
    RoutinesContext,
    RunItem,
    routines_router,
)
from noctusai_lib.domain.routines.workflow import ROUTINES_WORKFLOW

ORG, ADMIN, MEMBER, OUTSIDER = (uuid4() for _ in range(4))


class Col:
    async def collect(self, routine):
        return [RunItem("a", {"t": 1}), RunItem("b", {"t": 2})]


def _client():
    store, ed = FakeRoutineStore(), FakeEditorialStore(ROUTINES_WORKFLOW)
    svc = RoutineService(store, ed, Col())

    def auth(authorization: str | None = Header(default=None)):
        if not authorization:
            raise HTTPException(401, detail="no token")
        return UUID(authorization.removeprefix("Bearer "))

    def resolve(u):
        return RoutinesContext(org_id=None if u == OUTSIDER else ORG, user_id=u, is_org_admin=u == ADMIN)

    app = FastAPI()
    app.include_router(routines_router(
        auth_dependency=auth, resolve_context=resolve, get_store=lambda: store, get_service=lambda: svc,
        success_response=lambda d: {"success": True, "data": d}, prefix="/routines"))
    return TestClient(app), store, ed


def H(u):
    return {"Authorization": f"Bearer {u}"}


def _create(c, who=ADMIN, name="news"):
    return c.post("/routines", json={"name": name, "cron": "0 7 * * *", "config": {"q": "x"}}, headers=H(who))


ROUTES = [
    ("get", "/routines", None), ("post", "/routines", {"name": "n", "cron": "0 7 * * *"}),
    ("get", "/routines/master", None), ("put", "/routines/master", {"enabled": False, "reason": "xxx"}),
    ("get", "/routines/events", None), ("get", "/routines/report", None),
    ("get", f"/routines/{uuid4()}", None), ("patch", f"/routines/{uuid4()}", {"name": "z"}),
    ("post", f"/routines/{uuid4()}/enable", {"reason": "xxx"}), ("post", f"/routines/{uuid4()}/disable", {"reason": "xxx"}),
    ("post", f"/routines/{uuid4()}/kill", {"reason": "xxx"}), ("post", f"/routines/{uuid4()}/trigger", None),
    ("post", f"/routines/{uuid4()}/drafts/{uuid4()}/approve", None),
    ("post", f"/routines/{uuid4()}/drafts/{uuid4()}/reject", {"reason": "xxx"}),
]


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_every_route_is_strictly_401_without_a_token(method, path, body):
    c, *_ = _client()
    assert getattr(c, method)(path, **({"json": body} if body is not None else {})).status_code == 401


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_every_route_is_403_for_a_non_admin_member_and_for_a_non_member(method, path, body):
    c, *_ = _client()
    for who, code in ((MEMBER, "admin_required"), (OUTSIDER, "org_membership_required")):
        r = getattr(c, method)(path, headers=H(who), **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and r.json()["detail"]["code"] == code


def test_create_list_edit_and_extra_field_is_422():
    c, store, _ = _client()
    rid = _create(c).json()["data"]["id"]
    assert _create(c).status_code == 409
    assert c.post("/routines", json={"name": "n2", "cron": "bad cron x y z", "mode": "trigger"},
                  headers=H(ADMIN)).status_code == 422
    assert c.post("/routines", json={"name": "n3", "cron": "0 7 * * *", "org_id": str(uuid4())},
                  headers=H(ADMIN)).status_code == 422
    r = c.patch(f"/routines/{rid}", json={"mode": "routine", "config": {"q": "y"}, "reason": "validated"}, headers=H(ADMIN))
    assert r.status_code == 200 and r.json()["data"]["mode"] == "routine"
    lst = c.get("/routines", headers=H(ADMIN)).json()["data"]
    assert [x["name"] for x in lst["routines"]] == ["news"] and lst["master_enabled"] is True
    kinds = [e["kind"] for e in c.get("/routines/events", headers=H(ADMIN)).json()["data"]["events"]]
    assert kinds == ["created", "edited", "mode_changed"]


def test_flips_need_a_reason_and_are_recorded_with_actor():
    c, store, _ = _client()
    rid = _create(c).json()["data"]["id"]
    assert c.post(f"/routines/{rid}/enable", json={"reason": ""}, headers=H(ADMIN)).status_code == 422
    assert c.post(f"/routines/{rid}/enable", json={}, headers=H(ADMIN)).status_code == 422
    assert c.post(f"/routines/{rid}/enable", json={"reason": "validated"}, headers=H(ADMIN)).json()["data"]["ativo"] is True
    k = c.post(f"/routines/{rid}/kill", json={"reason": "bad output"}, headers=H(ADMIN)).json()["data"]
    assert (k["killed"], k["ativo"]) == (True, False)
    m = c.put("/routines/master", json={"enabled": False, "reason": "incident"}, headers=H(ADMIN))
    assert m.json()["data"] == {"enabled": False}
    ev = c.get("/routines/events", headers=H(ADMIN)).json()["data"]["events"]
    flips = [(e["scope"], e["kind"], e["actor_id"], e["reason"]) for e in ev if e["kind"] in ("enabled", "killed", "disabled")]
    assert flips == [("routine", "enabled", str(ADMIN), "validated"), ("routine", "killed", str(ADMIN), "bad output"),
                     ("master", "disabled", str(ADMIN), "incident")]
    assert c.get("/routines/404404", headers=H(ADMIN)).status_code == 422  # malformed id


def test_trigger_now_then_approve_and_reject_with_required_reason():
    c, store, ed = _client()
    rid = _create(c).json()["data"]["id"]
    run = c.post(f"/routines/{rid}/trigger", headers=H(ADMIN)).json()["data"]
    a, b = run["item_ids"]
    assert (run["status"], run["drafts"]) == ("ok", 2)
    assert c.post(f"/routines/{rid}/drafts/{b}/reject", json={"reason": ""}, headers=H(ADMIN)).status_code == 422
    assert c.post(f"/routines/{rid}/drafts/{a}/approve", headers=H(ADMIN)).status_code == 200
    assert c.post(f"/routines/{rid}/drafts/{b}/reject", json={"reason": "off topic"}, headers=H(ADMIN)).status_code == 200
    assert {ed.get_item(ORG, UUID(a)).state, ed.get_item(ORG, UUID(b)).state} == {"publicado", "arquivado"}
    assert c.post(f"/routines/{rid}/drafts/{a}/approve", headers=H(ADMIN)).status_code == 409  # already published
    rep = c.get("/routines/report", headers=H(ADMIN)).json()["data"]
    assert rep["totals"]["approved"] == 1 and rep["totals"]["rejected"] == 1


def test_trigger_blocked_when_killed_is_409_and_unknown_routine_404():
    c, *_ = _client()
    rid = _create(c).json()["data"]["id"]
    c.post(f"/routines/{rid}/kill", json={"reason": "bad output"}, headers=H(ADMIN))
    r = c.post(f"/routines/{rid}/trigger", headers=H(ADMIN))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "killed"
    assert c.get(f"/routines/{uuid4()}", headers=H(ADMIN)).status_code == 404


def test_other_orgs_routine_is_404_not_leaked():
    c, store, _ = _client()
    other = store.create_routine(org_id=uuid4(), name="x", cron="0 7 * * *", mode="trigger", config={}, actor_id=ADMIN)
    assert c.get(f"/routines/{other.id}", headers=H(ADMIN)).status_code == 404

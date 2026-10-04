"""editorial_router — strict auth, org scoping, server-derived grants, separation of duties."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.editorial import (
    EditorialContext,
    FakeEditorialStore,
    Grant,
    diff_content,
    editorial_router,
)
from noctusai_lib.domain.permissions.repo import FakePermissionGrantRepository

ORG, OTHER_ORG = uuid4(), uuid4()
AUTHOR, EDITOR, SECURITY, PUBLISHER, OUTSIDER = (uuid4() for _ in range(5))
ALL = {
    AUTHOR: [Grant.EDITAR],
    EDITOR: [Grant.REVISAR],
    SECURITY: [Grant.REVISAR_SEGURANCA],
    PUBLISHER: [Grant.PUBLICAR],
}
MEMBERS = {ORG: {AUTHOR, EDITOR, SECURITY, PUBLISHER}, OTHER_ORG: {OUTSIDER}}


def _build(grants=None, permission_names=None):
    store = FakeEditorialStore()
    names = {g: (permission_names or {}).get(g, g.value) for g in Grant}
    repo = FakePermissionGrantRepository(
        [(u, names[g]) for u, gs in (grants or ALL).items() for g in gs]
    )

    def auth(authorization: str | None = Header(default=None)):
        if not authorization:
            raise HTTPException(401, detail="no token")
        return UUID(authorization.removeprefix("Bearer "))

    def resolve(user_id: UUID) -> EditorialContext:
        # product-owned membership: the org this request acts in, only if a member
        org = ORG if user_id in MEMBERS[ORG] else None
        return EditorialContext(org_id=org, user_id=user_id)

    app = FastAPI()
    app.include_router(
        editorial_router(
            auth_dependency=auth, resolve_context=resolve, get_store=lambda: store,
            get_permission_repo=lambda: repo, success_response=lambda d: {"success": True, "data": d},
            permission_names=permission_names, prefix="/editorial",
        )
    )
    return TestClient(app), store


def H(u):
    return {"Authorization": f"Bearer {u}"}


def _create(c, who=AUTHOR, content=None):
    return c.post("/editorial/", json={"kind": "doc", "ref": "a", "content": content or {"t": "v1"}}, headers=H(who))


def _tr(c, item, who, action, motivo=None):
    return c.post(f"/editorial/{item}/transitions", json={"action": action, "motivo": motivo}, headers=H(who))


def _code(r):
    return r.json()["detail"]["code"]


def _to_security_review(c):
    item = _create(c).json()["data"]["item"]["id"]
    assert _tr(c, item, AUTHOR, "submit").status_code == 200
    assert _tr(c, item, EDITOR, "approve_editorial").status_code == 200
    return item


class TestAuth:
    def test_no_token_401(self):
        c, _ = _build()
        assert c.get("/editorial").status_code == 401
        assert c.post("/editorial/", json={"kind": "d", "ref": "r", "content": {}}).status_code == 401

    def test_non_member_403_org_membership(self):
        c, _ = _build()
        r = c.get("/editorial", headers=H(OUTSIDER))
        assert r.status_code == 403 and _code(r) == "org_membership_required"
        assert _create(c, who=OUTSIDER).status_code == 403

    def test_missing_grant_403_machine_code(self):
        c, _ = _build()
        r = _create(c, who=EDITOR)  # holds only revisar
        assert r.status_code == 403 and _code(r) == "missing_grant"

    def test_global_grant_does_not_cross_org(self):
        # the outsider holds every grant, but is not a member of the acting org
        c, _ = _build(grants={OUTSIDER: list(Grant)})
        assert _create(c, who=OUTSIDER).status_code == 403

    def test_extra_grants_field_is_422(self):
        c, _ = _build()
        r = c.post("/editorial/", json={"kind": "d", "ref": "r", "content": {}, "grants": ["editorial:publicar"]}, headers=H(EDITOR))
        assert r.status_code == 422
        item = _create(c).json()["data"]["item"]["id"]
        r = c.post(f"/editorial/{item}/transitions", json={"action": "submit", "grants": ["editorial:editar"]}, headers=H(EDITOR))
        assert r.status_code == 422

    def test_grants_are_server_derived_and_renamable(self):
        names = {g: f"nnl:{g.value}" for g in Grant}
        c, _ = _build(permission_names=names)
        assert _create(c).status_code == 201
        c2, _ = _build(grants={AUTHOR: []})  # no grant ⇒ refused
        assert _create(c2).status_code == 403


class TestSeparationOfDuties:
    def test_author_cannot_approve_own_version(self):
        c, _ = _build(grants={**ALL, AUTHOR: [Grant.EDITAR, Grant.REVISAR]})
        item = _create(c).json()["data"]["item"]["id"]
        _tr(c, item, AUTHOR, "submit")
        r = _tr(c, item, AUTHOR, "approve_editorial")
        assert r.status_code == 403 and _code(r) == "self_approval"

    def test_security_approver_cannot_be_editorial_approver(self):
        c, _ = _build(grants={**ALL, EDITOR: [Grant.REVISAR, Grant.REVISAR_SEGURANCA]})
        item = _to_security_review(c)
        r = _tr(c, item, EDITOR, "approve_security")
        assert r.status_code == 403 and _code(r) == "same_approver"

    def test_publish_needs_signoff(self):
        c, _ = _build()
        item = _to_security_review(c)
        r = _tr(c, item, PUBLISHER, "publish")
        assert r.status_code == 409 and _code(r) == "security_signoff_missing"


class TestFlow:
    def test_happy_path_all_states(self):
        c, _ = _build()
        item = _to_security_review(c)
        assert _tr(c, item, SECURITY, "approve_security").status_code == 200
        r = _tr(c, item, PUBLISHER, "publish")
        assert r.status_code == 200 and r.json()["data"]["item"]["state"] == "publicado"
        assert r.json()["data"]["item"]["published_version_n"] == 1
        # edit-after-publish: v2 draft while v1 keeps serving
        r = c.post(f"/editorial/{item}/versions", json={"content": {"t": "v2", "x": 1}}, headers=H(AUTHOR))
        assert r.status_code == 201
        assert r.json()["data"]["item"]["state"] == "rascunho"
        assert r.json()["data"]["item"]["published_version_n"] == 1
        assert _tr(c, item, PUBLISHER, "archive", "obsoleto").json()["data"]["item"]["state"] == "arquivado"
        d = c.get(f"/editorial/{item}", headers=H(AUTHOR)).json()["data"]
        assert [v["n"] for v in d["versions"]] == [1, 2]
        assert [e["action"] for e in d["events"]] == [
            "create", "submit", "approve_editorial", "approve_security", "publish", "edit", "archive",
        ]

    def test_queue_filters_and_pages(self):
        c, _ = _build()
        for i in range(3):
            c.post("/editorial/", json={"kind": "doc", "ref": f"r{i}", "content": {}}, headers=H(AUTHOR))
        d = c.get("/editorial?state=rascunho&page_size=2&page=2", headers=H(EDITOR)).json()["data"]
        assert d["total"] == 3 and len(d["items"]) == 1
        assert c.get("/editorial?state=publicado", headers=H(EDITOR)).json()["data"]["total"] == 0

    def test_duplicate_ref_409(self):
        c, _ = _build()
        _create(c)
        r = _create(c)
        assert r.status_code == 409 and _code(r) == "already_exists"


class TestIllegal:
    def test_illegal_transition_409(self):
        c, _ = _build()
        item = _create(c).json()["data"]["item"]["id"]
        r = _tr(c, item, PUBLISHER, "publish")
        assert r.status_code == 409 and _code(r) == "illegal_transition"

    def test_send_back_needs_motivo_422(self):
        c, _ = _build()
        item = _create(c).json()["data"]["item"]["id"]
        _tr(c, item, AUTHOR, "submit")
        r = _tr(c, item, EDITOR, "send_back")
        assert r.status_code == 422 and _code(r) == "motivo_required"

    def test_unknown_action_422(self):
        c, _ = _build()
        item = _create(c).json()["data"]["item"]["id"]
        assert _code(_tr(c, item, AUTHOR, "explode")) == "unknown_action"

    def test_edit_via_transitions_refused(self):
        c, _ = _build()
        item = _create(c).json()["data"]["item"]["id"]
        r = _tr(c, item, AUTHOR, "edit")
        assert r.status_code == 422 and _code(r) == "use_versions_endpoint"

    def test_unknown_item_404(self):
        c, _ = _build()
        assert c.get(f"/editorial/{uuid4()}", headers=H(AUTHOR)).status_code == 404
        assert _tr(c, uuid4(), AUTHOR, "submit").status_code == 404


class TestDiff:
    def test_structured_diff(self):
        c, _ = _build()
        item = _create(c, content={"a": 1, "b": {"x": 1}, "gone": True}).json()["data"]["item"]["id"]
        c.post(f"/editorial/{item}/versions", json={"content": {"a": 2, "b": {"x": 1, "y": 2}, "new": 1}}, headers=H(AUTHOR))
        r = c.get(f"/editorial/{item}/diff?from_n=1&to_n=2", headers=H(EDITOR))
        ch = {x["path"]: (x["op"], x["before"], x["after"]) for x in r.json()["data"]["changes"]}
        assert ch == {
            "a": ("changed", 1, 2), "b.y": ("added", None, 2),
            "gone": ("removed", True, None), "new": ("added", None, 1),
        }
        assert c.get(f"/editorial/{item}/diff?from_n=1&to_n=9", headers=H(EDITOR)).status_code == 404

    def test_diff_identical_is_empty(self):
        assert diff_content({"a": [1, 2]}, {"a": [1, 2]}) == []

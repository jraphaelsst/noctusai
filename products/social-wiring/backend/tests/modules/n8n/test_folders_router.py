"""Tests for /api/n8n/folders (GET/POST) and /api/n8n/folders/{id}
(PATCH/DELETE).

Covers: auth boundary, 404/403 via account resolution (GET/POST) and
via the folder row's own org_id (PATCH/DELETE), the 422 cycle-guard,
409 name-conflict, and the delete-with-reassignment tree operation —
including the binding "absent reassign_to ⇒ root" FE contract.
"""
from __future__ import annotations

from tests.modules.n8n.conftest import make_n8n_account


class TestAuthBoundary:
    def test_list_folders_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().get(
            "/api/n8n/folders", params={"account_id": "00000000-0000-0000-0000-000000000001"}
        )
        assert resp.status_code == 401, resp.text

    def test_create_folder_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().post(
            "/api/n8n/folders",
            json={"account_id": "00000000-0000-0000-0000-000000000001", "name": "X"},
        )
        assert resp.status_code == 401, resp.text


class TestAccountResolution:
    def test_list_unknown_account_is_404(self, n8n_env):
        resp = n8n_env.client.get(
            "/api/n8n/folders", params={"account_id": "00000000-0000-0000-0000-000000009999"}
        )
        assert resp.status_code == 404, resp.text

    def test_list_other_org_account_is_403(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, org_id=n8n_env.OTHER_ORG)
        resp = n8n_env.client.get(
            "/api/n8n/folders", params={"account_id": str(account.id)}
        )
        assert resp.status_code == 403, resp.text


class TestCreateAndList:
    def test_create_then_list_round_trips(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        create_resp = n8n_env.client.post(
            "/api/n8n/folders",
            json={"account_id": str(account.id), "name": "Cliente A"},
        )
        assert create_resp.status_code == 201, create_resp.text
        folder_id = create_resp.json()["id"]

        list_resp = n8n_env.client.get(
            "/api/n8n/folders", params={"account_id": str(account.id)}
        )
        assert list_resp.status_code == 200, list_resp.text
        assert [f["id"] for f in list_resp.json()] == [folder_id]
        assert list_resp.json()[0]["parent_id"] is None

    def test_create_duplicate_sibling_name_is_409(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        n8n_env.client.post(
            "/api/n8n/folders", json={"account_id": str(account.id), "name": "Dup"}
        )
        resp = n8n_env.client.post(
            "/api/n8n/folders", json={"account_id": str(account.id), "name": "Dup"}
        )
        assert resp.status_code == 409, resp.text

    def test_create_with_unknown_parent_is_404(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/folders",
            json={
                "account_id": str(account.id),
                "name": "Orphan",
                "parent_id": "00000000-0000-0000-0000-000000009999",
            },
        )
        assert resp.status_code == 404, resp.text


class TestUpdateFolder:
    def test_rename_and_reposition(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        folder = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Old", parent_id=None
        )
        resp = n8n_env.client.patch(
            f"/api/n8n/folders/{folder.id}", json={"name": "New", "position": 3}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "New"
        assert body["position"] == 3

    def test_reparent_into_own_descendant_is_422(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        parent = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Parent", parent_id=None
        )
        child = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Child", parent_id=parent.id
        )
        resp = n8n_env.client.patch(
            f"/api/n8n/folders/{parent.id}", json={"parent_id": str(child.id)}
        )
        assert resp.status_code == 422, resp.text

    def test_self_parent_is_422(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        folder = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Solo", parent_id=None
        )
        resp = n8n_env.client.patch(
            f"/api/n8n/folders/{folder.id}", json={"parent_id": str(folder.id)}
        )
        assert resp.status_code == 422, resp.text

    def test_update_unknown_folder_is_404(self, n8n_env):
        resp = n8n_env.client.patch(
            "/api/n8n/folders/00000000-0000-0000-0000-000000009999", json={"name": "X"}
        )
        assert resp.status_code == 404, resp.text

    def test_update_other_org_folder_is_403(self, n8n_env):
        other_account = make_n8n_account(n8n_env.svc, org_id=n8n_env.OTHER_ORG)
        foreign_folder = n8n_env.folders_svc.create(
            org_id=n8n_env.OTHER_ORG, account_id=other_account.id, name="Not yours", parent_id=None
        )
        resp = n8n_env.client.patch(
            f"/api/n8n/folders/{foreign_folder.id}", json={"name": "Hijack"}
        )
        assert resp.status_code == 403, resp.text


class TestDeleteFolder:
    def test_delete_reassigns_children_and_placements_to_explicit_target(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        root = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Root2", parent_id=None
        )
        doomed = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Doomed", parent_id=None
        )
        child = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Child", parent_id=doomed.id
        )
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-1",
            folder_id=doomed.id,
        )

        resp = n8n_env.client.delete(
            f"/api/n8n/folders/{doomed.id}", params={"reassign_to": str(root.id)}
        )
        assert resp.status_code == 204, resp.text

        remaining = {f.id: f for f in n8n_env.folders_svc.list_for_account(account.id, n8n_env.CALLER_ORG)}
        assert doomed.id not in remaining
        assert remaining[child.id].parent_id == root.id
        placements = n8n_env.folders_svc.get_placements(account.id)
        assert placements["fake-wf-1"] == root.id

    def test_delete_without_reassign_to_moves_children_and_placements_to_root(self, n8n_env):
        """The binding FE contract: an ABSENT `reassign_to` query param
        means root, not an error and not a literal "null" string."""
        account = make_n8n_account(n8n_env.svc)
        doomed = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Doomed2", parent_id=None
        )
        child = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Child2", parent_id=doomed.id
        )
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-2",
            folder_id=doomed.id,
        )

        resp = n8n_env.client.delete(f"/api/n8n/folders/{doomed.id}")
        assert resp.status_code == 204, resp.text

        remaining = {f.id: f for f in n8n_env.folders_svc.list_for_account(account.id, n8n_env.CALLER_ORG)}
        assert remaining[child.id].parent_id is None
        placements = n8n_env.folders_svc.get_placements(account.id)
        assert "fake-wf-2" not in placements  # root ⇒ absent from the dict

    def test_delete_reassign_to_own_descendant_is_422(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        parent = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="P", parent_id=None
        )
        child = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="C", parent_id=parent.id
        )
        resp = n8n_env.client.delete(
            f"/api/n8n/folders/{parent.id}", params={"reassign_to": str(child.id)}
        )
        assert resp.status_code == 422, resp.text

    def test_delete_unknown_folder_is_404(self, n8n_env):
        resp = n8n_env.client.delete("/api/n8n/folders/00000000-0000-0000-0000-000000009999")
        assert resp.status_code == 404, resp.text

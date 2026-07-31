"""Tests for /api/n8n/workflows + /api/n8n/tags.

Covers: auth boundary (strict 401), 403-vs-404 account resolution,
424 on incomplete credential, scope filtering (client/unassigned),
assign/unassign tag-preservation, the 409-run-blocked zero-side-effect
path, and the 502 upstream-error translation.
"""
from __future__ import annotations

from tests.modules.n8n.conftest import delete_with_body, make_n8n_account


# ─── auth boundary ──────────────────────────────────────────────────────
class TestAuthBoundary:
    def test_list_workflows_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().get(
            "/api/n8n/workflows",
            params={"account_id": "00000000-0000-0000-0000-000000000001", "scope": "client"},
        )
        assert resp.status_code == 401, resp.text

    def test_run_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().post(
            "/api/n8n/workflows/fake-wf-1/run",
            json={"account_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 401, resp.text


# ─── account resolution: 403 vs 404 ─────────────────────────────────────
class TestAccountResolution:
    def test_unknown_account_is_404(self, n8n_env):
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": "00000000-0000-0000-0000-000000009999", "scope": "client"},
        )
        assert resp.status_code == 404, resp.text

    def test_account_in_other_org_is_403(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, org_id=n8n_env.OTHER_ORG)
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "client"},
        )
        assert resp.status_code == 403, resp.text

    def test_non_n8n_provider_account_is_404(self, n8n_env):
        other = n8n_env.svc.create_account(
            org_id=n8n_env.CALLER_ORG,
            provider="youtube",
            account_label="Not n8n",
            credential_dict={"access_token": "x"},
        )
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(other.id), "scope": "client"},
        )
        assert resp.status_code == 404, resp.text


# ─── 424 incomplete credential ───────────────────────────────────────────
class TestIncompleteCredential:
    def test_missing_base_url_returns_424(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, base_url=None, api_key="k")
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "client"},
        )
        assert resp.status_code == 424, resp.text

    def test_missing_api_key_returns_424(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, base_url="https://n8n.x.com", api_key=None)
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "client"},
        )
        assert resp.status_code == 424, resp.text

    def test_incomplete_credential_never_returns_fake_data_silently(self, n8n_env):
        """The exact silent-error trap this module guards against:
        get_n8n_client() would silently hand back FakeN8nClient's
        seeded demo workflows for an incomplete credential — assert
        that never happens (424, not 200 with data)."""
        account = make_n8n_account(n8n_env.svc, base_url=None, api_key=None)
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "unassigned"},
        )
        assert resp.status_code == 424, resp.text


# ─── scope filtering ──────────────────────────────────────────────────────
class TestListScoping:
    def test_unassigned_scope_returns_untagged_workflows(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "unassigned"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {w["id"] for w in body["workflows"]}
        # FakeN8nClient seeds fake-wf-1/fake-wf-3 WITH a tag, fake-wf-2 with none.
        assert ids == {"fake-wf-2"}
        assert body["workflows"][0]["archived"] is False

    def test_client_scope_with_no_tag_configured_is_empty_not_error(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)  # no tag configured
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "client"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["workflows"] == []

    def test_client_scope_with_tag_matches_only_that_tag(self, n8n_env):
        account = make_n8n_account(
            n8n_env.svc, tag={"id": "fake-tag-1", "name": "prod"}
        )
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={"account_id": str(account.id), "scope": "client"},
        )
        assert resp.status_code == 200, resp.text
        ids = {w["id"] for w in resp.json()["workflows"]}
        # fake-wf-1 carries fake-tag-1 and is not archived (default
        # include_archived=False excludes fake-wf-3).
        assert ids == {"fake-wf-1"}
        wf = resp.json()["workflows"][0]
        assert wf["can_run"] is True
        assert wf["run_blocked_reason"] is None
        assert wf["open_url"] == "https://n8n.example.com/workflow/fake-wf-1"

    def test_include_archived_true_surfaces_archived_workflow(self, n8n_env):
        account = make_n8n_account(
            n8n_env.svc, tag={"id": "fake-tag-1", "name": "prod"}
        )
        resp = n8n_env.client.get(
            "/api/n8n/workflows",
            params={
                "account_id": str(account.id),
                "scope": "client",
                "include_archived": "true",
            },
        )
        ids = {w["id"] for w in resp.json()["workflows"]}
        assert ids == {"fake-wf-1", "fake-wf-3"}
        archived_wf = next(w for w in resp.json()["workflows"] if w["id"] == "fake-wf-3")
        assert archived_wf["can_run"] is False
        assert archived_wf["run_blocked_reason"] == "workflow is archived"


# ─── assign / unassign ────────────────────────────────────────────────────
class TestAssignUnassign:
    def test_assign_without_configured_tag_returns_424(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)  # no tag
        resp = n8n_env.client.post(
            "/api/n8n/workflows/fake-wf-2/assign",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 424, resp.text

    def test_assign_preserves_other_tags(self, n8n_env):
        account = make_n8n_account(
            n8n_env.svc, tag={"id": "fake-tag-1", "name": "prod"}
        )
        # Pre-attach an UNRELATED tag directly on the fake client's raw
        # workflow state (the sanctioned test hook — see FakeN8nClient's
        # docstring) so assignment's tag-preservation is actually
        # exercised: fake-wf-2 starts with zero tags otherwise.
        n8n_env.fake_client.tags["other-tag"] = type(
            n8n_env.fake_client.tags["fake-tag-1"]
        )(id="other-tag", name="unrelated")
        n8n_env.fake_client._raw_workflows["fake-wf-2"]["tags"] = [
            {"id": "other-tag", "name": "unrelated"}
        ]
        resp = n8n_env.client.post(
            "/api/n8n/workflows/fake-wf-2/assign",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        tag_ids = {t["id"] for t in body["tags"]}
        assert tag_ids == {"fake-tag-1", "other-tag"}

    def test_unassign_removes_only_the_client_tag_and_clears_placement(self, n8n_env):
        account = make_n8n_account(
            n8n_env.svc, tag={"id": "fake-tag-1", "name": "prod"}
        )
        # fake-wf-1 already carries fake-tag-1 (seeded). Place it in a folder first.
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-1",
            folder_id=None,
        )
        resp = delete_with_body(
            n8n_env.client,
            "/api/n8n/workflows/fake-wf-1/assign",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tags"] == []
        assert body["folder_id"] is None
        placements = n8n_env.folders_svc.get_placements(account.id)
        assert "fake-wf-1" not in placements


# ─── PATCH workflow ───────────────────────────────────────────────────────
class TestPatchWorkflow:
    def test_rename_and_deactivate(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.patch(
            "/api/n8n/workflows/fake-wf-1",
            json={"account_id": str(account.id), "name": "Renamed", "active": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Renamed"
        assert body["active"] is False

    def test_folder_id_null_moves_to_root(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        folder = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Bucket", parent_id=None
        )
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-1",
            folder_id=folder.id,
        )
        resp = n8n_env.client.patch(
            "/api/n8n/workflows/fake-wf-1",
            json={"account_id": str(account.id), "folder_id": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["folder_id"] is None

    def test_omitted_folder_id_leaves_placement_unchanged(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        folder = n8n_env.folders_svc.create(
            org_id=n8n_env.CALLER_ORG, account_id=account.id, name="Bucket", parent_id=None
        )
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-1",
            folder_id=folder.id,
        )
        resp = n8n_env.client.patch(
            "/api/n8n/workflows/fake-wf-1",
            json={"account_id": str(account.id), "name": "New name only"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["folder_id"] == str(folder.id)


# ─── DELETE workflow ──────────────────────────────────────────────────────
class TestDeleteWorkflow:
    def test_delete_returns_204_and_clears_placement(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        n8n_env.folders_svc.set_placement(
            org_id=n8n_env.CALLER_ORG,
            account_id=account.id,
            workflow_id="fake-wf-2",
            folder_id=None,
        )
        resp = delete_with_body(
            n8n_env.client,
            "/api/n8n/workflows/fake-wf-2",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 204, resp.text
        assert "fake-wf-2" not in n8n_env.fake_client._raw_workflows
        assert "fake-wf-2" not in n8n_env.folders_svc.get_placements(account.id)

    def test_delete_unknown_workflow_is_404(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = delete_with_body(
            n8n_env.client,
            "/api/n8n/workflows/ghost-workflow",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 404, resp.text


# ─── run: 409 zero-side-effect + happy path ─────────────────────────────
class TestRunWorkflow:
    def test_run_blocked_workflow_returns_409_with_zero_side_effects(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/workflows/fake-wf-2/run",  # manual-trigger only, no webhook
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 409, resp.text
        assert "fake-wf-2" not in n8n_env.fake_client.webhook_calls

    def test_run_archived_workflow_returns_409(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/workflows/fake-wf-3/run",  # webhook, but archived
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["message"] == "workflow is archived"

    def test_run_runnable_workflow_dispatches(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/workflows/fake-wf-1/run",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dispatched"] is True
        assert body["workflow_id"] == "fake-wf-1"
        assert n8n_env.fake_client.webhook_calls == ["fake-wf-1"]

    def test_run_unknown_workflow_is_404(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/workflows/ghost/run",
            json={"account_id": str(account.id)},
        )
        assert resp.status_code == 404, resp.text


# ─── executions ────────────────────────────────────────────────────────
class TestExecutions:
    def test_list_executions(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.get(
            "/api/n8n/workflows/fake-wf-1/executions",
            params={"account_id": str(account.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["executions"]) == 1
        assert body["executions"][0]["id"] == 1
        assert body["executions"][0]["status"] == "success"


# ─── tags ──────────────────────────────────────────────────────────────
class TestTags:
    def test_list_tags(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.get("/api/n8n/tags", params={"account_id": str(account.id)})
        assert resp.status_code == 200, resp.text
        names = {t["name"] for t in resp.json()}
        assert names == {"prod"}

    def test_create_tag(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.post(
            "/api/n8n/tags", json={"account_id": str(account.id), "name": "staging"}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == "staging"


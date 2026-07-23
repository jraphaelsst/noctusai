"""Tests for FakeN8nClient — Protocol conformance + deterministic
behavior.

Covers:
- Structural Protocol conformance (``isinstance(fake, N8nClient)``).
- Seeded run-eligibility matrix (1 runnable / 2 not, matching the
  live-measured 1-of-9 ratio's shape).
- Workflow lifecycle: create/activate/deactivate/rename/update/delete.
- Tag lifecycle: list/create/set_workflow_tags (ids not names,
  unknown-id fails loudly).
- Execution list/get/delete (int id; include_data toggles the heavy
  payload).
- Credential lifecycle: create/delete/schema (write-only — no
  list/get; the secret ``data`` never round-trips).
- ``run_via_webhook``: dispatches the runnable workflow, raises
  ``N8nWorkflowNotRunnableError`` (status 409) — never a faked
  dispatch — for the other two.
- ``ping()`` always succeeds (no network in the fake).
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.n8n import get_n8n_client
from noctusai_lib.integrations.n8n.fake_adapter import FakeN8nClient
from noctusai_lib.integrations.n8n.types import (
    N8nClient,
    N8nNotFoundError,
    N8nWorkflowNotRunnableError,
)


# ---------------------------------------------------------------------------
# Protocol conformance + factory
# ---------------------------------------------------------------------------


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeN8nClient(), N8nClient)


def test_factory_returns_fake_when_no_credentials() -> None:
    assert isinstance(get_n8n_client(), FakeN8nClient)
    assert isinstance(get_n8n_client(base_url="https://x.com"), FakeN8nClient)
    assert isinstance(get_n8n_client(api_key="k"), FakeN8nClient)


def test_factory_returns_real_when_both_credentials_present() -> None:
    from noctusai_lib.integrations.n8n.n8n_adapter import HttpxN8nClient

    client = get_n8n_client(base_url="https://n8n.x.com", api_key="k")
    assert isinstance(client, HttpxN8nClient)


# ---------------------------------------------------------------------------
# Seeded run-eligibility matrix
# ---------------------------------------------------------------------------


def test_seeded_workflows_cover_the_eligibility_matrix() -> None:
    client = FakeN8nClient()
    workflows = asyncio.run(client.list_workflows(include_archived=True))
    by_id = {w.id: w for w in workflows}
    assert by_id["fake-wf-1"].can_run is True
    assert by_id["fake-wf-2"].can_run is False  # no webhook node
    assert by_id["fake-wf-3"].can_run is False  # archived


def test_list_workflows_excludes_archived_by_default() -> None:
    client = FakeN8nClient()
    workflows = asyncio.run(client.list_workflows())
    assert "fake-wf-3" not in {w.id for w in workflows}


def test_list_workflows_include_archived_true_shows_all() -> None:
    client = FakeN8nClient()
    workflows = asyncio.run(client.list_workflows(include_archived=True))
    assert {w.id for w in workflows} == {"fake-wf-1", "fake-wf-2", "fake-wf-3"}


def test_list_workflows_filters_by_tag_id() -> None:
    client = FakeN8nClient()
    workflows = asyncio.run(
        client.list_workflows(tag="fake-tag-1", include_archived=True)
    )
    assert {w.id for w in workflows} == {"fake-wf-1", "fake-wf-3"}


def test_list_workflows_filters_by_tag_name() -> None:
    client = FakeN8nClient()
    workflows = asyncio.run(client.list_workflows(tag="prod"))
    assert {w.id for w in workflows} == {"fake-wf-1"}  # wf-3 archived, excluded


# ---------------------------------------------------------------------------
# get_workflow — full raw fidelity
# ---------------------------------------------------------------------------


def test_get_workflow_returns_full_raw_with_nodes() -> None:
    client = FakeN8nClient()
    raw = asyncio.run(client.get_workflow("fake-wf-1"))
    assert raw["id"] == "fake-wf-1"
    assert "nodes" in raw
    assert raw["nodes"][0]["type"] == "n8n-nodes-base.webhook"


def test_get_workflow_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.get_workflow("does-not-exist"))


def test_get_workflow_returns_a_copy_not_internal_state() -> None:
    """Mutating the returned dict must not corrupt the fake's store."""
    client = FakeN8nClient()
    raw = asyncio.run(client.get_workflow("fake-wf-1"))
    raw["name"] = "mutated"
    fresh = asyncio.run(client.get_workflow("fake-wf-1"))
    assert fresh["name"] != "mutated"


# ---------------------------------------------------------------------------
# activate / deactivate
# ---------------------------------------------------------------------------


def test_activate_flips_active_true() -> None:
    client = FakeN8nClient()
    asyncio.run(client.deactivate("fake-wf-2"))
    w = asyncio.run(client.activate("fake-wf-2"))
    assert w.active is True


def test_deactivate_flips_active_false() -> None:
    client = FakeN8nClient()
    w = asyncio.run(client.deactivate("fake-wf-1"))
    assert w.active is False
    assert w.can_run is False  # inactive ⇒ not runnable


# ---------------------------------------------------------------------------
# create_workflow / update_workflow — the general forms rename() builds on
# ---------------------------------------------------------------------------


def test_create_workflow_sanitizes_and_assigns_id() -> None:
    client = FakeN8nClient()
    workflow = asyncio.run(
        client.create_workflow(
            {
                "name": "New Flow",
                "nodes": [{"type": "n8n-nodes-base.manualTrigger"}],
                "connections": {},
                "id": "should-be-stripped",  # not in the PUT allowlist
                "active": True,  # not in the PUT allowlist — ignored
            }
        )
    )
    assert workflow.name == "New Flow"
    assert workflow.id != "should-be-stripped"
    assert workflow.active is False  # new workflows are never active on create
    raw = asyncio.run(client.get_workflow(workflow.id))
    assert raw["nodes"]


def test_create_workflow_deterministic_ids() -> None:
    client = FakeN8nClient()
    w1 = asyncio.run(client.create_workflow({"name": "a"}))
    w2 = asyncio.run(client.create_workflow({"name": "b"}))
    assert w1.id != w2.id


def test_update_workflow_replaces_arbitrary_fields() -> None:
    client = FakeN8nClient()
    updated = asyncio.run(
        client.update_workflow(
            "fake-wf-2",
            {"name": "Retitled", "nodes": [{"type": "n8n-nodes-base.webhook", "parameters": {"path": "new-hook"}}]},
        )
    )
    assert updated.name == "Retitled"
    assert updated.has_webhook_node is True  # nodes were actually replaced


def test_update_workflow_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.update_workflow("does-not-exist", {"name": "x"}))


# ---------------------------------------------------------------------------
# rename — exercises sanitize_workflow_put_body via the fake too
# ---------------------------------------------------------------------------


def test_rename_updates_name_and_preserves_nodes() -> None:
    client = FakeN8nClient()
    w = asyncio.run(client.rename("fake-wf-1", "Renamed Flow"))
    assert w.name == "Renamed Flow"
    raw = asyncio.run(client.get_workflow("fake-wf-1"))
    assert raw["name"] == "Renamed Flow"
    assert raw["nodes"]  # preserved, not dropped by the sanitize round-trip


def test_rename_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.rename("does-not-exist", "x"))


# ---------------------------------------------------------------------------
# delete_workflow
# ---------------------------------------------------------------------------


def test_delete_workflow_removes_it() -> None:
    client = FakeN8nClient()
    asyncio.run(client.delete_workflow("fake-wf-2"))
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.get_workflow("fake-wf-2"))


def test_delete_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.delete_workflow("does-not-exist"))


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_list_tags_seeded() -> None:
    client = FakeN8nClient()
    tags = asyncio.run(client.list_tags())
    assert [t.id for t in tags] == ["fake-tag-1"]


def test_create_tag_deterministic_id() -> None:
    client = FakeN8nClient()
    tag = asyncio.run(client.create_tag("staging"))
    assert tag.id == "fake-tag-2"
    assert tag.name == "staging"


def test_set_workflow_tags_by_id_not_name() -> None:
    client = FakeN8nClient()
    new_tag = asyncio.run(client.create_tag("staging"))
    tags = asyncio.run(client.set_workflow_tags("fake-wf-2", [new_tag.id]))
    assert [t.id for t in tags] == ["fake-tag-2"]


def test_set_workflow_tags_unknown_id_fails_loudly() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.set_workflow_tags("fake-wf-1", ["nope"]))


# ---------------------------------------------------------------------------
# Executions — int id, list vs. get(include_data)
# ---------------------------------------------------------------------------


def test_list_executions_seeded() -> None:
    client = FakeN8nClient()
    executions = asyncio.run(client.list_executions())
    assert len(executions) == 1
    assert executions[0].id == 1
    assert isinstance(executions[0].id, int)


def test_list_executions_filters_by_workflow_id() -> None:
    client = FakeN8nClient()
    executions = asyncio.run(client.list_executions(workflow_id="fake-wf-1"))
    assert len(executions) == 1
    executions = asyncio.run(client.list_executions(workflow_id="fake-wf-2"))
    assert executions == []


def test_get_execution_include_data_true_keeps_data_key() -> None:
    client = FakeN8nClient()
    raw = asyncio.run(client.get_execution(1, include_data=True))
    assert "data" in raw


def test_get_execution_include_data_false_strips_data_key() -> None:
    client = FakeN8nClient()
    raw = asyncio.run(client.get_execution(1, include_data=False))
    assert "data" not in raw


def test_get_execution_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.get_execution(999))


def test_get_execution_extracts_retry_of() -> None:
    client = FakeN8nClient()
    client.executions[2] = {"id": 2, "workflowId": "fake-wf-1", "retryOf": 1}
    executions = {e.id: e for e in asyncio.run(client.list_executions())}
    assert executions[2].retry_of == 1


def test_delete_execution_removes_it() -> None:
    client = FakeN8nClient()
    asyncio.run(client.delete_execution(1))
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.get_execution(1))


def test_delete_execution_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.delete_execution(999))


# ---------------------------------------------------------------------------
# Credentials — write-only (no list/get; the secret never round-trips)
# ---------------------------------------------------------------------------


def test_create_credential_deterministic_id_no_secret_echoed() -> None:
    client = FakeN8nClient()
    cred = asyncio.run(
        client.create_credential(
            name="hdr", type="httpHeaderAuth", data={"name": "X-Api-Key", "value": "s3cr3t"}
        )
    )
    assert cred.id == "fake-cred-1"
    assert cred.name == "hdr"
    assert cred.type == "httpHeaderAuth"
    assert not hasattr(cred, "data")


def test_delete_credential_removes_it() -> None:
    client = FakeN8nClient()
    cred = asyncio.run(client.create_credential(name="hdr", type="httpHeaderAuth", data={}))
    asyncio.run(client.delete_credential(cred.id))
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.delete_credential(cred.id))


def test_delete_credential_missing_raises_not_found() -> None:
    client = FakeN8nClient()
    with pytest.raises(N8nNotFoundError):
        asyncio.run(client.delete_credential("does-not-exist"))


def test_get_credential_schema_known_type() -> None:
    client = FakeN8nClient()
    schema = asyncio.run(client.get_credential_schema("httpHeaderAuth"))
    assert schema["required"] == ["name", "value"]


def test_get_credential_schema_unknown_type_generic_fallback() -> None:
    client = FakeN8nClient()
    schema = asyncio.run(client.get_credential_schema("someUnknownType"))
    assert schema == {"type": "object", "properties": {}, "required": []}


# ---------------------------------------------------------------------------
# run_via_webhook — never a faked dispatch
# ---------------------------------------------------------------------------


def test_run_via_webhook_dispatches_runnable_workflow() -> None:
    client = FakeN8nClient()
    workflows = {w.id: w for w in asyncio.run(client.list_workflows())}
    result = asyncio.run(client.run_via_webhook(workflows["fake-wf-1"]))
    assert result.dispatched is True
    assert result.workflow_id == "fake-wf-1"
    assert client.webhook_calls == ["fake-wf-1"]


def test_run_via_webhook_raises_for_no_webhook_node() -> None:
    client = FakeN8nClient()
    workflows = {
        w.id: w for w in asyncio.run(client.list_workflows(include_archived=True))
    }
    with pytest.raises(N8nWorkflowNotRunnableError) as exc_info:
        asyncio.run(client.run_via_webhook(workflows["fake-wf-2"]))
    assert exc_info.value.status == 409
    assert client.webhook_calls == []  # never a faked dispatch


def test_run_via_webhook_raises_for_archived() -> None:
    client = FakeN8nClient()
    workflows = {
        w.id: w for w in asyncio.run(client.list_workflows(include_archived=True))
    }
    with pytest.raises(N8nWorkflowNotRunnableError) as exc_info:
        asyncio.run(client.run_via_webhook(workflows["fake-wf-3"]))
    assert exc_info.value.status == 409
    assert client.webhook_calls == []


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------


def test_ping_always_succeeds() -> None:
    client = FakeN8nClient()
    assert asyncio.run(client.ping()) is True

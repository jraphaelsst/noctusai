"""Tests for the n8n pure-function mappers.

Covers:
- ``normalize_base_url`` / ``instance_root`` / ``webhook_url``: the
  two derived URLs from one stored instance root.
- ``sanitize_workflow_put_body``: the PUT-accepted key allowlist.
- ``tag_refs_body``: tag-ids-not-names.
- ``extract_webhook_trigger``: webhook node detection vs. the other
  trigger flavors observed live (formTrigger/executeWorkflowTrigger/
  manualTrigger).
- ``raw_to_workflow`` / ``raw_to_tag`` / ``raw_to_execution`` /
  ``raw_to_credential``: raw dict → dataclass round-trips, including
  the ``can_run`` eligibility matrix (webhook × active × archived) and
  ``retryOf`` extraction.
- ``extract_error_message``: best-effort n8n error-body extraction.
"""

from __future__ import annotations

from noctusai_lib.integrations.n8n.mappers import (
    WORKFLOW_PUT_ALLOWED_KEYS,
    extract_error_message,
    extract_webhook_trigger,
    instance_root,
    normalize_base_url,
    raw_to_credential,
    raw_to_execution,
    raw_to_tag,
    raw_to_workflow,
    sanitize_workflow_put_body,
    tag_refs_body,
    webhook_url,
)


# ---------------------------------------------------------------------------
# URL derivation
# ---------------------------------------------------------------------------


def test_normalize_base_url_appends_api_v1() -> None:
    assert normalize_base_url("https://n8n.x.com") == "https://n8n.x.com/api/v1"


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert normalize_base_url("https://n8n.x.com/") == "https://n8n.x.com/api/v1"


def test_normalize_base_url_idempotent_on_already_suffixed() -> None:
    assert (
        normalize_base_url("https://n8n.x.com/api/v1")
        == "https://n8n.x.com/api/v1"
    )


def test_normalize_base_url_empty_stays_empty() -> None:
    assert normalize_base_url("") == ""


def test_instance_root_strips_api_v1_suffix() -> None:
    assert instance_root("https://n8n.x.com/api/v1") == "https://n8n.x.com"


def test_instance_root_strips_trailing_slash() -> None:
    assert instance_root("https://n8n.x.com/") == "https://n8n.x.com"


def test_instance_root_empty_stays_empty() -> None:
    assert instance_root("") == ""


def test_webhook_url_lives_outside_versioned_api() -> None:
    assert (
        webhook_url("https://n8n.x.com", "matricula-extractor")
        == "https://n8n.x.com/webhook/matricula-extractor"
    )


def test_webhook_url_from_already_suffixed_base() -> None:
    """Whichever shape base_url was stored in, webhook_url lands on the
    bare instance root — never `.../api/v1/webhook/...`."""
    assert (
        webhook_url("https://n8n.x.com/api/v1", "abc")
        == "https://n8n.x.com/webhook/abc"
    )


# ---------------------------------------------------------------------------
# PUT-sanitize allowlist
# ---------------------------------------------------------------------------


def test_put_allowed_keys_are_exactly_four() -> None:
    assert WORKFLOW_PUT_ALLOWED_KEYS == ("name", "nodes", "connections", "settings")


def test_sanitize_strips_readonly_keys() -> None:
    dirty = {
        "id": "abc",
        "name": "Flow",
        "active": True,
        "tags": [{"id": "1", "name": "prod"}],
        "createdAt": "2026-01-01",
        "updatedAt": "2026-05-19",
        "versionId": "v9",
        "triggerCount": 3,
        "nodes": [{"name": "Webhook"}],
        "connections": {"Webhook": {}},
    }
    body = sanitize_workflow_put_body(dirty)
    assert set(body.keys()) == {"name", "nodes", "connections", "settings"}
    assert body["settings"] == {}  # defaulted, source omitted it


def test_sanitize_preserves_existing_settings() -> None:
    body = sanitize_workflow_put_body({"name": "x", "settings": {"a": 1}})
    assert body["settings"] == {"a": 1}


# ---------------------------------------------------------------------------
# Tag-ids-not-names
# ---------------------------------------------------------------------------


def test_tag_refs_body_uses_ids_not_names() -> None:
    assert tag_refs_body(["t1", "t2"]) == [{"id": "t1"}, {"id": "t2"}]


def test_tag_refs_body_empty_clears() -> None:
    assert tag_refs_body([]) == []


# ---------------------------------------------------------------------------
# Webhook-trigger extraction
# ---------------------------------------------------------------------------


def test_extract_webhook_trigger_finds_webhook_node() -> None:
    nodes = [
        {
            "type": "n8n-nodes-base.webhook",
            "parameters": {"httpMethod": "POST", "path": "my-hook"},
        }
    ]
    assert extract_webhook_trigger(nodes) == ("POST", "my-hook")


def test_extract_webhook_trigger_defaults_method_to_get() -> None:
    nodes = [{"type": "n8n-nodes-base.webhook", "parameters": {"path": "abc"}}]
    assert extract_webhook_trigger(nodes) == ("GET", "abc")


def test_extract_webhook_trigger_none_for_form_trigger() -> None:
    nodes = [{"type": "n8n-nodes-base.formTrigger", "parameters": {}}]
    assert extract_webhook_trigger(nodes) is None


def test_extract_webhook_trigger_none_for_execute_workflow_trigger() -> None:
    nodes = [{"type": "n8n-nodes-base.executeWorkflowTrigger", "parameters": {}}]
    assert extract_webhook_trigger(nodes) is None


def test_extract_webhook_trigger_none_for_manual_trigger() -> None:
    nodes = [{"type": "n8n-nodes-base.manualTrigger", "parameters": {}}]
    assert extract_webhook_trigger(nodes) is None


def test_extract_webhook_trigger_none_for_empty_nodes() -> None:
    assert extract_webhook_trigger([]) is None
    assert extract_webhook_trigger(None) is None


def test_extract_webhook_trigger_ignores_webhook_node_without_path() -> None:
    """A webhook node without a `path` isn't dispatchable — skip it."""
    nodes = [{"type": "n8n-nodes-base.webhook", "parameters": {}}]
    assert extract_webhook_trigger(nodes) is None


# ---------------------------------------------------------------------------
# raw_to_workflow — can_run eligibility matrix
# ---------------------------------------------------------------------------


def _raw_workflow(**overrides: object) -> dict:
    base = {
        "id": "wf1",
        "name": "Flow",
        "active": True,
        "isArchived": False,
        "tags": [],
        "nodes": [{"type": "n8n-nodes-base.webhook", "parameters": {"path": "p", "httpMethod": "GET"}}],
        "createdAt": "2026-07-16T00:00:00.000Z",
        "updatedAt": "2026-07-16T01:00:00.000Z",
    }
    base.update(overrides)
    return base


def test_raw_to_workflow_can_run_true_when_webhook_active_not_archived() -> None:
    w = raw_to_workflow(_raw_workflow())
    assert w.has_webhook_node is True
    assert w.can_run is True
    assert w.webhook_method == "GET"
    assert w.webhook_path == "p"


def test_raw_to_workflow_can_run_false_when_inactive() -> None:
    w = raw_to_workflow(_raw_workflow(active=False))
    assert w.has_webhook_node is True
    assert w.can_run is False


def test_raw_to_workflow_can_run_false_when_archived() -> None:
    w = raw_to_workflow(_raw_workflow(isArchived=True))
    assert w.can_run is False


def test_raw_to_workflow_can_run_false_when_no_webhook_node() -> None:
    w = raw_to_workflow(
        _raw_workflow(nodes=[{"type": "n8n-nodes-base.manualTrigger", "parameters": {}}])
    )
    assert w.has_webhook_node is False
    assert w.can_run is False
    assert w.webhook_path is None


def test_raw_to_workflow_id_is_str() -> None:
    w = raw_to_workflow(_raw_workflow(id=123))
    assert w.id == "123"
    assert isinstance(w.id, str)


def test_raw_to_workflow_maps_tags() -> None:
    w = raw_to_workflow(_raw_workflow(tags=[{"id": "t1", "name": "prod"}]))
    assert len(w.tags) == 1
    assert w.tags[0].id == "t1"
    assert w.tags[0].name == "prod"


def test_raw_to_workflow_parses_timestamps() -> None:
    w = raw_to_workflow(_raw_workflow())
    assert w.created_at is not None
    assert w.updated_at is not None


# ---------------------------------------------------------------------------
# raw_to_tag
# ---------------------------------------------------------------------------


def test_raw_to_tag() -> None:
    t = raw_to_tag({"id": "t1", "name": "prod"})
    assert t.id == "t1"
    assert t.name == "prod"


# ---------------------------------------------------------------------------
# raw_to_execution — int id, never unified with the str workflow id
# ---------------------------------------------------------------------------


def test_raw_to_execution_id_is_int() -> None:
    e = raw_to_execution({"id": 42, "workflowId": "wf1", "status": "success"})
    assert e.id == 42
    assert isinstance(e.id, int)
    assert e.workflow_id == "wf1"
    assert isinstance(e.workflow_id, str)


def test_raw_to_execution_no_workflow_id() -> None:
    e = raw_to_execution({"id": 1})
    assert e.workflow_id is None


def test_raw_to_execution_extracts_retry_of() -> None:
    e = raw_to_execution({"id": 2, "retryOf": 1})
    assert e.retry_of == 1


def test_raw_to_execution_retry_of_defaults_none() -> None:
    e = raw_to_execution({"id": 1})
    assert e.retry_of is None


# ---------------------------------------------------------------------------
# raw_to_credential — never carries the secret `data`
# ---------------------------------------------------------------------------


def test_raw_to_credential() -> None:
    c = raw_to_credential({"id": "9xZ", "name": "hdr", "type": "httpHeaderAuth", "data": {"leaked": "no"}})
    assert c.id == "9xZ"
    assert c.name == "hdr"
    assert c.type == "httpHeaderAuth"
    assert not hasattr(c, "data")  # the dataclass has no such field at all


# ---------------------------------------------------------------------------
# extract_error_message
# ---------------------------------------------------------------------------


def test_extract_error_message_from_message_key() -> None:
    title, detail = extract_error_message({"message": "Bad request"})
    assert detail == "Bad request"


def test_extract_error_message_from_title_detail() -> None:
    title, detail = extract_error_message({"title": "Bad Request", "detail": "explain"})
    assert title == "Bad Request"
    assert detail == "explain"


def test_extract_error_message_non_dict_body() -> None:
    assert extract_error_message(None) == ("", "")
    assert extract_error_message("plain text") == ("", "")

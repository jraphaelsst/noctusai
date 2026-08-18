"""`trello.contract.*` tool-layer behaviour — no credentials, no network.

Every test here runs with NO env vars set and NO patched transport —
proving the zero-IO guarantee for real, not by mocking the boundary away.
"""
from __future__ import annotations

import asyncio

from trello.tools import contract


def run(coro):
    return asyncio.run(coro)


# -- list_endpoints ----------------------------------------------------


def test_list_endpoints_with_no_filter_returns_all_261():
    result = run(contract.list_endpoints({}))
    assert result["count"] == 261
    assert len(result["endpoints"]) == 261


def test_list_endpoints_filters_by_resource():
    result = run(contract.list_endpoints({"resource": "checklists"}))
    assert result["count"] == 12
    assert all(e["resource"] == "checklists" for e in result["endpoints"])


def test_list_endpoints_filters_by_method():
    result = run(contract.list_endpoints({"method": "delete"}))
    assert result["count"] > 0
    assert all(e["method"] == "DELETE" for e in result["endpoints"])


def test_list_endpoints_filters_by_substring():
    result = run(contract.list_endpoints({"q": "checklist"}))
    assert result["count"] > 0
    for e in result["endpoints"]:
        assert "checklist" in e["path"].lower() or "checklist" in e["summary"].lower()


def test_list_endpoints_combines_filters():
    result = run(contract.list_endpoints({"resource": "cards", "method": "post"}))
    assert all(e["resource"] == "cards" and e["method"] == "POST" for e in result["endpoints"])
    assert result["count"] > 0


# -- describe_operation --------------------------------------------------


def test_describe_operation_by_method_and_path():
    result = run(contract.describe_operation({"method": "PUT", "path": "/cards/{id}"}))
    op = result["operation"]
    assert op["method"] == "PUT"
    assert op["path"] == "/cards/{id}"
    names = [p["name"] for p in op["parameters"]]
    assert names[:4] == ["name", "desc", "closed", "idMembers"]
    assert op["response_schema_ref"] == "Card"


def test_describe_operation_by_operation_id():
    by_id = run(contract.describe_operation({"operation_id": "get-cards-id"}))
    by_path = run(contract.describe_operation({"method": "GET", "path": "/cards/{id}"}))
    assert by_id["operation"]["path"] == by_path["operation"]["path"]


def test_describe_operation_requires_enough_identifying_info():
    result = run(contract.describe_operation({}))
    assert result["operation"] is None
    assert result["error"]["status"] is None


def test_describe_operation_unknown_path_is_404_not_a_fabricated_shape():
    result = run(contract.describe_operation({"method": "GET", "path": "/not/real"}))
    assert result["operation"] is None
    assert result["error"]["status"] == 404


# -- describe_model -------------------------------------------------------


def test_describe_model_card_flattens_badges_one_level():
    result = run(contract.describe_model({"name": "Card"}))
    badges = result["model"]["properties"]["badges"]
    assert "comments" in badges["nested_properties"]
    assert "checkItems" in badges["nested_properties"]


def test_describe_model_unknown_name_is_404():
    result = run(contract.describe_model({"name": "NotAThing"}))
    assert result["model"] is None
    assert result["error"]["status"] == 404


def test_describe_model_trello_list_is_the_lists_schema_name():
    result = run(contract.describe_model({"name": "TrelloList"}))
    assert "name" in result["model"]["properties"]
    assert "idBoard" in result["model"]["properties"]


# -- card_surface ----------------------------------------------------------


def test_card_surface_groups_sum_to_the_full_42_card_operations():
    result = run(contract.card_surface({}))
    assert result["operation_count"] == 42
    assert sum(len(v) for v in result["groups"].values()) == 42


def test_card_surface_covers_every_expected_affordance_group():
    result = run(contract.card_surface({}))
    expected_groups = {
        "core", "comments_activity", "attachments", "checklists",
        "check_items", "labels", "members", "votes", "stickers",
        "custom_fields",
    }
    assert set(result["groups"].keys()) == expected_groups


def test_card_surface_publishes_the_put_writable_field_list():
    result = run(contract.card_surface({}))
    assert result["put_writable_fields"][0] == "name"
    assert "cover" in result["put_writable_fields"]


def test_card_surface_embeds_the_card_schema_with_flattened_badges():
    result = run(contract.card_surface({}))
    assert "due" in result["card_schema"]["properties"]["badges"]["nested_properties"]


# -- capability_map ----------------------------------------------------------


def test_capability_map_covers_all_9_trello_affordances_from_the_roadmap():
    result = run(contract.capability_map({}))
    names = {row["trello_affordance"] for row in result["mappings"]}
    assert names == {
        "Título", "Etiquetas", "Descrição", "Datas + lembrete", "Anexo",
        "Comentários e atividade", "Membros", "Checklist", "Card-face badges",
    }
    assert "lead-card-hub-2026-08.md" in result["source"]


def test_capability_map_status_is_one_of_the_three_documented_values():
    result = run(contract.capability_map({}))
    for row in result["mappings"]:
        assert row["status"] in {"exists", "build-new", "no-equivalent"}


def test_capability_map_titulo_is_marked_exists():
    result = run(contract.capability_map({}))
    titulo = next(r for r in result["mappings"] if r["trello_affordance"] == "Título")
    assert titulo["status"] == "exists"
    assert titulo["trello_schema_ref"] == "Card.name"

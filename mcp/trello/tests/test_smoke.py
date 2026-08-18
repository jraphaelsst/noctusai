"""Registry-shape smoke tests for the Trello connector MCP.

Pins the exact registered tool-name set (a silent addition/removal fails
here), 3-segment dotted naming under `trello.*`, descriptor/handler
agreement, and that every descriptor carries a non-empty description +
a valid object inputSchema.
"""
from __future__ import annotations

from trello.tools import all_descriptors, all_handlers

EXPECTED_TOOLS = {
    "trello.contract.list_endpoints",
    "trello.contract.describe_operation",
    "trello.contract.describe_model",
    "trello.contract.card_surface",
    "trello.contract.capability_map",
    "trello.diagnostics.connection_status",
    "trello.diagnostics.probe",
    "trello.boards.list",
    "trello.lists.list",
    "trello.cards.list",
    "trello.cards.get",
    "trello.checklists.get",
    "trello.labels.list",
    "trello.actions.list",
    "trello.cards.create",
    "trello.cards.update",
    "trello.cards.comment_add",
    "trello.checklists.create",
}

WRITE_TOOLS = {
    "trello.cards.create",
    "trello.cards.update",
    "trello.cards.comment_add",
    "trello.checklists.create",
}


def test_registry_exposes_exactly_the_expected_18_tools():
    assert set(all_handlers().keys()) == EXPECTED_TOOLS
    assert len(EXPECTED_TOOLS) == 18


def test_descriptors_and_handlers_agree():
    assert {d.name for d in all_descriptors()} == set(all_handlers().keys())


def test_every_tool_name_is_three_dotted_segments_under_trello():
    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, name
        assert parts[0] == "trello", name


def test_every_descriptor_carries_a_description_and_object_schema():
    for descriptor in all_descriptors():
        assert descriptor.description, descriptor.name
        assert descriptor.inputSchema.get("type") == "object", descriptor.name


def test_write_tool_descriptions_say_write_and_confirm_gated():
    by_name = {d.name: d for d in all_descriptors()}
    for name in WRITE_TOOLS:
        desc = by_name[name].description.lower()
        assert "write" in desc, name
        assert "confirm" in desc, name


def test_read_tool_descriptions_say_read():
    by_name = {d.name: d for d in all_descriptors()}
    for name in all_handlers():
        if name in WRITE_TOOLS:
            continue
        assert "read" in by_name[name].description.lower(), name


def test_contract_tool_descriptions_say_zero_io():
    by_name = {d.name: d for d in all_descriptors()}
    for name in all_handlers():
        if name.startswith("trello.contract.") or name == "trello.diagnostics.connection_status":
            assert "zero" in by_name[name].description.lower(), name

"""Registry-shape smoke tests for the Telegram connector MCP."""
from __future__ import annotations

from telegram.tools import all_descriptors, all_handlers

EXPECTED_TOOLS = {
    "telegram.diagnostics.connection_status",
    "telegram.diagnostics.me",
    "telegram.dialogs.list",
    "telegram.messages.list",
    "telegram.messages.search",
    "telegram.messages.export",
    "telegram.media.download",
    "telegram.messages.send",
}
WRITE_TOOLS = {"telegram.media.download", "telegram.messages.send"}


def test_registry_exposes_exactly_the_expected_tools():
    assert set(all_handlers().keys()) == EXPECTED_TOOLS


def test_descriptors_and_handlers_agree():
    assert {d.name for d in all_descriptors()} == set(all_handlers().keys())


def test_every_tool_name_is_three_dotted_segments_under_telegram():
    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3 and parts[0] == "telegram", name


def test_every_descriptor_has_description_and_object_schema():
    for d in all_descriptors():
        assert d.description, d.name
        assert d.inputSchema.get("type") == "object", d.name


def test_write_descriptions_say_write_and_confirm_reads_say_read():
    by = {d.name: d.description.lower() for d in all_descriptors()}
    for name, desc in by.items():
        if name in WRITE_TOOLS:
            assert "write" in desc and "confirm" in desc, name
        else:
            assert "read" in desc, name

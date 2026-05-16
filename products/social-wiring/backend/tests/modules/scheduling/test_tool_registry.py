"""Tests for the absorbed scheduling tool registry (Wave 2.3).

Exercises the ``ToolHandler`` dispatch contract (seed
``noctusai_lib.domain.chatbot.ToolCall``/``ToolResult``) in both the
stub path (no service) and the live path (service injected).
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from noctusai_lib.domain.chatbot import ToolCall
from noctusai_lib.testing import MockSupabaseClient
from app.modules.scheduling.engine import SchedulingService, build_rules
from app.modules.scheduling.tool_registry import (
    TOOL_DESCRIPTORS,
    build_tool_handler,
    tool_names,
)

_ORG = UUID("00000000-0000-4000-8000-000000000001")


def _call(name: str, **args) -> ToolCall:
    return ToolCall(call_id=f"c-{name}", name=name, arguments=args)


def test_descriptors_cover_the_five_tools():
    names = {d["function"]["name"] for d in TOOL_DESCRIPTORS}
    assert names == {
        "lookup_property",
        "propose_appointment",
        "confirm_appointment",
        "cancel_appointment",
        "reschedule_appointment",
    }
    assert set(tool_names()) == names


def test_stub_path_returns_not_implemented_when_no_service():
    handler = build_tool_handler()
    result = handler(_call("lookup_property", code="AP-1"))
    payload = json.loads(result.content)
    assert payload["status"] == "not_implemented"
    assert payload["tool"] == "lookup_property"


def test_unknown_tool_returns_structured_payload_not_exception():
    handler = build_tool_handler()
    result = handler(_call("definitely_not_a_tool"))
    payload = json.loads(result.content)
    assert payload["status"] == "unknown_tool"
    assert result.call_id == "c-definitely_not_a_tool"


def test_live_lookup_property_missing_argument():
    svc = SchedulingService(
        MockSupabaseClient([], validate_schema=False),
        org_id=_ORG,
        rules=build_rules(),
    )
    handler = build_tool_handler(svc)
    result = handler(_call("lookup_property", code=""))
    payload = json.loads(result.content)
    assert payload["status"] == "failure"
    assert "code" in payload["error"]


def test_live_lookup_property_not_found_status():
    svc = SchedulingService(
        MockSupabaseClient([], validate_schema=False),
        org_id=_ORG,
        rules=build_rules(),
    )
    handler = build_tool_handler(svc)
    result = handler(_call("lookup_property", code="AP-404"))
    payload = json.loads(result.content)
    assert payload["status"] == "not_found"
    assert payload["code"] == "AP-404"


def test_live_lookup_property_success():
    prop_id = str(uuid4())
    condo_id = str(uuid4())
    rows = [
        {
            "id": prop_id,
            "code": "AP-77",
            "condominium_id": condo_id,
            "active": True,
            "org_id": str(_ORG),
            "name": "Cond Y",
        }
    ]
    svc = SchedulingService(
        MockSupabaseClient(rows, validate_schema=False),
        org_id=_ORG,
        rules=build_rules(),
    )
    handler = build_tool_handler(svc)
    result = handler(_call("lookup_property", code="AP-77"))
    payload = json.loads(result.content)
    assert payload["status"] == "success"
    assert payload["property_id"] == prop_id
    assert payload["condominium_id"] == condo_id

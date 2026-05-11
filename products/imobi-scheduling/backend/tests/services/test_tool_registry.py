"""Tests for `app.services.tool_registry`.

Phase 6 wiring contract: three tools registered + a handler that
dispatches by name. Unknown-tool path returns a structured response
rather than raising. Tool descriptors are OpenAI-shaped for the
`LLMDispatcher.reply(tools=...)` consumer.
"""
from __future__ import annotations

import json

import pytest

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

from app.services.tool_registry import (
    TOOL_DESCRIPTORS,
    TOOL_IMPLEMENTATIONS,
    build_tool_handler,
    tool_names,
)


class TestRegistryShape:
    """The Phase 6 initial registry has exactly three tools."""

    def test_three_tools_registered(self):
        assert tool_names() == [
            "lookup_property",
            "propose_appointment",
            "confirm_appointment",
        ]

    def test_descriptors_match_implementations(self):
        descriptor_names = {d["function"]["name"] for d in TOOL_DESCRIPTORS}
        impl_names = set(TOOL_IMPLEMENTATIONS.keys())
        assert descriptor_names == impl_names

    def test_descriptors_are_openai_shaped(self):
        for descriptor in TOOL_DESCRIPTORS:
            assert descriptor["type"] == "function"
            fn = descriptor["function"]
            assert "name" in fn and isinstance(fn["name"], str)
            assert "description" in fn and fn["description"]
            assert fn["parameters"]["type"] == "object"
            assert "properties" in fn["parameters"]
            assert "required" in fn["parameters"]


class TestHandlerDispatch:
    """The handler closure dispatches by `ToolCall.name`."""

    def test_lookup_property_stub_returns_not_implemented(self):
        handler = build_tool_handler()
        result = handler(ToolCall(
            call_id="call_1",
            name="lookup_property",
            arguments={"code": "AP-2034"},
        ))
        assert result.call_id == "call_1"
        payload = json.loads(result.content)
        assert payload["status"] == "not_implemented"
        assert payload["tool"] == "lookup_property"
        assert payload["echo"] == {"code": "AP-2034"}

    def test_propose_appointment_stub(self):
        handler = build_tool_handler()
        args = {
            "property_code": "AP-2034",
            "requested_date": "2026-05-15",
            "time_window": "morning",
        }
        result = handler(ToolCall(
            call_id="call_2", name="propose_appointment", arguments=args,
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "not_implemented"
        assert payload["echo"] == args

    def test_confirm_appointment_stub(self):
        handler = build_tool_handler()
        args = {
            "property_code": "AP-2034",
            "services": ["photos", "videos"],
            "start_at": "2026-05-15T10:00:00-03:00",
            "end_at": "2026-05-15T11:30:00-03:00",
        }
        result = handler(ToolCall(
            call_id="call_3", name="confirm_appointment", arguments=args,
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "not_implemented"
        assert payload["echo"] == args

    def test_unknown_tool_returns_structured_response(self):
        """Unknown tool names do NOT raise — they return a structured
        `unknown_tool` payload the LLM can read back."""
        handler = build_tool_handler()
        result = handler(ToolCall(
            call_id="call_x", name="not_a_real_tool", arguments={},
        ))
        assert isinstance(result, ToolResult)
        assert result.call_id == "call_x"
        payload = json.loads(result.content)
        assert payload["status"] == "unknown_tool"
        assert payload["tool"] == "not_a_real_tool"

    def test_handler_catches_implementation_exceptions(self, monkeypatch):
        """If a tool implementation raises, the handler returns a
        `failure` payload (not propagate). The seed dispatcher would
        otherwise deadlock the LLM tool loop."""
        from app.services import tool_registry

        def _exploding(_args):
            raise ValueError("boom")

        monkeypatch.setitem(
            tool_registry.TOOL_IMPLEMENTATIONS, "lookup_property", _exploding,
        )
        handler = build_tool_handler()
        result = handler(ToolCall(
            call_id="call_e", name="lookup_property", arguments={"code": "X"},
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "failure"
        assert payload["error"] == "boom"


class TestParameterSchema:
    """Spot-check the JSON Schema for each tool — the LLM's tool-call
    arguments are validated against this on OpenAI's side."""

    @pytest.mark.parametrize(
        "tool_name,required_params",
        [
            ("lookup_property", ["code"]),
            ("propose_appointment", ["property_code", "requested_date", "time_window"]),
            ("confirm_appointment", ["property_code", "services", "start_at", "end_at"]),
        ],
    )
    def test_required_parameters_present(self, tool_name, required_params):
        descriptor = next(
            d for d in TOOL_DESCRIPTORS if d["function"]["name"] == tool_name
        )
        assert descriptor["function"]["parameters"]["required"] == required_params

    def test_time_window_enum(self):
        descriptor = next(
            d for d in TOOL_DESCRIPTORS if d["function"]["name"] == "propose_appointment"
        )
        prop = descriptor["function"]["parameters"]["properties"]["time_window"]
        assert prop["enum"] == ["morning", "afternoon", "any"]

    def test_services_enum(self):
        descriptor = next(
            d for d in TOOL_DESCRIPTORS if d["function"]["name"] == "confirm_appointment"
        )
        items = descriptor["function"]["parameters"]["properties"]["services"]["items"]
        assert items["enum"] == ["photos", "videos", "reels", "virtual_tour"]


# ---------------------------------------------------------------------------
# Phase 7 — live SchedulingService dispatch
# ---------------------------------------------------------------------------


class TestHandlerWithSchedulingService:
    """When a `SchedulingService` is injected, the handler dispatches
    `lookup_property` / `propose_appointment` / `confirm_appointment`
    against the live engine. Stubs only run when no service is wired."""

    def _make_service(self):
        """Build a real `SchedulingService` against a `MockSupabaseClient`."""
        from datetime import time
        from zoneinfo import ZoneInfo

        from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

        from app.services.scheduling import SchedulingService, build_rules

        org_id = "00000000-0000-0000-0000-000000000001"
        # Settings stub mirroring _settings_stub() in test_scheduling.py.
        class _S:
            imobi_scheduling_timezone = "America/Sao_Paulo"
            imobi_scheduling_morning_start = "09:00"
            imobi_scheduling_morning_end = "12:00"
            imobi_scheduling_afternoon_start = "13:30"
            imobi_scheduling_afternoon_end = "16:30"
            imobi_scheduling_travel_buffer_minutes = 10
            imobi_scheduling_standard_duration_minutes = 90
            imobi_scheduling_same_condo_duration_minutes = 60
            imobi_scheduling_slot_grid_minutes = 30

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=org_id,
            rules=build_rules(_S()),
        )
        return svc, MockSupabaseResponse

    def test_lookup_property_returns_not_found_when_db_empty(self):
        from app.services.tool_registry import build_tool_handler

        svc, MockResp = self._make_service()
        svc._scoped.set_sequential_responses("properties", [MockResp(data=[])])

        handler = build_tool_handler(scheduling_service=svc)
        result = handler(ToolCall(
            call_id="lp_1",
            name="lookup_property",
            arguments={"code": "AP-MISSING"},
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "not_found"
        assert payload["code"] == "AP-MISSING"

    def test_propose_appointment_returns_slots(self):
        from app.services.tool_registry import build_tool_handler

        svc, MockResp = self._make_service()
        svc._scoped.set_sequential_responses(
            "properties",
            [MockResp(data=[{
                "id": "ppppppp1-0000-0000-0000-000000000001",
                "org_id": "00000000-0000-0000-0000-000000000001",
                "code": "AP-2034",
                "condominium_id": "ccccccc1-0000-0000-0000-000000000001",
                "active": True,
            }])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums",
            [MockResp(data=[{
                "id": "ccccccc1-0000-0000-0000-000000000001",
                "name": "Edifício Aurora",
                "org_id": "00000000-0000-0000-0000-000000000001",
            }])],
        )
        svc._scoped.set_sequential_responses(
            "appointments", [MockResp(data=[])],
        )

        handler = build_tool_handler(scheduling_service=svc)
        result = handler(ToolCall(
            call_id="pa_1",
            name="propose_appointment",
            arguments={
                "property_code": "AP-2034",
                "requested_date": "2026-05-15",
                "time_window": "morning",
            },
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "success"
        assert len(payload["slots"]) > 0
        # Top-3 cap.
        assert len(payload["slots"]) <= 3

    def test_propose_appointment_returns_failure_on_unknown_property(self):
        from app.services.tool_registry import build_tool_handler

        svc, MockResp = self._make_service()
        svc._scoped.set_sequential_responses("properties", [MockResp(data=[])])

        handler = build_tool_handler(scheduling_service=svc)
        result = handler(ToolCall(
            call_id="pa_2",
            name="propose_appointment",
            arguments={
                "property_code": "AP-MISSING",
                "requested_date": "2026-05-15",
                "time_window": "any",
            },
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "failure"
        assert "Property code not found" in payload["error"]

    def test_confirm_appointment_inserts_and_returns_id(self):
        from app.services.tool_registry import build_tool_handler

        svc, MockResp = self._make_service()
        new_id = "aaaaaaa9-0000-0000-0000-000000000099"
        svc._scoped.set_sequential_responses(
            "properties",
            [MockResp(data=[{
                "id": "ppppppp1-0000-0000-0000-000000000001",
                "org_id": "00000000-0000-0000-0000-000000000001",
                "code": "AP-2034",
                "condominium_id": "ccccccc1-0000-0000-0000-000000000001",
                "active": True,
            }])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums",
            [MockResp(data=[{
                "id": "ccccccc1-0000-0000-0000-000000000001",
                "name": "Edifício Aurora",
                "org_id": "00000000-0000-0000-0000-000000000001",
            }])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockResp(data=[]),                    # re-validation
                MockResp(data=[{"id": new_id}]),      # insert
            ],
        )

        handler = build_tool_handler(scheduling_service=svc)
        result = handler(ToolCall(
            call_id="ca_1",
            name="confirm_appointment",
            arguments={
                "property_code": "AP-2034",
                "services": ["photos"],
                "start_at": "2026-05-15T10:00:00-03:00",
                "end_at": "2026-05-15T11:30:00-03:00",
            },
        ))
        payload = json.loads(result.content)
        assert payload["status"] == "success"
        assert payload["appointment_id"] == new_id

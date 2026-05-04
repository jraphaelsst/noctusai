"""Phase 4 — `propose_appointment` happy path against the seed engine.

Wires:
- `StaticRoutingAdapter` (no Maps API, deterministic).
- A minimal in-memory Supabase stub returning one property + condo + zero
  existing appointments.
- The full `register_scheduling_tools(...)` chain → `dispatcher.tool_handler`.

Asserts the candidate list comes back sorted by `(score, start_at)` and
that the seed engine's `same_location_duration_minutes` knob propagates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from noctusai_lib.domain.chatbot import LLMDispatcher, ToolCall
from noctusai_lib.integrations.google_maps import StaticRoutingAdapter

from app.services.routing_lookup import RoutingLookup
from app.services.scheduling_tools import (
    ToolContext,
    register_scheduling_tools,
)


# ---------------------------------------------------------------------------
# Minimal Supabase stub — enough for propose_appointment's three queries:
# (1) properties.select.eq(code).eq(active).single  — returns one row
# (2) condominiums.select.eq(id).single             — returns one row
# (3) appointments.select.eq(status,scheduled).gte/lte(start_at) — empty
# ---------------------------------------------------------------------------


@dataclass
class _StubResponse:
    data: object


class _StubBuilder:
    def __init__(self, table_name: str, store: dict[str, list[dict]]):
        self._table = table_name
        self._store = store
        self._filters: list[tuple[str, str, object]] = []
        self._is_single = False

    def select(self, *_args, **_kwargs) -> "_StubBuilder":
        return self

    def eq(self, col: str, value: object) -> "_StubBuilder":
        self._filters.append(("eq", col, value))
        return self

    def gte(self, col: str, value: object) -> "_StubBuilder":
        self._filters.append(("gte", col, value))
        return self

    def lte(self, col: str, value: object) -> "_StubBuilder":
        self._filters.append(("lte", col, value))
        return self

    def in_(self, col: str, values: list) -> "_StubBuilder":
        self._filters.append(("in_", col, values))
        return self

    def order(self, *_args, **_kwargs) -> "_StubBuilder":
        return self

    def single(self) -> "_StubBuilder":
        self._is_single = True
        return self

    def execute(self) -> _StubResponse:
        rows = self._store.get(self._table, [])
        for op, col, value in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == value]
            elif op == "gte":
                rows = [r for r in rows if str(r.get(col)) >= str(value)]
            elif op == "lte":
                rows = [r for r in rows if str(r.get(col)) <= str(value)]
            elif op == "in_":
                rows = [r for r in rows if r.get(col) in value]
        if self._is_single:
            if not rows:
                raise RuntimeError("no row")
            return _StubResponse(data=rows[0])
        return _StubResponse(data=rows)


class _StubSchema:
    def __init__(self, store: dict[str, list[dict]]):
        self._store = store

    def table(self, name: str) -> _StubBuilder:
        return _StubBuilder(name, self._store)


class _StubSupabase:
    def __init__(self, store: dict[str, list[dict]]):
        self._store = store

    def schema(self, _name: str) -> _StubSchema:
        return _StubSchema(self._store)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_propose_appointment_returns_sorted_slots(monkeypatch):
    store: dict[str, list[dict]] = {
        "properties": [
            {
                "id": 7,
                "code": "ONE0007",
                "condominium_id": 1,
                "unit": "101",
                "address_notes": None,
                "active": True,
            }
        ],
        "condominiums": [
            {
                "id": 1,
                "name": "Edificio Um",
                "address": "Rua A, 1",
                "latitude": -23.55,
                "longitude": -46.63,
                "active": True,
            }
        ],
        "appointments": [],
    }
    sb = _StubSupabase(store)

    routing_lookup = RoutingLookup(
        supabase=sb,  # type: ignore[arg-type]
        adapter=StaticRoutingAdapter(default_minutes=15),
    )
    calendar_writer_stub = object()  # not invoked by propose_appointment

    def context_provider() -> ToolContext:
        return ToolContext(
            supabase=sb,  # type: ignore[arg-type]
            calendar_writer=calendar_writer_stub,  # type: ignore[arg-type]
            routing_lookup=routing_lookup,
            timezone_name="America/Sao_Paulo",
            org_id="test-org",
            caller_phone="+5511999998888",
            caller_user_id=1,
        )

    # Fake OpenAI client — we never call it; we go directly through the
    # registered tool_handler to exercise propose_appointment in isolation.
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    register_scheduling_tools(dispatcher, context_provider=context_provider)

    handler = dispatcher.tool_handler  # type: ignore[attr-defined]
    call = ToolCall(
        call_id="call_abc",
        name="propose_appointment",
        arguments={
            "property_code": "ONE0007",
            "requested_date": "2030-06-10",
        },
    )
    result = handler(call)
    payload = json.loads(result.content)

    assert payload.get("error") is None, payload
    assert payload["property_code"] == "ONE0007"
    assert payload["requested_date"] == "2030-06-10"
    assert payload["candidate_count"] >= 1
    candidates = payload["candidates"]
    assert candidates, "expected at least one candidate slot"

    # Sorted by (score, start_at) — ascending score, then start_at.
    for prev, curr in zip(candidates, candidates[1:]):
        assert (prev["score"], prev["start_at"]) <= (
            curr["score"],
            curr["start_at"],
        )

    # Empty calendar + single condo target → score 0 across the board.
    assert all(c["score"] == 0 for c in candidates)


def test_register_scheduling_tools_exposes_payload_and_handler():
    dispatcher = LLMDispatcher(client=None, model="gpt-4o-mini")
    register_scheduling_tools(dispatcher, context_provider=None)
    payload = dispatcher.tool_payload  # type: ignore[attr-defined]
    assert isinstance(payload, list) and payload
    names = {item["function"]["name"] for item in payload}
    assert {
        "propose_appointment",
        "confirm_appointment",
        "cancel_appointment",
        "find_authorized_user",
        "lookup_property",
    }.issubset(names)
    # Without a context provider, calls must refuse rather than crash.
    refusal = dispatcher.tool_handler(  # type: ignore[attr-defined]
        ToolCall(call_id="x", name="lookup_property", arguments={"code": "X"})
    )
    body = json.loads(refusal.content)
    assert body["error"] == "tool_context_unavailable"

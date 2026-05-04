"""`lookup_property` tool handler — property code resolution.

Ported from `whatsapp-google-scheduling/tests/test_openai_tools_lookup_property.py`.

Source-side: a free `handler({"code": ...}, ctx)` callable hit a
SQLAlchemy-backed `properties` table.
Product-side: `LookupProperty()` dataclass exposing `__call__(args, ToolContext)`,
running against a Supabase-shaped client. Same contract:
  - found: True/False + code echoed back in normalized uppercase form.
  - condominium info nested with `has_coordinates` flag.
  - missing/empty code → `{"found": False, "error": "missing_code"}`.
  - inactive properties don't match (the `.eq("active", True)` filter).
  - whitespace + lowercase normalized to uppercase before lookup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from noctusai_lib.domain.chatbot import ToolCall

from app.services.scheduling_tools import LookupProperty, ToolContext


# ---------------------------------------------------------------------------
# Stubs — same minimal Supabase shape used by `test_scheduling_tools.py`.
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

    def single(self) -> "_StubBuilder":
        self._is_single = True
        return self

    def execute(self) -> _StubResponse:
        rows = self._store.get(self._table, [])
        for op, col, value in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == value]
        if self._is_single:
            if not rows:
                # Source's "no row" path raises so the production code's
                # `except Exception` returns None — preserve that here.
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
# Source seed: ONE0007 active, OLD0001 inactive, NOGPS01 with no coords.
# ---------------------------------------------------------------------------


def _store() -> dict[str, list[dict]]:
    return {
        "properties": [
            {
                "id": 1,
                "code": "ONE0007",
                "condominium_id": 1,
                "unit": "Casa 07",
                "address_notes": None,
                "active": True,
            },
            {
                "id": 2,
                "code": "OLD0001",
                "condominium_id": 1,
                "unit": None,
                "address_notes": None,
                "active": False,  # inactive — must not match.
            },
            {
                "id": 3,
                "code": "NOGPS01",
                "condominium_id": 2,
                "unit": "Bloco B",
                "address_notes": None,
                "active": True,
            },
        ],
        "condominiums": [
            {
                "id": 1,
                "name": "Reserva One",
                "address": "Estrada do Capuava, Cotia, SP",
                "latitude": -23.6,
                "longitude": -46.88,
                "active": True,
            },
            {
                "id": 2,
                "name": "Sem Coordenadas",
                "address": "Rua Sem GPS, 1",
                "latitude": None,
                "longitude": None,
                "active": True,
            },
        ],
    }


def _ctx(sb) -> ToolContext:
    """Stub `ToolContext` — `lookup_property` only consumes `.supabase`."""
    return ToolContext(
        supabase=sb,  # type: ignore[arg-type]
        calendar_writer=object(),  # type: ignore[arg-type]
        routing_lookup=object(),  # type: ignore[arg-type]
        timezone_name="America/Sao_Paulo",
        org_id="test-org",
        caller_phone=None,
        caller_user_id=None,
    )


def _invoke(args: dict) -> dict:
    sb = _StubSupabase(_store())
    handler = LookupProperty()
    args_with_call = dict(args)
    args_with_call["__call_id"] = "test_call"
    result = handler(args_with_call, _ctx(sb))
    return json.loads(result.content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_lookup_property_returns_condominium_info_for_known_active_code() -> None:
    payload = _invoke({"code": "ONE0007"})

    assert payload["found"] is True
    assert payload["code"] == "ONE0007"
    assert payload["unit"] == "Casa 07"
    assert payload["condominium"]["name"] == "Reserva One"
    assert payload["condominium"]["has_coordinates"] is True


def test_lookup_property_normalizes_code_to_uppercase() -> None:
    payload = _invoke({"code": " one0007 "})

    assert payload["found"] is True
    assert payload["code"] == "ONE0007"


def test_lookup_property_returns_not_found_for_unknown_code() -> None:
    payload = _invoke({"code": "ZZZ9999"})

    assert payload["found"] is False
    assert payload["code"] == "ZZZ9999"


def test_lookup_property_returns_not_found_for_inactive_code() -> None:
    payload = _invoke({"code": "OLD0001"})

    assert payload["found"] is False
    assert payload["code"] == "OLD0001"


def test_lookup_property_handles_missing_code_arg() -> None:
    payload = _invoke({})

    assert payload["found"] is False
    assert payload["error"] == "missing_code"


def test_lookup_property_flags_condominium_without_coordinates() -> None:
    payload = _invoke({"code": "NOGPS01"})

    assert payload["found"] is True
    assert payload["condominium"]["has_coordinates"] is False

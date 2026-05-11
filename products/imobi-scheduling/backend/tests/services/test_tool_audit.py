"""Tests for `app.services.tool_audit` — the Supabase-shaped audit writer.

The seed ships `make_audit_writer(db, table_class)` against SQLAlchemy
Session. This product is Supabase-client based; the adapter built here
maps `(ToolCall, ToolResult)` → `AuditRecord.to_row_kwargs()` →
`admin_client.schema(...).table(...).insert(...).execute()`.

Best-effort guarantee is REQUIRED — failures log + swallow, never raise.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

from app.services.tool_audit import (
    SCHEMA,
    TABLE,
    _decode_result_status,
    make_supabase_audit_writer,
)


@pytest.fixture
def admin_client():
    """A MagicMock admin client whose `.schema(...).table(...)` chain is
    inspectable. Tests assert on the recorded calls."""
    client = MagicMock(name="admin_client")
    return client


class TestDecodeResultStatus:
    """The status mapper inspects the JSON-encoded `ToolResult.content`."""

    def test_failure_payload_maps_to_failure(self):
        content = json.dumps({"status": "failure", "error": "boom"})
        status, error = _decode_result_status(ToolResult(call_id="x", content=content))
        assert status == "failure"
        assert error == "boom"

    def test_unknown_tool_maps_to_unknown_tool(self):
        content = json.dumps({"status": "unknown_tool", "tool": "ghost"})
        status, error = _decode_result_status(ToolResult(call_id="x", content=content))
        assert status == "unknown_tool"
        assert error is None

    def test_not_implemented_maps_to_success(self):
        content = json.dumps({"status": "not_implemented"})
        status, error = _decode_result_status(ToolResult(call_id="x", content=content))
        assert status == "success"
        assert error is None

    def test_bare_string_defaults_to_success(self):
        """A non-JSON content (rare but possible) doesn't crash the
        status decode — defaults to `success` so the audit row still
        lands."""
        status, error = _decode_result_status(ToolResult(call_id="x", content="hi"))
        assert status == "success"
        assert error is None

    def test_empty_content_defaults_to_success(self):
        status, error = _decode_result_status(ToolResult(call_id="x", content=""))
        assert status == "success"
        assert error is None


class TestMakeSupabaseAuditWriter:
    """The writer factory + the writer callback shape."""

    def test_requires_admin_client(self):
        with pytest.raises(ValueError, match="non-None admin_client"):
            make_supabase_audit_writer(admin_client=None, org_id=uuid4())

    def test_writer_inserts_audit_row_with_org_id(self, admin_client):
        org_id = uuid4()
        writer = make_supabase_audit_writer(admin_client=admin_client, org_id=org_id)
        call = ToolCall(call_id="c1", name="lookup_property", arguments={"code": "AP-1"})
        result = ToolResult(
            call_id="c1",
            content=json.dumps({"status": "not_implemented", "echo": {"code": "AP-1"}}),
        )

        writer(call, result)

        # admin_client.schema(SCHEMA).table(TABLE) was acquired once at
        # factory time; the insert happens per-call.
        admin_client.schema.assert_called_once_with(SCHEMA)
        table_handle = admin_client.schema.return_value.table.return_value
        table_handle.insert.assert_called_once()

        # Inspect the inserted payload — the org_id must be stamped, the
        # tool_name preserved, the arguments JSONB-safe, the seed's int
        # `user_id` field stripped when no provider supplies it.
        inserted = table_handle.insert.call_args[0][0]
        assert inserted["org_id"] == str(org_id)
        assert inserted["tool_name"] == "lookup_property"
        assert inserted["status"] == "success"  # not_implemented → success
        assert inserted["arguments"] == {"code": "AP-1"}
        assert inserted["result"]["status"] == "not_implemented"
        # No user_id provider → key absent from the insert payload
        # (we strip it because the seed int field doesn't match our UUID col).
        assert "user_id" not in inserted

    def test_writer_records_failure_status(self, admin_client):
        writer = make_supabase_audit_writer(admin_client=admin_client, org_id=uuid4())
        call = ToolCall(call_id="c2", name="propose_appointment", arguments={})
        result = ToolResult(
            call_id="c2",
            content=json.dumps({"status": "failure", "error": "DB unavailable"}),
        )
        writer(call, result)
        inserted = admin_client.schema.return_value.table.return_value.insert.call_args[0][0]
        assert inserted["status"] == "failure"
        assert inserted["error"] == "DB unavailable"

    def test_writer_threads_conversation_and_user_providers(self, admin_client):
        conv_id = "wa-conv-123"
        user_uuid = uuid4()
        writer = make_supabase_audit_writer(
            admin_client=admin_client,
            org_id=uuid4(),
            conversation_id_provider=lambda: conv_id,
            user_id_provider=lambda: user_uuid,
        )
        writer(
            ToolCall(call_id="c3", name="confirm_appointment", arguments={}),
            ToolResult(call_id="c3", content=json.dumps({"status": "not_implemented"})),
        )
        inserted = admin_client.schema.return_value.table.return_value.insert.call_args[0][0]
        assert inserted["conversation_id"] == conv_id
        assert inserted["user_id"] == str(user_uuid)

    def test_writer_swallows_db_exceptions_per_best_effort_contract(
        self, admin_client, caplog,
    ):
        """The seed `make_audit_writer` contract is best-effort. DB
        exceptions log at WARNING and never propagate to the caller —
        otherwise audit failures would break user-facing LLM dispatch."""
        admin_client.schema.return_value.table.return_value.insert.return_value.execute.side_effect = (
            RuntimeError("connection refused")
        )
        writer = make_supabase_audit_writer(admin_client=admin_client, org_id=uuid4())

        # Must not raise.
        writer(
            ToolCall(call_id="c4", name="lookup_property", arguments={}),
            ToolResult(call_id="c4", content=json.dumps({"status": "not_implemented"})),
        )

        warning_messages = [
            rec.message for rec in caplog.records
            if rec.levelname == "WARNING" and "tool_call_audit insert failed" in rec.message
        ]
        assert warning_messages, "Expected a WARNING about the failed insert"

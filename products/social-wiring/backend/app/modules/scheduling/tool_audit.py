"""Supabase-backed tool-call audit adapter for the social-wiring
``scheduling`` module. Absorbed from ``imobi-scheduling`` (Wave 2.3).

The seed ships ``noctusai_lib.domain.ai.tool_audit.make_audit_writer``
which closes over a SQLAlchemy ``Session`` + ORM class. social-wiring is
Supabase-client based (no SQLAlchemy ORM layer) — consumer-side adapter
required. This module composes the seed's ``AuditRecord`` DTO with a
Supabase admin client writing to ``social_wiring.sched_tool_call_audits``.

Per ``KB § PATTERNS/llm-tool-audit.md`` — ``arguments`` + ``result``
JSONB may carry PII. The scheduling domain is real-estate (not Art. 11
sensitive); no redaction wired here (the ``sanitization`` module redacts
tool-result PII before it reaches the LLM surface).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable
from uuid import UUID

from noctusai_lib.domain.ai.tool_audit import AuditRecord, AuditStatus, now_utc
from noctusai_lib.domain.chatbot import ToolCall, ToolResult

logger = logging.getLogger(__name__)


SCHEMA = "social_wiring"
TABLE = "sched_tool_call_audits"

_clock: Callable[[], float] = time.monotonic


def _decode_result_status(result: ToolResult) -> tuple[AuditStatus, str | None]:
    try:
        payload = json.loads(result.content) if result.content else {}
    except (json.JSONDecodeError, TypeError):
        return ("success", None)

    raw = payload.get("status") if isinstance(payload, dict) else None
    if raw == "failure":
        return ("failure", str(payload.get("error") or "(no error string)"))
    if raw == "unknown_tool":
        return ("unknown_tool", None)
    return ("success", None)


def make_supabase_audit_writer(
    *,
    admin_client: Any,
    org_id: UUID,
    conversation_id_provider: Callable[[], str | None] | None = None,
    user_id_provider: Callable[[], UUID | None] | None = None,
) -> Callable[[ToolCall, ToolResult], None]:
    """Build a ``LLMDispatcher.AuditWriter`` adapter persisting rows to
    ``social_wiring.sched_tool_call_audits``. Best-effort: failures log
    at WARNING and never raise (the seed ``make_audit_writer`` contract)."""
    if admin_client is None:
        raise ValueError(
            "make_supabase_audit_writer requires a non-None admin_client. "
            "Pass the resolved admin client (e.g. from app.dependencies.get_admin_client())."
        )

    table_handle = admin_client.schema(SCHEMA).table(TABLE)

    def _write(call: ToolCall, result: ToolResult) -> None:
        status, error = _decode_result_status(result)
        record = AuditRecord(
            tool_name=call.name,
            status=status,
            duration_ms=0,
            started_at=now_utc(),
            arguments=call.arguments,
            result=_safe_jsonable_result(result.content),
            error=error,
            gpt_call_id=call.call_id,
            tool_call_id=call.call_id,
            conversation_id=(
                conversation_id_provider() if conversation_id_provider else None
            ),
        )

        row_kwargs = record.to_row_kwargs()
        if user_id_provider is not None:
            uid = user_id_provider()
            if uid is not None:
                row_kwargs["user_id"] = str(uid)
        else:
            row_kwargs.pop("user_id", None)
        row_kwargs["org_id"] = str(org_id)
        if "user_id" in row_kwargs and row_kwargs["user_id"] is None:
            row_kwargs.pop("user_id")

        try:
            table_handle.insert(row_kwargs).execute()
        except Exception as exc:  # noqa: BLE001 — best-effort audit.
            logger.warning(
                "tool_call_audit insert failed for tool=%s status=%s: %s",
                call.name,
                status,
                exc,
            )

    return _write


def _safe_jsonable_result(content: str) -> Any:
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": content}


__all__ = ["make_supabase_audit_writer", "SCHEMA", "TABLE"]

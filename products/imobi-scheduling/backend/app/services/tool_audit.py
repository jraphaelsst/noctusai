"""Supabase-backed adapter wiring the tool-call audit trail.

**Why this module exists** — verify-the-seed-ships-it test, 2026-05-11.
The seed ships `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db,
table_class)` which closes over a **SQLAlchemy `Session`** and a
**SQLAlchemy ORM class**. Imobi Scheduling — like every other recently-
scaffolded product — is **Supabase-client based** (no SQLAlchemy ORM
layer). The seed factory does NOT cover the Supabase path; consumer-side
adapter required.

**N=1 carve-out.** This is the first Supabase consumer of the tool-audit
seam. Ship against the gap, surface a follow-up. If a second product
(therapy / mailing) needs Supabase-backed `tool_call_audits` persistence,
the recurrence rule fires (N=2 → triage / formalize) — lift this writer
into `noctusai_lib.domain.ai.tool_audit.make_supabase_audit_writer(...)`
mirroring the existing factory shape. Tracked in PROJECT.md §6 Phase 6
``**Improvements:**`` block.

**Adapter shape.** The `LLMDispatcher.AuditWriter` signature is
`Callable[[ToolCall, ToolResult], None]` (post-tool-call callback at the
dispatch site). The seed's `AuditRecord` is the canonical persistence
DTO — same field-set as the `tool_call_audits` table the product
migration ships. The adapter:

  1. Maps `(ToolCall, ToolResult)` → `AuditRecord` (status / duration
     inferred from `ToolResult.content`).
  2. Calls into the product's `imobi_scheduling.tool_call_audits` table
     via the Supabase admin client (RLS scoped to `org_id`).
  3. Best-effort — DB exceptions log at WARNING and swallow per the
     seed's `make_audit_writer` contract.

Per `KB § PATTERNS/llm-tool-audit.md` — `arguments` + `result` JSONB may
carry PII. Products handling Art. 11 sensitive data MUST redact before
the AuditRecord lands. Imobi Scheduling is not Art. 11 (real-estate
scheduling, not clinical/health) — no redaction wired.
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


SCHEMA = "imobi_scheduling"
TABLE = "tool_call_audits"

# Module-level dispatch-clock so callers (and tests) can override.
_clock: Callable[[], float] = time.monotonic


def _decode_result_status(result: ToolResult) -> tuple[AuditStatus, str | None]:
    """Inspect the ``ToolResult.content`` JSON for an embedded
    ``status`` discriminator.

    Tool-stub responses (`app/services/tool_registry.py`) embed a
    ``status`` field — ``"success"`` / ``"failure"`` /
    ``"unknown_tool"`` / ``"not_implemented"``. We map the latter two
    to seed-level statuses (`AuditStatus`) for audit-row consistency.

    Returns:
        ``(status, error)`` where ``error`` is non-None only on
        ``failure``.
    """
    try:
        payload = json.loads(result.content) if result.content else {}
    except (json.JSONDecodeError, TypeError):
        return ("success", None)

    raw = payload.get("status") if isinstance(payload, dict) else None
    if raw == "failure":
        return ("failure", str(payload.get("error") or "(no error string)"))
    if raw == "unknown_tool":
        return ("unknown_tool", None)
    # "not_implemented" / "success" / unknown → success at audit layer
    # (LLM still saw a structured response — the dispatch succeeded).
    return ("success", None)


def make_supabase_audit_writer(
    *,
    admin_client: Any,
    org_id: UUID,
    conversation_id_provider: Callable[[], str | None] | None = None,
    user_id_provider: Callable[[], UUID | None] | None = None,
) -> Callable[[ToolCall, ToolResult], None]:
    """Build a `LLMDispatcher.AuditWriter` adapter that persists rows
    to ``imobi_scheduling.tool_call_audits`` via the Supabase admin
    client.

    Args:
        admin_client: A Supabase admin client (service-role-keyed).
            Late-binding via the wrapper in `app.dependencies`; pass
            the bare admin client here. The writer scopes to ``SCHEMA``
            internally.
        org_id: Single-agency v1 (PROJECT.md Phase 0 Q4) — the org_id
            stamped on every audit row.
        conversation_id_provider: Optional callable returning the
            conversation_id for the current dispatch. Defaults to None
            → the audit row's ``conversation_id`` column is NULL.
            Wired by `app.services.conversation` per-message.
        user_id_provider: Optional callable returning the authenticated
            user UUID for the current dispatch. Defaults to None →
            ``user_id`` is NULL on the audit row. Wired by
            `app.services.conversation` per-message.

    Returns:
        Callable matching `noctusai_lib.domain.chatbot.AuditWriter`
        (i.e. ``Callable[[ToolCall, ToolResult], None]``). Best-effort:
        failures log at WARNING and never raise.
    """
    if admin_client is None:
        raise ValueError(
            "make_supabase_audit_writer requires a non-None admin_client. "
            "Pass the resolved admin client (e.g. from app.dependencies.get_admin_client())."
        )

    table_handle = admin_client.schema(SCHEMA).table(TABLE)

    def _write(call: ToolCall, result: ToolResult) -> None:
        status, error = _decode_result_status(result)
        # Duration is unknown at this seam — the LLMDispatcher does not
        # surface it via AuditWriter. Stamp 0; revisit when the seed
        # passes a duration into the writer (filed in Improvements).
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
        # AuditRecord.user_id is int-typed at the seed (SQLAlchemy bigint
        # legacy from the sibling). The product's column is UUID. Pull the
        # user_id from the provider directly so the JSONB-safe coercion
        # in to_row_kwargs() doesn't drop our UUID string.
        if user_id_provider is not None:
            uid = user_id_provider()
            if uid is not None:
                row_kwargs["user_id"] = str(uid)
        else:
            row_kwargs.pop("user_id", None)
        row_kwargs["org_id"] = str(org_id)
        # Drop seed-int field that doesn't match our UUID column when
        # we didn't override above (None → leave NULL).
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
    """Coerce ToolResult.content (a JSON string per dispatcher contract)
    into a JSONB-safe value. Falls back to ``{"_raw": content}`` on
    parse failure so audit rows never go missing.
    """
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": content}


__all__ = ["make_supabase_audit_writer", "SCHEMA", "TABLE"]

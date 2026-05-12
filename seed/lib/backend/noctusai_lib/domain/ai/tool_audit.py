"""Tool-call audit trail — opt-in writer + in-memory record shape.

Pattern (lifted from sibling repo `whatsapp-google-scheduling/app/services/audit_service.py`):
the LLM dispatcher (chatbot framework or any consumer) calls
``audit_writer(record)`` after each tool dispatch — successful, failing,
or unknown-tool. The writer persists one row to the consuming product's
``tool_call_audits`` table.

**Per-product table.** Each product owns its own table (per the
cross-product LGPD block — no shared platform tables until encryption
lands). The lib does NOT ship a SQLAlchemy ORM model — the product
defines its own `ToolCallAudit` class against its own `Base`. This
module ships:

  - The in-memory record shape (`AuditRecord`) every consumer fills.
  - The writer factory `make_audit_writer(db, table_class)` that
    closes over the product's session + ORM class.
  - The default writer logic — best-effort, logs + swallows failures.
  - The `_safe_jsonable` helper for non-JSON-serializable args/results.

**Best-effort guarantee.** A DB exception NEVER raises to the caller.
The audit table is for visibility, not correctness — losing a row to
a transient hiccup is much less costly than failing the user-facing
dispatch because of it. Per the noctusai logging convention (no
silent except), failures DO log at WARNING — the audit-trail gap is
observable.

**Wiring at the consumer side** (the chatbot framework's
``llm_dispatcher.py``, lands in ``projects/whatsapp-seed-absorption/``
Phase 5):

    from noctusai_lib.domain.ai.tool_audit import make_audit_writer
    from app.models.tool_call_audit import ToolCallAudit

    audit_writer = make_audit_writer(db, ToolCallAudit)
    # ... dispatcher calls audit_writer(AuditRecord(...)) after each tool

**LGPD note.** `arguments` and `result` may carry PII. Products handling
Art. 11 sensitive data (e.g. clinical text) MUST redact those fields
before constructing the `AuditRecord`. See
`KB § PATTERNS/llm-tool-audit.md § LGPD redaction`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Literal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


AuditStatus = Literal["success", "failure", "unknown_tool"]


@dataclass(slots=True)
class AuditRecord:
    """In-memory representation of one tool-call event.

    Built by the LLM dispatcher; passed to an `AuditWriter`. Mirror
    fields populated for joinability:

      - `correlation_id` joins to log lines via the
        `noctusai_lib.primitives._correlation` context var.
      - `gpt_call_id` is the OpenAI-issued tool_call.id (informational
        only — not unique on its own).
      - `tool_call_id` is the platform-issued ID (when distinct from
        the GPT-issued one).
      - `conversation_id` groups all tool calls within one bot
        conversation.
      - `user_id` ties to the requesting user (nullable — unauthorized
        callers, system flows).
    """

    tool_name: str
    status: AuditStatus
    duration_ms: int
    started_at: datetime
    arguments: dict[str, Any] | None = None
    result: Any = None
    error: str | None = None
    correlation_id: str | None = None
    gpt_call_id: str | None = None
    tool_call_id: str | None = None
    conversation_id: str | None = None
    user_id: int | None = None

    def to_row_kwargs(self) -> dict[str, Any]:
        """Return kwargs suitable for `TableClass(**kwargs)` construction.

        Pre-applies `_safe_jsonable` to `arguments` and `result` so
        Postgres JSONB columns can accept them even when the source
        value isn't a plain dict (e.g. a Pydantic model dump that
        round-trips through JSON cleanly, or a non-serializable
        sentinel that gets repr'd).
        """
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "arguments": _safe_jsonable(self.arguments),
            "result": _safe_jsonable(self.result),
            "error": self.error,
            "correlation_id": self.correlation_id,
            "gpt_call_id": self.gpt_call_id,
            "tool_call_id": self.tool_call_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
        }


AuditWriter = Callable[[AuditRecord], None]


def make_audit_writer(db: "Session", table_class: type) -> AuditWriter:
    """Build an audit writer closure bound to a session + ORM class.

    The returned callable is **best-effort**: DB exceptions are
    rolled-back, logged at WARNING, and swallowed. The caller never
    sees an audit failure.

    Args:
        db: Open SQLAlchemy session. The closure does NOT close it —
            the caller owns lifecycle.
        table_class: The product's concrete `ToolCallAudit` ORM class
            (a subclass of the product's `Base`). The class must accept
            the kwargs in `AuditRecord.to_row_kwargs()` — typically
            generated from the migration template at
            `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`.
    """

    def write(record: AuditRecord) -> None:
        try:
            row = table_class(**record.to_row_kwargs())
            db.add(row)
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "tool_audit writer: rollback after failed commit also raised; ignoring"
                )
            logger.warning(
                "tool_call_audit write failed for tool=%s user_id=%s: %s",
                record.tool_name,
                record.user_id,
                exc,
            )

    return write


def _safe_jsonable(value: Any) -> Any:
    """Coerce a value into something a Postgres JSONB column will accept.

    - ``None`` → ``None`` (allowed).
    - ``dict`` / ``list`` already JSON-clean → returned as-is.
    - anything else → round-tripped through ``json.dumps(..., default=str)``
      and parsed back, so Pydantic models / dataclasses / Decimals / etc.
      land as plain JSON.
    - non-serializable values → wrapped as ``{"_repr": repr(value)}``
      with a debug log; audit row still lands.

    accept-with-rationale: "_safe_jsonable accepts string + repr
    fallbacks instead of raising" in
    KB § PATTERNS/accept-with-rationale.md — the audit writer is
    best-effort; raising would either break user-facing dispatch or
    multiply silent-error wrappers at every call site. Revisit when a
    BI consumer reports unusable bare-string / _repr rows.
    """
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        logger.debug(
            "tool_audit: value not JSON-round-trippable (%s); storing repr",
            exc,
        )
        return {"_repr": repr(value)}


def now_utc() -> datetime:
    """Convenience: timezone-aware UTC `datetime.now()`. Use as default for
    `AuditRecord.started_at` when the dispatcher doesn't carry a clock."""
    return datetime.now(timezone.utc)


def apply_feature_redaction(
    record: AuditRecord,
    *,
    redact_arguments: Optional[Callable[[Any], Any]] = None,
    redact_result: Optional[Callable[[Any], Any]] = None,
) -> AuditRecord:
    """Return a new `AuditRecord` with arguments/result run through
    the feature's redactor callables.

    Defensive: if a redactor raises, log + fall back to dropping the value
    rather than persist unredacted PII (LGPD-safe failure mode). The
    record is *replaced* not mutated — callers can keep the raw record
    for non-audit observability (e.g. logging at debug level).
    """
    new_args = record.arguments
    new_result = record.result
    if redact_arguments is not None:
        try:
            new_args = redact_arguments(record.arguments)
        except Exception as exc:
            logger.warning(
                "tool_audit: redact_arguments raised for tool=%s; dropping value: %s",
                record.tool_name,
                exc,
            )
            new_args = None
    if redact_result is not None:
        try:
            new_result = redact_result(record.result)
        except Exception as exc:
            logger.warning(
                "tool_audit: redact_result raised for tool=%s; dropping value: %s",
                record.tool_name,
                exc,
            )
            new_result = None
    return AuditRecord(
        tool_name=record.tool_name,
        status=record.status,
        duration_ms=record.duration_ms,
        started_at=record.started_at,
        arguments=new_args,
        result=new_result,
        error=record.error,
        correlation_id=record.correlation_id,
        gpt_call_id=record.gpt_call_id,
        tool_call_id=record.tool_call_id,
        conversation_id=record.conversation_id,
        user_id=record.user_id,
    )


__all__ = [
    "AuditRecord",
    "AuditStatus",
    "AuditWriter",
    "apply_feature_redaction",
    "make_audit_writer",
    "now_utc",
]

"""Tool-call audit-writer factory — wires seed `make_audit_writer` to the
product's `ToolCallAudit` ORM class.

Per `KB § PATTERNS/llm-tool-audit.md`: every LLM dispatch site in PF
(see `app.services.ai_service` and `app.services.monthly_narrative_service`)
calls `audit_writer(record)` after the chat-completion result lands. The
writer persists one row to `"personal-finance".tool_call_audits` via
SQLAlchemy.

Best-effort: the seed `make_audit_writer` rolls back + logs on DB error;
tool dispatch is never broken by an audit-side failure. See
`noctusai_lib.domain.ai.tool_audit.make_audit_writer` for the guarantee.

**Lazy SQLAlchemy session.** PF's primary data path is the Supabase
admin/user client; SQLAlchemy exists only because the seed audit-writer
contract requires a typed table class. We construct the engine +
sessionmaker lazily — the first time `get_audit_writer()` is called — so:

  - App boot doesn't require a Postgres connection string.
  - Settings without `postgres_url` get a noop writer (debug log + skip).
  - Tests can override `postgres_url` to point at a fixture DB.

When `postgres_url` is unset the audit writer is a noop — every dispatch
still completes, the audit row simply isn't written. This matches the
seed's best-effort semantics one level out.

**Redaction.** This module does NOT apply LGPD redaction itself — callers
at the dispatch site MUST scrub via the feature's registered
`redact_arguments` / `redact_result` callables (see
`app.services.ai_consent_features`) BEFORE building the `AuditRecord`.
The `build_audit_record` helper centralizes that pattern.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from app.config import settings
from app.models.tool_call_audit import ToolCallAudit
from noctusai_lib.domain.ai import get_feature
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    AuditWriter,
    make_audit_writer,
    now_utc,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


_engine: Optional["Engine"] = None
_session_factory = None


def _get_engine_and_factory():
    """Lazily construct the SQLAlchemy engine + sessionmaker.

    Returns (engine, session_factory) on success; (None, None) when
    `settings.postgres_url` is empty or the engine cannot be created.
    """
    global _engine, _session_factory
    if _engine is not None and _session_factory is not None:
        return _engine, _session_factory
    postgres_url = getattr(settings, "postgres_url", "")
    if not postgres_url:
        return None, None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        _engine = create_engine(
            postgres_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        return _engine, _session_factory
    except Exception:
        logger.exception(
            "audit_hook: failed to construct SQLAlchemy engine; tool_call_audit will skip writes"
        )
        return None, None


def _noop_writer(record: AuditRecord) -> None:
    """Used when no Postgres connection is configured. Best-effort means
    audit gaps are visible — log at debug so dev runs don't spam."""
    logger.debug(
        "audit_hook: postgres_url unset; skipping tool_call_audit write for tool=%s",
        record.tool_name,
    )


def get_audit_writer() -> AuditWriter:
    """Return an `AuditWriter` bound to a fresh SQLAlchemy session.

    Wraps `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, ToolCallAudit)`
    — seed pattern, no hand-rolled SQL. Each call to the returned writer
    opens a short-lived session, writes the row, commits, and closes.

    When `postgres_url` is unset, returns a noop writer that debug-logs
    each call so audit-trail gaps remain observable.
    """
    engine, session_factory = _get_engine_and_factory()
    if session_factory is None:
        return _noop_writer

    def write(record: AuditRecord) -> None:
        # Per-call session: seed `make_audit_writer` does the
        # try/commit/rollback/log dance internally; we just ensure the
        # session is closed when it's done.
        session = session_factory()
        try:
            inner = make_audit_writer(session, ToolCallAudit)
            inner(record)
        finally:
            session.close()

    return write


def build_audit_record(
    *,
    feature_key: str,
    tool_name: str,
    status: str,
    duration_ms: int,
    arguments: Optional[dict[str, Any]] = None,
    result: Any = None,
    error: Optional[str] = None,
    user_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> AuditRecord:
    """Construct an `AuditRecord` with redaction applied per the catalog feature.

    Looks up `feature_key` in the seed consent catalog and applies the
    feature's `redact_arguments` / `redact_result` callables (registered in
    `app.services.ai_consent_features`) BEFORE the record is built. If the
    feature has no redactor registered, the corresponding field is dropped
    to `None` for safety — PF is finance-LGPD sensitive and the audit table
    is NOT a free-text dump.

    Best-effort: a redaction callable that raises is logged at warning and
    the field falls back to `None` (over-redact rather than leak).
    """
    feature = get_feature(feature_key)

    def _apply(redactor, value, kind: str):
        if value is None:
            return None
        if redactor is None:
            # No redactor registered — over-redact (drop) to keep PII out of audit.
            logger.debug(
                "audit_hook: no %s redactor for feature=%s; dropping field",
                kind,
                feature_key,
            )
            return None
        try:
            return redactor(value)
        except Exception:
            logger.warning(
                "audit_hook: %s redactor raised for feature=%s; dropping field",
                kind,
                feature_key,
            )
            return None

    safe_arguments = _apply(
        getattr(feature, "redact_arguments", None), arguments, "arguments"
    )
    safe_result = _apply(getattr(feature, "redact_result", None), result, "result")

    return AuditRecord(
        tool_name=tool_name,
        status=status,  # type: ignore[arg-type]
        duration_ms=duration_ms,
        started_at=now_utc(),
        arguments=safe_arguments if isinstance(safe_arguments, dict) or safe_arguments is None else {"_value": safe_arguments},
        result=safe_result,
        error=error,
        user_id=user_id,
        correlation_id=correlation_id,
        conversation_id=conversation_id,
    )

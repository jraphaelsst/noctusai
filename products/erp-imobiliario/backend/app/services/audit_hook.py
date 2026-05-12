"""Tool-call audit-writer factory — wires seed `make_audit_writer` to the
product's `ToolCallAudit` ORM class.

Per `KB § PATTERNS/llm-tool-audit.md`: every LLM dispatch site builds an
`AuditRecord` and calls `get_audit_writer()(record)` after the call
returns. The writer persists one row to `erp.tool_call_audits` via
SQLAlchemy.

Best-effort: the seed `make_audit_writer` rolls back + logs on DB error;
tool dispatch is never broken by an audit-side failure. See
`noctusai_lib.domain.ai.tool_audit.make_audit_writer` for the guarantee.

**Lazy SQLAlchemy session.** ERP's primary data path is the Supabase
admin client (per `app/database.py`). SQLAlchemy is only needed for the
typed-table-class shape `make_audit_writer` requires. We construct the
engine + sessionmaker lazily — the first time `get_audit_writer()` is
called — so:

  - App boot doesn't require a Postgres connection string.
  - Settings without `postgres_url` get a noop writer (debug log + skip).
  - Tests can override `postgres_url` to point at a fixture DB.

When `postgres_url` is unset the audit writer is a noop — every dispatch
still completes, the audit row simply isn't written. This matches the
seed's best-effort semantics one level out.

Mirror of `products/media-scheduling/backend/app/services/audit_hook.py`
— the reference adopter (LLM-tool-audit rollout Phase 1).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from app.config import settings
from app.models.tool_call_audit import ToolCallAudit
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    AuditWriter,
    make_audit_writer,
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
    postgres_url = getattr(settings, "postgres_url", "") or ""
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
            "audit_hook: failed to construct SQLAlchemy engine; tool-call audit will skip writes"
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

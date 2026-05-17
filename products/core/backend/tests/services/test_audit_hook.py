"""Tool-call audit integration — core `ToolCallAudit` ORM ⇄ seed writer.

Mirrors the original canonical reference adopter (retired `media-scheduling`,
consolidated into `social-wiring` 2026-05-16; LLM-tool-audit rollout Phase 1).

What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into core's `public.tool_call_audits` table.
  - JSONB columns accept dict / list values (the `_safe_jsonable` round-trip).
  - DB exceptions are swallowed (best-effort guarantee — never break the
    digest pipeline on an audit failure).
  - `app.services.audit_hook.get_audit_writer()` returns a noop writer
    when `settings.postgres_url` is empty (so the digest keeps going).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    make_audit_writer,
    now_utc,
)


@pytest.fixture()
def session_factory():
    """In-memory SQLite session bound to core's `ToolCallAudit` ORM.

    The model's table args carry `schema="public"` (also the SQLite default,
    but we register it explicitly via ATTACH so the schema-qualified table
    path resolves identically to Postgres in production).

    JSONB doesn't exist in SQLite either — SQLAlchemy falls back to TEXT
    storage with JSON serialization, which is fine for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS public"))
        conn.commit()

    # Build the table directly — mirrors the production columns 1:1 (see
    # `products/core/backend/migrations/031_tool_call_audits.sql`).
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE public.tool_call_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id VARCHAR(64),
                gpt_call_id VARCHAR(64),
                tool_call_id VARCHAR(64),
                conversation_id VARCHAR(64),
                user_id BIGINT,
                tool_name VARCHAR(80) NOT NULL,
                status VARCHAR(16) NOT NULL,
                arguments TEXT,
                result TEXT,
                error TEXT,
                duration_ms INTEGER,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

    Session = sessionmaker(bind=engine)
    yield Session
    engine.dispose()


def test_make_audit_writer_persists_record_with_seed_factory(session_factory) -> None:
    """The seed writer + core's `ToolCallAudit` ORM successfully round-trip
    an `AuditRecord` to the table — one row per dispatch."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        record = AuditRecord(
            tool_name="core.audit_digest",
            status="success",
            duration_ms=128,
            started_at=now_utc(),
            arguments={
                "period_days": 7,
                "total_events": 42,
                "model": "gpt-4o-mini",
                "actions_by_count_top3": [("user.login", 30), ("settings.changed", 8)],
            },
            result={"narrative_chars": 612},
            correlation_id="corr_core_001",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "core.audit_digest"
        assert row.status == "success"
        assert row.duration_ms == 128
        assert row.correlation_id == "corr_core_001"
    finally:
        session.close()


def test_audit_writer_handles_unknown_tool_status(session_factory) -> None:
    """`status='unknown_tool'` is a valid seed AuditStatus literal — must persist."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        writer(
            AuditRecord(
                tool_name="bogus_name",
                status="unknown_tool",
                duration_ms=1,
                started_at=now_utc(),
                arguments=None,
                result=None,
            )
        )
        row = session.query(ToolCallAudit).one()
        assert row.status == "unknown_tool"
        assert row.tool_name == "bogus_name"
    finally:
        session.close()


def test_audit_writer_failure_does_not_raise(session_factory, caplog) -> None:
    """Best-effort guarantee: a DB exception NEVER reaches the caller.
    The writer logs WARNING and swallows so the digest pipeline keeps going."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)

        # Force a failure: `tool_name` column is NOT NULL — passing None
        # triggers a constraint violation. The seed writer must log + swallow.
        bad_record = AuditRecord(
            tool_name="x",
            status="success",
            duration_ms=1,
            started_at=datetime.now(timezone.utc),
        )
        bad_record.tool_name = None  # type: ignore[assignment]

        with caplog.at_level(logging.WARNING):
            writer(bad_record)  # MUST NOT raise

        # The audit table stays empty — failure was swallowed.
        assert session.query(ToolCallAudit).count() == 0
        assert any(
            "tool_call_audit write failed" in r.getMessage() for r in caplog.records
        )
    finally:
        session.close()


def test_get_audit_writer_returns_noop_when_postgres_url_unset(monkeypatch, caplog):
    """`audit_hook.get_audit_writer()` returns a noop when no Postgres URL —
    the digest still functions; debug-log surfaces the audit-trail gap."""
    from app.config import settings
    from app.services import audit_hook

    monkeypatch.setattr(settings, "postgres_url", "", raising=False)

    # Reset the lazy module cache so the noop branch fires.
    monkeypatch.setattr(audit_hook, "_engine", None, raising=False)
    monkeypatch.setattr(audit_hook, "_session_factory", None, raising=False)

    writer = audit_hook.get_audit_writer()

    with caplog.at_level(logging.DEBUG, logger="app.services.audit_hook"):
        writer(
            AuditRecord(
                tool_name="core.audit_digest",
                status="success",
                duration_ms=0,
                started_at=now_utc(),
            )
        )

    # Must be the noop branch — no exception, no DB call.
    assert any(
        "audit_hook: postgres_url unset" in r.getMessage() for r in caplog.records
    )

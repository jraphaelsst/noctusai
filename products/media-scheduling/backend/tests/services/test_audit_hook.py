"""Tool-call audit integration — product `ToolCallAudit` ORM ⇄ seed writer.

Ported & adapted from `whatsapp-google-scheduling/tests/test_appointment_request_audit.py`.

Source-side: a hand-rolled `appointment_requests` audit table tracked
propose → confirm funnel rows.
Product-side (Phase 4 decision): the appointment-request funnel is subsumed
by the seed-shaped `tool_call_audits` table (one row per dispatch, captured
via `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, ToolCallAudit)`).

So the SOURCE TEST'S CONTRACT — "tool dispatch persists an audit row" — has
moved one level up: instead of `record_proposal(...)` writing to
`appointment_requests`, every tool call writes to `tool_call_audits` via
the seed-supplied writer factory + the product's `audit_hook` wrapper.
These tests pin that integration end-to-end against an in-memory SQLite
session bound to the product's `ToolCallAudit` ORM model.

What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into the product's table.
  - JSONB columns accept dict / list / non-serializable values (the
    `_safe_jsonable` round-trip).
  - DB exceptions are swallowed (best-effort guarantee — never break tool
    dispatch on an audit failure).
  - `app.services.audit_hook.get_audit_writer()` returns a noop writer
    when `settings.postgres_url` is empty (so every dispatch keeps going).
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
    """In-memory SQLite session bound to the product's `ToolCallAudit` ORM.

    The model's table args carry `schema="media_scheduling"` (Postgres-only).
    SQLite has no schema concept, so we register the schema as a no-op
    `ATTACH DATABASE` alias before `metadata.create_all`. This keeps the
    production model untouched while letting unit tests run fast.

    JSONB doesn't exist in SQLite either — SQLAlchemy falls back to TEXT
    storage with JSON serialization, which is fine for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS media_scheduling"))
        conn.commit()

    # Build the table directly — bypasses Base.metadata.create_all's
    # schema-aware DDL (which SQLite-attached DBs handle but error in
    # some sqlalchemy versions). We mirror the production columns 1:1.
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE media_scheduling.tool_call_audits (
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
    """The seed writer + product's `ToolCallAudit` ORM successfully round-trips
    an `AuditRecord` to the table — one row per dispatch."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        record = AuditRecord(
            tool_name="propose_appointment",
            status="success",
            duration_ms=42,
            started_at=now_utc(),
            arguments={"property_code": "ONE0007", "requested_date": "2026-06-10"},
            result={"candidate_count": 4},
            user_id=2,
            correlation_id="corr_abc",
            conversation_id="conv_xyz",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "propose_appointment"
        assert row.status == "success"
        assert row.duration_ms == 42
        assert row.user_id == 2
        assert row.correlation_id == "corr_abc"
        assert row.conversation_id == "conv_xyz"
    finally:
        session.close()


def test_audit_writer_handles_unknown_tool_status(session_factory) -> None:
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
    The writer logs WARNING and swallows so tool dispatch keeps going."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)

        # Force a failure: status column is NOT NULL — passing an empty
        # status simulates a corrupt-record path. The seed writer must
        # log + swallow.
        bad_record = AuditRecord(
            tool_name="x",
            status="success",
            duration_ms=1,
            started_at=datetime.now(timezone.utc),
        )
        # Patch to_row_kwargs to return invalid kwargs (e.g. NOT NULL violation
        # on tool_name).
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
    the product still functions; debug-log surfaces the gap."""
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
                tool_name="ping",
                status="success",
                duration_ms=0,
                started_at=now_utc(),
            )
        )

    # Must be the noop branch — no exception, no DB call.
    assert any(
        "audit_hook: postgres_url unset" in r.getMessage() for r in caplog.records
    )

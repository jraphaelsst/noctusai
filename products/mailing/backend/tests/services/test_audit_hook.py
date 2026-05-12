"""Tool-call audit integration — mailing `ToolCallAudit` ORM ⇄ seed writer.

Mirrors `products/media-scheduling/backend/tests/services/test_audit_hook.py`
(the llm-tool-audit-rollout Phase 1 reference adopter).

What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into `mailing.tool_call_audits`.
  - `app.services.audit_hook.get_audit_writer()` returns a noop writer
    when `settings.postgres_url` is empty (so every dispatch keeps going).
"""

from __future__ import annotations

import logging

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

    The model's table args carry `schema="mailing"` (Postgres-only). SQLite
    has no schema concept, so we register the schema as a no-op
    `ATTACH DATABASE` alias before `metadata.create_all`. This keeps the
    production model untouched while letting unit tests run fast.

    JSONB doesn't exist in SQLite either — SQLAlchemy falls back to TEXT
    storage with JSON serialization, which is fine for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS mailing"))
        conn.commit()

    # Build the table directly — bypasses Base.metadata.create_all's
    # schema-aware DDL. We mirror the production columns 1:1.
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE mailing.tool_call_audits (
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
    """The seed writer + mailing's `ToolCallAudit` ORM successfully round-trip
    an `AuditRecord` to the table — one row per dispatch."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        record = AuditRecord(
            tool_name="generate_subjects",
            status="success",
            duration_ms=42,
            started_at=now_utc(),
            arguments={"campaign_summary": "Black Friday — 50% off premium plans"},
            result={"variant_count": 4},
            conversation_id="org_abc",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "generate_subjects"
        assert row.status == "success"
        assert row.duration_ms == 42
        assert row.conversation_id == "org_abc"
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

    assert any(
        "audit_hook: postgres_url unset" in r.getMessage() for r in caplog.records
    )

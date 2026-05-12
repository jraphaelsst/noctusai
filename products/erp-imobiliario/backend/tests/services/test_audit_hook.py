"""Tool-call audit integration — product `ToolCallAudit` ORM ⇄ seed writer.

Mirror of `products/media-scheduling/backend/tests/services/test_audit_hook.py`
(the reference adopter). What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into the product's table.
  - DB exceptions are swallowed (best-effort guarantee — never break LLM
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

    The model's table args carry `schema="erp"` (Postgres-only). SQLite has
    no schema concept, so we register the schema as an `ATTACH DATABASE`
    alias before creating the table. JSONB doesn't exist in SQLite either —
    we declare the column as TEXT for the test fixture.
    """
    from app.models import ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS erp"))
        conn.commit()

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE erp.tool_call_audits (
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
            tool_name="erp.lead_score",
            status="success",
            duration_ms=125,
            started_at=now_utc(),
            arguments={"nome": "Fulano", "etapa": "qualificação"},
            result={"content": "SCORE: 78\nJUSTIFICATIVA: ..."},
            user_id=42,
            correlation_id="corr_erp_001",
            conversation_id="conv_erp_lead_42",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "erp.lead_score"
        assert row.status == "success"
        assert row.duration_ms == 125
        assert row.user_id == 42
        assert row.correlation_id == "corr_erp_001"
        assert row.conversation_id == "conv_erp_lead_42"
    finally:
        session.close()


def test_audit_writer_handles_failure_status(session_factory) -> None:
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        writer(
            AuditRecord(
                tool_name="erp.imovel_description",
                status="failure",
                duration_ms=8,
                started_at=now_utc(),
                arguments={"tipo": "apartamento"},
                result=None,
                error="LLMBudgetExceeded: org quota at 110%",
            )
        )
        row = session.query(ToolCallAudit).one()
        assert row.status == "failure"
        assert row.tool_name == "erp.imovel_description"
        assert "LLMBudgetExceeded" in (row.error or "")
    finally:
        session.close()


def test_audit_writer_failure_does_not_raise(session_factory, caplog) -> None:
    """Best-effort guarantee: a DB exception NEVER reaches the caller.
    The writer logs WARNING and swallows so tool dispatch keeps going."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)

        bad_record = AuditRecord(
            tool_name="x",
            status="success",
            duration_ms=1,
            started_at=datetime.now(timezone.utc),
        )
        # Force NOT-NULL violation on tool_name.
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
                tool_name="erp.search_relevance",
                status="success",
                duration_ms=0,
                started_at=now_utc(),
            )
        )

    # Must be the noop branch — no exception, no DB call.
    assert any(
        "audit_hook: postgres_url unset" in r.getMessage() for r in caplog.records
    )

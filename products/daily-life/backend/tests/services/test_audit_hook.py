"""Tool-call audit integration — Daily Life `ToolCallAudit` ORM ⇄ seed writer.

Mirrors the original canonical reference adopter (retired `media-scheduling`,
consolidated into `social-wiring` 2026-05-16).

What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into the product's table.
  - DB exceptions are swallowed (best-effort guarantee — never break tool
    dispatch on an audit failure).
  - `app.services.audit_hook.get_audit_writer()` returns a noop writer
    when `settings.postgres_url` is empty (so every dispatch keeps going).
  - `app.services.audit_hook.build_audit_record(...)` applies the
    registered redaction lambdas BEFORE the AuditRecord is built.
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

    The model's table args carry `schema="daily_life"` (Postgres-only).
    SQLite has no schema concept, so we register the schema as a no-op
    `ATTACH DATABASE` alias before issuing DDL. JSONB doesn't exist in
    SQLite either — fall back to TEXT/JSON for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS daily_life"))
        conn.commit()

    # Build the table directly to mirror the production columns 1:1 while
    # avoiding `Base.metadata.create_all`'s schema-aware DDL edge cases on
    # SQLite-attached DBs.
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE daily_life.tool_call_audits (
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
    an `AuditRecord` to the daily-life table — one row per dispatch."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        record = AuditRecord(
            tool_name="daily_life.daily_brief.generate_summary",
            status="success",
            duration_ms=42,
            started_at=now_utc(),
            arguments={
                "tasks_today": 3,
                "events_today": 1,
                "habits_pending": 2,
                "prompt_version": "daily-life-daily-brief@v1",
            },
            result={"summary": "[REDACTED]"},
            user_id=7,
            correlation_id="corr_dl",
            conversation_id=None,
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "daily_life.daily_brief.generate_summary"
        assert row.status == "success"
        assert row.duration_ms == 42
        assert row.user_id == 7
        assert row.correlation_id == "corr_dl"
    finally:
        session.close()


def test_audit_writer_failure_does_not_raise(session_factory, caplog) -> None:
    """Best-effort guarantee: a DB exception NEVER reaches the caller.
    The writer logs WARNING and swallows so tool dispatch keeps going."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)

        # Force a NOT NULL violation on `tool_name`.
        bad_record = AuditRecord(
            tool_name="x",
            status="success",
            duration_ms=1,
            started_at=datetime.now(timezone.utc),
        )
        bad_record.tool_name = None  # type: ignore[assignment]

        with caplog.at_level(logging.WARNING):
            writer(bad_record)  # MUST NOT raise

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

    assert any(
        "audit_hook: postgres_url unset" in r.getMessage() for r in caplog.records
    )


def test_build_audit_record_applies_registered_redaction():
    """`build_audit_record` looks up the feature in the catalog and applies
    the registered `redact_arguments` / `redact_result` lambdas BEFORE
    constructing the `AuditRecord`."""
    from app.services import audit_hook

    # `app.services.ai_consent_features` registers the 3 features at import.
    # We import it explicitly here to populate the catalog for this test.
    import app.services.ai_consent_features  # noqa: F401

    record = audit_hook.build_audit_record(
        feature_key="daily_life.note_extract",
        tool_name="daily_life.extract_tasks_from_note",
        status="success",
        duration_ms=12,
        arguments={
            "note_content": "Comprei leite. Preciso ligar para João sobre o relatório.",
            "org_id": "org_test",
            "prompt_version": "daily-life-extract-tasks@v1",
        },
        result=[
            {"title": "Ligar para João sobre o relatório", "due_hint": None},
        ],
    )

    # Personal content gone, structural fields kept.
    assert record.arguments is not None
    assert record.arguments["note_content"] == "[REDACTED]"
    assert record.arguments["org_id"] == "org_test"
    assert record.arguments["prompt_version"] == "daily-life-extract-tasks@v1"
    assert isinstance(record.result, list)
    assert record.result[0]["title"] == "[REDACTED]"


def test_build_audit_record_falls_back_to_raw_when_feature_missing(caplog):
    """Unknown feature_key → audit row uses raw arguments/result (no
    redaction available). Debug-log surfaces the gap."""
    from app.services import audit_hook

    with caplog.at_level(logging.DEBUG, logger="app.services.audit_hook"):
        record = audit_hook.build_audit_record(
            feature_key="daily_life.nonexistent_feature",
            tool_name="x",
            status="success",
            duration_ms=1,
            arguments={"sensitive": "raw"},
            result={"echo": "raw"},
        )

    assert record.arguments == {"sensitive": "raw"}
    assert record.result == {"echo": "raw"}
    assert any(
        "not in catalog" in r.getMessage() for r in caplog.records
    )


def test_build_audit_record_redaction_failure_falls_back_to_raw(caplog):
    """Per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`: a redaction
    lambda crash NEVER raises — log + use raw value rather than drop the
    audit row entirely."""
    from noctusai_lib.domain.ai import register_feature, reset_catalog_for_test
    from app.services import audit_hook

    reset_catalog_for_test()
    try:
        def _broken_redactor(_):
            raise RuntimeError("synthetic redaction failure")

        register_feature(
            "daily_life.broken_test_feature",
            title="Broken",
            rationale="Test fixture.",
            product="daily-life",
            redact_arguments=_broken_redactor,
            redact_result=_broken_redactor,
        )

        with caplog.at_level(logging.ERROR, logger="app.services.audit_hook"):
            record = audit_hook.build_audit_record(
                feature_key="daily_life.broken_test_feature",
                tool_name="x",
                status="success",
                duration_ms=1,
                arguments={"raw": "in"},
                result={"raw": "out"},
            )

        assert record.arguments == {"raw": "in"}
        assert record.result == {"raw": "out"}
        assert any(
            "redact_arguments failed" in r.getMessage() for r in caplog.records
        )
    finally:
        reset_catalog_for_test()
        # Re-register the real features (subsequent tests rely on them).
        import importlib
        import app.services.ai_consent_features as _features
        importlib.reload(_features)

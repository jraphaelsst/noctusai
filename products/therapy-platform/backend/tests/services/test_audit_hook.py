"""Therapy tool-call audit integration tests.

Pinning two contracts:

1. **Writer fires.** `make_audit_writer(session, ToolCallAudit)` produces a
   writer that persists an `AuditRecord` to `therapy.tool_call_audits` via
   the seed primitive — best-effort guarantee preserved (DB failure swallowed).

2. **Noop branch.** `app.services.audit_hook.get_audit_writer()` returns a
   noop writer when `settings.postgres_url` is empty — every dispatch keeps
   going, debug-log surfaces the gap.

Mirrors `products/media-scheduling/backend/tests/services/test_audit_hook.py`
shape (canonical reference adopter per `projects/llm-tool-audit-rollout/PROJECT.md`).
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
    """In-memory SQLite session bound to therapy's `ToolCallAudit` ORM.

    The model's table args carry `schema="therapy"` (Postgres-only).
    SQLite has no schema concept, so we register the schema as a no-op
    `ATTACH DATABASE` alias before issuing the CREATE TABLE. JSONB falls
    back to TEXT storage with JSON serialization, fine for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401 — registers the table

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS therapy"))
        conn.commit()

    # Mirror the production columns 1:1, bypassing Base.metadata.create_all's
    # schema-aware DDL (which some sqlalchemy versions error on for attached DBs).
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE therapy.tool_call_audits (
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
    """The seed writer + therapy's `ToolCallAudit` ORM round-trips an
    `AuditRecord` to the table — one row per dispatch.

    Note: `arguments` here uses ALREADY-REDACTED content (length-only metadata),
    matching the production wiring where the dispatch site calls
    `audit_hook.audit_dispatch` which scrubs before constructing the record.
    """
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        record = AuditRecord(
            tool_name="chat_completion",
            status="success",
            duration_ms=42,
            started_at=now_utc(),
            # Pre-redacted: NOT raw clinical text. Length flags only.
            arguments={
                "messages": [
                    {"role": "system", "content": {"present": True, "redacted_length": 180}},
                    {"role": "user", "content": {"present": True, "redacted_length": 3204}},
                ],
                "model": "gpt-4o",
                "org_id_present": True,
            },
            result={
                "present": True,
                "summary": {"present": True, "redacted_length": 480},
                "key_points_count": 6,
                "tags_count": 4,
            },
            user_id=42,
            correlation_id="corr_therapy_001",
            conversation_id="session_xyz",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "chat_completion"
        assert row.status == "success"
        assert row.duration_ms == 42
        assert row.user_id == 42
        assert row.correlation_id == "corr_therapy_001"
        assert row.conversation_id == "session_xyz"
    finally:
        session.close()


def test_audit_writer_handles_failure_status(session_factory) -> None:
    """The writer records `status='failure'` rows with an `error` string —
    needed for end-to-end LGPD audit (we want to see which LLM dispatches
    failed for which patient session)."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        writer(
            AuditRecord(
                tool_name="transcribe_audio",
                status="failure",
                duration_ms=11,
                started_at=now_utc(),
                arguments={"audio_bytes": {"present": True, "byte_length": 0}},
                result=None,
                error="LLMNotConfigured: openai_api_key empty",
            )
        )
        row = session.query(ToolCallAudit).one()
        assert row.status == "failure"
        assert row.tool_name == "transcribe_audio"
        assert row.error is not None
        assert "LLMNotConfigured" in row.error
    finally:
        session.close()


def test_audit_writer_failure_does_not_raise(session_factory, caplog) -> None:
    """Best-effort guarantee: a DB exception NEVER reaches the caller.
    The writer logs WARNING and swallows so LLM dispatch keeps going.

    This is the LGPD-vs-availability tradeoff: we'd rather lose a row to
    a transient hiccup than fail the user-facing dispatch — the seed
    `make_audit_writer` ensures that contract.
    """
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
    therapy still functions; debug-log surfaces the gap. Mirrors
    media-scheduling's identical contract."""
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


def test_audit_dispatch_redacts_before_writing(session_factory, monkeypatch):
    """End-to-end: `audit_dispatch` redacts via the feature's lambdas BEFORE
    constructing the AuditRecord — confirming the LGPD redaction wiring
    fires inside the dispatch helper, not just at the redactor unit level.

    This is the pin that catches a regression where a future engineer
    sidesteps the redactor and passes raw clinical text into AuditRecord.
    """
    from app.models import ToolCallAudit
    from app.services import audit_hook

    Session = session_factory

    # Stub get_audit_writer to write to our in-memory session factory.
    def _stub_writer():
        def write(record):
            sess = Session()
            try:
                inner = make_audit_writer(sess, ToolCallAudit)
                inner(record)
            finally:
                sess.close()
        return write

    monkeypatch.setattr(audit_hook, "get_audit_writer", _stub_writer)

    # Raw, sensitive clinical text — would be an Art. 11 leak if it landed
    # in the audit row unredacted.
    raw_transcript = (
        "Paciente relatou sintomas de ansiedade. Discutimos estratégias "
        "cognitivo-comportamentais. Episódios de pânico nas últimas 2 semanas."
    )
    audit_hook.audit_dispatch(
        feature_key="therapy.session_summary",
        tool_name="chat_completion",
        status="success",
        duration_ms=120,
        arguments={
            "messages": [
                {"role": "system", "content": "Você é um assistente clínico..."},
                {"role": "user", "content": raw_transcript},
            ],
            "model": "gpt-4o",
        },
        result='{"summary": "Sessão focada em ansiedade e estratégias TCC", "key_points": ["ansiedade", "TCC"], "tags": ["clínico"]}',
    )

    # Verify a row landed AND verify the raw transcript is NOT in it.
    sess = Session()
    try:
        rows = sess.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "chat_completion"
        assert row.status == "success"

        # The arguments column is JSON-serialized (SQLite TEXT). Read raw.
        # In Postgres production this is JSONB; SQLAlchemy returns dict.
        # Either way, do a string-level "raw transcript MUST NOT appear" check.
        args_str = str(row.arguments)
        result_str = str(row.result)
        assert raw_transcript not in args_str, (
            f"LGPD leak: raw transcript present in audit_row.arguments: {args_str!r}"
        )
        assert "ansiedade" not in args_str, (
            f"LGPD leak: clinical content present in audit_row.arguments: {args_str!r}"
        )
        # Result was also redacted (raw_json_string variant).
        assert "estratégias TCC" not in result_str, (
            f"LGPD leak: response content present in audit_row.result: {result_str!r}"
        )
    finally:
        sess.close()

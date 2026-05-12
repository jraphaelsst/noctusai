"""Tool-call audit integration — product `ToolCallAudit` ORM ⇄ seed writer.

Mirrors `products/media-scheduling/backend/tests/services/test_audit_hook.py`
(reference adopter, per llm-tool-audit-rollout PROJECT.md §6 Phase 1).

What we verify here:
  - `make_audit_writer(session, ToolCallAudit)` produces a writer that
    persists `AuditRecord` fields into the product's table.
  - The writer accepts dict / list / non-serializable values (the seed
    `_safe_jsonable` round-trip) without raising.
  - DB exceptions are swallowed (best-effort guarantee — never break tool
    dispatch on an audit failure).
  - `app.services.audit_hook.get_audit_writer()` returns a noop writer
    when `settings.postgres_url` is empty (so every dispatch keeps going).
  - `build_audit_record` applies feature redactors when looked up via
    the seed consent catalog.
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

    The model's table args carry `schema="personal-finance"` (Postgres-only).
    SQLite has no schema concept, but it does NOT accept hyphens in attached
    DB names. We mirror media-scheduling's pattern with an `ATTACH` whose
    alias is quoted to handle the dash.

    JSONB doesn't exist in SQLite — SQLAlchemy falls back to TEXT storage
    with JSON serialization, which is fine for round-trip tests.
    """
    from app.models import Base, ToolCallAudit  # noqa: F401  (registers the table)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text('ATTACH DATABASE \':memory:\' AS "personal-finance"'))
        conn.commit()

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE "personal-finance".tool_call_audits (
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
            tool_name="pf.transaction_categorize",
            status="success",
            duration_ms=42,
            started_at=now_utc(),
            arguments={"tipo": "despesa", "has_descricao": True},
            result={"kind": "classification", "label": "Mercado", "confidence": 0.9},
            user_id=7,
            correlation_id="corr_pf_1",
        )

        writer(record)

        rows = session.query(ToolCallAudit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool_name == "pf.transaction_categorize"
        assert row.status == "success"
        assert row.duration_ms == 42
        assert row.user_id == 7
        assert row.correlation_id == "corr_pf_1"
    finally:
        session.close()


def test_audit_writer_handles_failure_status(session_factory) -> None:
    """Failure-status rows persist with the error message string."""
    from app.models import ToolCallAudit

    session = session_factory()
    try:
        writer = make_audit_writer(session, ToolCallAudit)
        writer(
            AuditRecord(
                tool_name="pf.monthly_narrative",
                status="failure",
                duration_ms=120,
                started_at=now_utc(),
                arguments={"period_days": 30},
                result=None,
                error="LLM_TIMEOUT",
            )
        )
        row = session.query(ToolCallAudit).one()
        assert row.status == "failure"
        assert row.tool_name == "pf.monthly_narrative"
        assert row.error == "LLM_TIMEOUT"
    finally:
        session.close()


def test_audit_writer_failure_does_not_raise(session_factory, caplog) -> None:
    """Best-effort guarantee: a DB exception NEVER reaches the caller.
    The writer logs WARNING and swallows so AI dispatch keeps going."""
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
        # Force a NOT NULL violation on tool_name.
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
    the product still functions; debug-log surfaces the gap.

    PFSettings does NOT declare `postgres_url` today (the seed `ProductSettings`
    omits it for Supabase-client-first products); the audit_hook reads via
    `getattr(settings, "postgres_url", "")` so the noop branch fires
    automatically. We assert that boot-time behavior here without touching
    the strict pydantic model.
    """
    from app.services import audit_hook

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


def test_build_audit_record_applies_feature_redactors(monkeypatch):
    """`build_audit_record` looks up the feature in the seed catalog and
    applies its `redact_arguments` / `redact_result` callables to scrub
    sensitive fields before constructing the `AuditRecord`. This is the
    LGPD guarantee — raw transaction descriptions never reach the audit
    table."""
    # Importing the feature module registers the 3 PF features (including
    # the redactors) in the seed catalog at import time.
    import app.services.ai_consent_features  # noqa: F401
    from app.services.audit_hook import build_audit_record

    raw_args = {
        "tipo": "despesa",
        "descricao": "Pagamento aluguel rua das flores",
        "comerciante": "IMOBILIARIA XYZ",
        "valor": 2500.00,
        "available_categories": [{"nome": "Moradia"}, {"nome": "Lazer"}],
        "org_id": "org_abc",
    }
    raw_result = {
        "kind": "classification",
        "label": "Moradia",
        "chip": "MORADIA",
        "explanation": "Padrão recorrente mensal de aluguel residencial",
        "confidence": 0.95,
        "model_version": "gpt-4o-mini",
        "prompt_version": "pf-categorize@v1",
        "matched_categoria_id": "cat_1",
    }

    record = build_audit_record(
        feature_key="pf.transaction_categorize",
        tool_name="pf.transaction_categorize",
        status="success",
        duration_ms=100,
        arguments=raw_args,
        result=raw_result,
    )

    # Arguments: sensitive free-form text + raw amount stripped; structural
    # metadata kept.
    assert record.arguments is not None
    assert "descricao" not in record.arguments
    assert "comerciante" not in record.arguments
    assert "valor" not in record.arguments
    assert record.arguments.get("tipo") == "despesa"
    assert record.arguments.get("has_descricao") is True
    assert record.arguments.get("has_comerciante") is True
    assert record.arguments.get("available_category_count") == 2

    # Result: explanation free-text stripped; classification metadata kept.
    assert record.result is not None
    assert "explanation" not in record.result
    assert record.result.get("label") == "Moradia"
    assert record.result.get("confidence") == 0.95
    assert record.result.get("matched_categoria_id") == "cat_1"


def test_build_audit_record_over_redacts_when_no_redactor_registered(monkeypatch):
    """Defensive default: a feature without `redact_arguments` /
    `redact_result` in the catalog → fields drop to `None`. Over-redaction
    rather than leak."""
    import app.services.ai_consent_features  # noqa: F401  (load catalog)
    from noctusai_lib.domain.ai import register_feature
    from app.services.audit_hook import build_audit_record

    register_feature(
        "pf.test_no_redactor",
        title="Test feature without redactors",
        rationale="(test only)",
        product="personal-finance",
        default_granted=True,
    )

    record = build_audit_record(
        feature_key="pf.test_no_redactor",
        tool_name="pf.test_no_redactor",
        status="success",
        duration_ms=1,
        arguments={"sensitive": "data"},
        result={"sensitive": "result"},
    )
    assert record.arguments is None
    assert record.result is None

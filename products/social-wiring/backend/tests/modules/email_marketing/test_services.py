"""Service-internal unit tests for the ``email_marketing`` module.

Pure-logic paths (no HTTP, no LLM): template var-extraction/render,
segmentation cosine + greedy clustering, the campaign-debrief aggregate,
and the audit-hook noop degradation when no Postgres URL is configured.
"""
from __future__ import annotations

import pytest

from app.modules.email_marketing.services.template_service import (
    TemplateService,
)
from app.modules.email_marketing.services import segmentation_service as seg
from app.modules.email_marketing.services import campaign_debrief_service as cd


class TestTemplateRendering:
    def test_extract_variables(self):
        html = "<p>Olá {{nome}}, da {{empresa}}. {{nome}} de novo.</p>"
        got = sorted(TemplateService.extract_variables(html))
        assert got == ["empresa", "nome"]

    def test_render_substitutes_and_keeps_unknown(self):
        out = TemplateService.render(
            "Oi {{nome}} / {{faltando}}", {"nome": "Ana"}
        )
        assert "Ana" in out
        assert "{{faltando}}" in out


class TestSegmentationPureLogic:
    def test_cosine_identity_and_orthogonal(self):
        assert seg._cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
        assert seg._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
        assert seg._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_greedy_cluster_groups_similar(self):
        embs = [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
            [0.01, 0.99],
        ]
        assignments = seg._greedy_cluster(
            embs, threshold=0.9, max_segments=8
        )
        assert assignments[0] == assignments[1]
        assert assignments[2] == assignments[3]
        assert assignments[0] != assignments[2]

    def test_greedy_cluster_respects_max_segments(self):
        embs = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
        assignments = seg._greedy_cluster(
            embs, threshold=0.99, max_segments=1
        )
        assert set(assignments) == {0}

    def test_build_contact_text_falls_back_to_email(self):
        txt = seg._build_contact_text({"email": "x@y.com"})
        assert "x@y.com" in txt


class TestCampaignDebriefAggregate:
    def test_aggregate_computes_rates(self):
        campaign = {"id": "c1", "nome": "Promo", "total_recipients": 10}
        send_logs = (
            [{"status": "delivered"}] * 4
            + [{"status": "opened"}] * 3
            + [{"status": "clicked"}] * 2
            + [{"status": "bounced"}] * 1
        )
        link_clicks = [
            {"send_log_id": "s1", "url": "https://a"},
            {"send_log_id": "s2", "url": "https://a"},
            {"send_log_id": "s3", "url": "https://b"},
        ]
        metrics, top_links = cd._aggregate(campaign, send_logs, link_clicks)
        assert metrics["total_recipients"] == 10
        assert metrics["clicked"] == 2
        assert metrics["opened"] == 5  # opened + clicked
        assert top_links[0] == ("https://a", 2)

    def test_pct_zero_denominator_safe(self):
        assert cd._pct(5, 0) == 0.0
        assert cd._pct(1, 2) == 50.0


class TestCampaignDebriefAuditWiring:
    """llm-tool-audit-rollout — closes the originating M-4 gap: the
    `campaign_debrief` LLM site now writes one redacted row to
    `mailing.tool_call_audits`. We exercise the real `_record_audit`
    helper + the seed `make_audit_writer` over in-memory SQLite (no
    monkeypatching of our own code), and assert the `mailing.campaign_debrief`
    feature redactors scrub correctly (campaign_id kept, body dropped).
    """

    @staticmethod
    def _sqlite_session_factory():
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from app.modules.email_marketing.models import SCHEMA

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text(f"ATTACH DATABASE ':memory:' AS {SCHEMA}"))
            conn.commit()
            conn.execute(text(f"""
                CREATE TABLE {SCHEMA}.tool_call_audits (
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
        return sessionmaker(bind=engine), engine

    def test_campaign_debrief_feature_redactors_scrub(self):
        # The registered feature must drop the narrative body + keep only
        # campaign_id from arguments (LGPD — no recipient/content leakage).
        import app.modules.email_marketing.services.ai_consent_features  # noqa: F401 — registers
        from noctusai_lib.domain.ai import get_feature

        feature = get_feature("mailing.campaign_debrief")
        assert feature is not None
        red_args = feature.redact_arguments(
            {"campaign_id": "c-123", "org_id": "org-9"}
        )
        assert red_args == {"campaign_id": "c-123"}
        red_result = feature.redact_result(
            "Parágrafo 1 com joao@exemplo.com e +55 11 99999-9999. Parágrafo 2."
        )
        assert red_result == {"_redacted": "body"}

    def test_record_audit_persists_redacted_row_via_seed_writer(self):
        # Exercise the real _record_audit helper with the seed
        # make_audit_writer bound to the product ORM over SQLite. Proves:
        # (a) a row lands, (b) redaction applied (campaign_id kept, body
        # dropped), (c) status/error round-trip.
        import json

        from sqlalchemy import text as sa_text

        from app.modules.email_marketing.models.tool_call_audit import (
            ToolCallAudit,
        )
        from app.modules.email_marketing.services import (
            campaign_debrief_service as cds,
        )
        from noctusai_lib.domain.ai.tool_audit import make_audit_writer

        Session, engine = self._sqlite_session_factory()
        captured: list = []

        def capturing_writer(record):
            session = Session()
            try:
                make_audit_writer(session, ToolCallAudit)(record)
            finally:
                session.close()
            captured.append(record)

        # Inject the real seed-backed writer in place of the lazy noop hook
        # (audit_hook.get_audit_writer is the seam; substituting the SEAM,
        # not patching our redaction/record-build logic, which is what runs).
        # get_audit_writer is the module-level audit-writer factory (the
        # lazy noop hook is the production default); test substitutes the
        # SEAM not the logic.
        import unittest.mock as _m

        with _m.patch.object(cds, "get_audit_writer", lambda: capturing_writer):  # self-patch-ok: di-seam-substitute
            cds._record_audit(
                "mailing.campaign_debrief",
                "campaign_debrief",
                arguments={"campaign_id": "c-77", "org_id": "org-1"},
                result="Narrativa longa com joao@x.com — sigiloso.",
                status="success",
                duration_ms=42,
                org_id="org-1",
            )

        assert len(captured) == 1
        from app.modules.email_marketing.models import SCHEMA

        with engine.connect() as conn:
            rows = conn.execute(
                sa_text(
                    "SELECT tool_name, status, arguments, result, duration_ms "
                    f"FROM {SCHEMA}.tool_call_audits"
                )
            ).fetchall()
        assert len(rows) == 1
        tool_name, status, args_json, result_json, dur = rows[0]
        assert tool_name == "campaign_debrief"
        assert status == "success"
        assert dur == 42
        # Redaction applied: only campaign_id in args, body dropped in result.
        assert json.loads(args_json) == {"campaign_id": "c-77"}
        assert json.loads(result_json) == {"_redacted": "body"}

    @pytest.mark.asyncio
    async def test_generate_narrative_records_audit_on_llm_unavailable(self):
        # When the external LLM is unavailable, digest_narrative returns the
        # fallback; the site must still record a 'failure' audit row. We
        # patch ONLY the external LLM boundary (digest_narrative wraps
        # chat_completion) and capture via an injected real writer.
        import unittest.mock as _m

        from app.modules.email_marketing.services import (
            campaign_debrief_service as cds,
        )

        captured: list = []

        metrics = {
            "total_recipients": 10, "sent": 8, "sent_rate": 80.0,
            "delivered": 7, "delivered_rate": 87.5, "opened": 5,
            "open_rate": 71.4, "clicked": 2, "click_rate": 28.6,
            "bounced": 1, "bounce_rate": 12.5, "complained": 0, "failed": 0,
        }

        async def _fake_narrative(*, fallback, **_kw):
            return fallback  # external LLM "unavailable" path

        # digest_narrative wraps the external LLM boundary (chat_completion);
        # patching it at the consumer-side import binding substitutes the LLM
        # boundary per KB § PATTERNS/di-test-seam.md Pattern-2. get_audit_writer
        # is the audit-writer factory seam (Pattern-1 DI default).
        with _m.patch.object(cds, "digest_narrative", _fake_narrative), _m.patch.object(cds, "get_audit_writer", lambda: captured.append):  # self-patch-ok: di-seam-substitute
            out = await cds._generate_narrative(
                campaign_name="Promo X",
                metrics=metrics,
                top_links=[("https://a", 3)],
                org_id="org-1",
                campaign_id="c-9",
            )

        assert out  # fallback string returned
        assert len(captured) == 1
        rec = captured[0]
        assert rec.tool_name == "campaign_debrief"
        assert rec.status == "failure"
        assert rec.error is not None
        # Redaction already applied by _record_audit before the writer.
        assert rec.arguments == {"campaign_id": "c-9"}
        assert rec.result == {"_redacted": "body"}


class TestAuditHookDegradation:
    def test_no_postgres_url_returns_noop_writer(self):
        # SocialWiringSettings does not declare postgres_url; the hook must
        # degrade to a noop writer (best-effort) rather than AttributeError.
        from app.modules.email_marketing.services.audit_hook import (
            get_audit_writer,
        )
        from noctusai_lib.domain.ai.tool_audit import AuditRecord, now_utc

        writer = get_audit_writer()
        # Must be callable and must not raise on a record.
        writer(
            AuditRecord(
                tool_name="t",
                status="success",
                duration_ms=1,
                started_at=now_utc(),
                arguments={},
                result={},
            )
        )

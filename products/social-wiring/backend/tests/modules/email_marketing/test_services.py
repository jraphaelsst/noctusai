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

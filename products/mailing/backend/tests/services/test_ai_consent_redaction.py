"""LGPD redaction tests for mailing consent features (llm-tool-audit-rollout
Phase 3, 2026-05-11).

The 7 mailing `register_feature(...)` calls in `app.services.ai_consent_features`
each declare `redact_arguments=` + `redact_result=` lambdas. These tests
assert that PII in raw arguments + results is scrubbed before the
`AuditRecord` lands in `mailing.tool_call_audits`.

Coverage shape:
  - Direct call against the helper / lambda surface (no DB round-trip).
  - `apply_feature_redaction(record, ...)` end-to-end for one feature, to
    confirm wiring + the AuditRecord-rebuild semantics.
"""
from __future__ import annotations

import pytest

# Importing the module registers all 7 features in the seed catalog as a
# side-effect; we re-import per test to defend against earlier tests that
# may have called `reset_catalog_for_test()` and wiped the catalog. We
# deliberately do NOT call `reset_catalog_for_test()` ourselves — clearing
# the global catalog leaks into the rest of the mailing test suite (the
# ai_router tests rely on the catalog being populated for consent-guard).
from noctusai_lib.domain.ai import get_feature
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    apply_feature_redaction,
    now_utc,
)


@pytest.fixture(autouse=True)
def _ensure_features_registered():
    """Force re-import of `ai_consent_features` so its module-level
    `register_feature(...)` calls re-fire — idempotent per the seed's
    re-registration semantics."""
    import importlib
    import sys

    sys.modules.pop("app.services.ai_consent_features", None)
    importlib.import_module("app.services.ai_consent_features")
    yield


def _apply(feature_key: str, arguments, result):
    feature = get_feature(feature_key)
    assert feature is not None, f"feature {feature_key!r} not registered"
    record = AuditRecord(
        tool_name=feature_key,
        status="success",
        duration_ms=1,
        started_at=now_utc(),
        arguments=arguments,
        result=result,
    )
    return apply_feature_redaction(
        record,
        redact_arguments=feature.redact_arguments,
        redact_result=feature.redact_result,
    )


class TestSubjectGenRedaction:
    def test_scrubs_emails_and_phones_from_campaign_summary(self):
        redacted = _apply(
            "mailing.subject_gen",
            arguments={
                "campaign_summary": "Contate joao@example.com ou +55 11 91234-5678 hoje",
                "org_id": "org-1",
            },
            result=[{"text": "a", "tone": "direto"}, {"text": "b", "tone": "social"}],
        )
        summary = redacted.arguments["campaign_summary"]
        assert "joao@example.com" not in summary
        assert "j***@***" in summary
        assert "91234" not in summary
        assert "[phone]" in summary
        # Result drops the body — only counts survive.
        assert redacted.result == {"variant_count": 2}

    def test_truncates_long_summary(self):
        long_text = "x" * 500
        redacted = _apply(
            "mailing.subject_gen",
            arguments={"campaign_summary": long_text, "org_id": None},
            result=[],
        )
        assert len(redacted.arguments["campaign_summary"]) < 500
        assert "+300 chars]" in redacted.arguments["campaign_summary"]


class TestTemplateDraftRedaction:
    def test_drops_html_result_keeps_prompt_text(self):
        redacted = _apply(
            "mailing.template_draft",
            arguments={"prompt": "Welcome message for new sign-ups", "org_id": "o"},
            result="<h1>Welcome</h1><p>Hello!</p>",
        )
        assert redacted.arguments == {"prompt": "Welcome message for new sign-ups"}
        # Body always dropped — body is reproducible from prompt + seed.
        assert redacted.result == {"_redacted": "body"}


class TestSegmentContactsRedaction:
    def test_aggregates_contact_list_to_counts(self):
        contacts = [
            {"id": "1", "email": "a@x.com", "nome": "Alice", "empresa": "Acme"},
            {"id": "2", "email": "b@y.com", "nome": "Bob",   "empresa": "Acme"},
            {"id": "3", "email": "c@z.com", "nome": "Carol", "empresa": "Beta"},
        ]
        redacted = _apply(
            "mailing.segment_contacts",
            arguments={
                "contacts": contacts,
                "threshold": 0.78,
                "max_segments": 8,
                "org_id": "org-xyz",
            },
            result=[
                {"_contact_id": "1", "label": "Cliente Acme", "kind": "classification"},
                {"_contact_id": "2", "label": "Cliente Acme", "kind": "classification"},
                {"_contact_id": "3", "label": "Cliente Beta", "kind": "classification"},
            ],
        )
        # Arguments: counts only, NO email / nome / empresa leakage.
        args = redacted.arguments
        assert args["contact_count"] == 3
        assert args["threshold"] == 0.78
        assert args["max_segments"] == 8
        assert "org_id_hash" in args
        assert len(args["org_id_hash"]) == 12
        # The raw contacts list is gone.
        assert "contacts" not in args
        for forbidden in ("a@x.com", "Alice", "Acme"):
            assert forbidden not in str(args), f"PII leaked: {forbidden!r}"

        # Result: row count + distinct labels (deduplicated).
        assert redacted.result["row_count"] == 3
        assert redacted.result["distinct_labels"] == ["Cliente Acme", "Cliente Beta"]


class TestDeliverabilityReviewRedaction:
    def test_strips_html_body_keeps_subject_and_length(self):
        redacted = _apply(
            "mailing.deliverability_review",
            arguments={
                "html": "<p>" + ("x" * 500) + "</p>",
                "subject": "Promoção para maria@exemplo.com",
                "org_id": "o",
            },
            result={"findings": [{"code": "x", "severity": "info"}]},
        )
        assert "html" not in redacted.arguments
        assert redacted.arguments["html_length"] > 500
        assert "maria@exemplo.com" not in redacted.arguments["subject"]
        assert "m***@***" in redacted.arguments["subject"]
        assert redacted.result == {"finding_count": 1}


class TestCampaignDebriefRedaction:
    def test_keeps_only_campaign_id(self):
        redacted = _apply(
            "mailing.campaign_debrief",
            arguments={"campaign_id": "camp-123", "recipient": "owner@org.com"},
            result={"subject": "X", "html": "<p>body</p>", "summary": {"opens": 10}},
        )
        assert redacted.arguments == {"campaign_id": "camp-123"}
        assert redacted.result == {"_redacted": "body"}

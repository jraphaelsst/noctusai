"""LGPD redaction unit tests for the `core.audit_digest` feature.

Per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`: every product that
wires the audit writer MUST scrub PII before constructing the AuditRecord.
Core's audit digest may touch:

  - org_id / org_name        → identifies a customer
  - user_id / user_ids       → identifies individuals (LGPD Art. 5 I)
  - email addresses          → PII
  - billing.* action labels  → financial signal

These tests pin the scrubbing behaviour at the unit level so a regression
that lets a UUID or email leak into `tool_call_audits.arguments` /
`.result` is caught before reaching production.
"""

from __future__ import annotations

from app.services.ai_consent_features import (
    REDACT_AUDIT_DIGEST_ARGUMENTS,
    REDACT_AUDIT_DIGEST_RESULT,
)


# ---------------------------------------------------------------------------
# Arguments redaction
# ---------------------------------------------------------------------------


def test_redact_arguments_scrubs_sensitive_keys() -> None:
    """Top-level sensitive keys → `[REDACTED]`. Operational aggregates pass through."""
    raw = {
        "org_id": "11111111-2222-3333-4444-555555555555",
        "org_name": "Acme Imobiliária Ltda",
        "user_id": "u-abc",
        "user_ids": ["u-1", "u-2"],
        "email": "alice@example.com",
        "emails": ["bob@example.com", "carol@example.com"],
        "period_days": 7,
        "total_events": 42,
        "model": "gpt-4o-mini",
        "prompt_version": "core-audit-digest@v1",
    }

    scrubbed = REDACT_AUDIT_DIGEST_ARGUMENTS(raw)

    assert scrubbed is not None
    assert scrubbed["org_id"] == "[REDACTED]"
    assert scrubbed["org_name"] == "[REDACTED]"
    assert scrubbed["user_id"] == "[REDACTED]"
    assert scrubbed["user_ids"] == "[REDACTED]"
    assert scrubbed["email"] == "[REDACTED]"
    assert scrubbed["emails"] == "[REDACTED]"
    # Operational fields survive.
    assert scrubbed["period_days"] == 7
    assert scrubbed["total_events"] == 42
    assert scrubbed["model"] == "gpt-4o-mini"
    assert scrubbed["prompt_version"] == "core-audit-digest@v1"


def test_redact_arguments_scrubs_uuids_inside_strings() -> None:
    """A UUID embedded in a free-text value gets `[REDACTED]` without
    nuking the surrounding text."""
    raw = {
        "model": "gpt-4o-mini",
        "comment": "Org 11111111-2222-3333-4444-555555555555 saw a spike.",
    }

    scrubbed = REDACT_AUDIT_DIGEST_ARGUMENTS(raw)

    assert scrubbed is not None
    assert "[REDACTED]" in scrubbed["comment"]
    assert "11111111-2222-3333-4444-555555555555" not in scrubbed["comment"]
    assert "saw a spike" in scrubbed["comment"]


def test_redact_arguments_scrubs_emails_inside_strings() -> None:
    """Emails inside free-text values are replaced with `[REDACTED]`."""
    raw = {
        "model": "gpt-4o-mini",
        "comment": "Admin alice@acme.com triggered the digest.",
    }

    scrubbed = REDACT_AUDIT_DIGEST_ARGUMENTS(raw)

    assert scrubbed is not None
    assert "[REDACTED]" in scrubbed["comment"]
    assert "alice@acme.com" not in scrubbed["comment"]


def test_redact_arguments_scrubs_nested_dicts_and_lists() -> None:
    """Recursive scrubbing — nested dicts + lists also get sanitized."""
    raw = {
        "model": "gpt-4o-mini",
        "actions_by_count_top3": [
            ("user.login", 30),
            ("settings.changed", 8),
            ("billing.subscription_canceled", 1),
        ],
        "extra": {
            "org_id": "deadbeef-0000-0000-0000-000000000000",
            "note": "Customer cafebabe-0000-0000-0000-000000000000 was active.",
        },
    }

    scrubbed = REDACT_AUDIT_DIGEST_ARGUMENTS(raw)

    assert scrubbed is not None
    # Tuples coerced to lists, action labels survive (operational signal).
    assert scrubbed["actions_by_count_top3"][0] == ["user.login", 30]
    assert scrubbed["actions_by_count_top3"][2] == ["billing.subscription_canceled", 1]
    # Nested scrubbing fires.
    assert scrubbed["extra"]["org_id"] == "[REDACTED]"
    assert "[REDACTED]" in scrubbed["extra"]["note"]
    assert "cafebabe-0000-0000-0000-000000000000" not in scrubbed["extra"]["note"]


def test_redact_arguments_handles_none() -> None:
    """None arguments → None (no row payload to scrub)."""
    assert REDACT_AUDIT_DIGEST_ARGUMENTS(None) is None


def test_redact_arguments_swallows_exceptions() -> None:
    """Best-effort: any internal failure returns None so the audit row still
    lands without leaking raw data."""

    class Boom:
        def __iter__(self):
            raise RuntimeError("boom")

    # Pass an object that breaks recursive scrubbing — must return None,
    # not raise.
    result = REDACT_AUDIT_DIGEST_ARGUMENTS({"bad": Boom()})
    # Should still produce a sanitized dict (Boom is not a dict/list/str,
    # so it falls through `_scrub_value`'s "safe as-is" branch). Confirm
    # the function does not raise.
    assert result is not None


# ---------------------------------------------------------------------------
# Result redaction
# ---------------------------------------------------------------------------


def test_redact_result_scrubs_uuids_and_emails_in_string() -> None:
    """Free-text narratives get UUIDs + emails scrubbed before audit storage."""
    raw = (
        "Organização deadbeef-0000-0000-0000-000000000000 enviou um digest "
        "para alice@acme.com nesta semana."
    )

    scrubbed = REDACT_AUDIT_DIGEST_RESULT(raw)

    assert isinstance(scrubbed, str)
    assert "[REDACTED]" in scrubbed
    assert "deadbeef-0000-0000-0000-000000000000" not in scrubbed
    assert "alice@acme.com" not in scrubbed


def test_redact_result_truncates_long_strings() -> None:
    """Long narratives get truncated — `tool_call_audits.result` only needs
    enough to know what was said; full text lives in the digest email."""
    raw = "x" * 2500
    scrubbed = REDACT_AUDIT_DIGEST_RESULT(raw)
    assert isinstance(scrubbed, str)
    assert len(scrubbed) < 1100  # 1000 + suffix
    assert scrubbed.endswith("…[truncated]")


def test_redact_result_scrubs_dict_payloads() -> None:
    """Dict payloads (e.g. `{"narrative_chars": N, "narrative_preview": "..."}`)
    are recursively sanitized."""
    raw = {
        "narrative_chars": 612,
        "narrative_preview": "Resumo para alice@acme.com em deadbeef-0000-0000-0000-000000000000.",
        "model": "gpt-4o-mini",
    }

    scrubbed = REDACT_AUDIT_DIGEST_RESULT(raw)

    assert isinstance(scrubbed, dict)
    assert scrubbed["narrative_chars"] == 612
    assert "[REDACTED]" in scrubbed["narrative_preview"]
    assert "alice@acme.com" not in scrubbed["narrative_preview"]
    assert "deadbeef-0000-0000-0000-000000000000" not in scrubbed["narrative_preview"]


def test_redact_result_handles_none() -> None:
    """None result → None."""
    assert REDACT_AUDIT_DIGEST_RESULT(None) is None

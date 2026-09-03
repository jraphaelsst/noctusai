"""`_classify_failure` — naming the cause so a consumer can act on it.

The catch-all in `transcribe()` exists because a background job must not
die. But one code for every cause means the product can only ever say
"Erro inesperado", and the operator cannot tell a corrupt PDF from an
unpaid bill. Found in prod 2026-09-03: a scanned matrícula would have
surfaced as "Erro inesperado: HTTP 429" while the real cause was an
OpenAI account with no credit — a two-minute fix nobody could see.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.transcription import _classify_failure


class TestQuotaIsItsOwnCause:
    """The one an operator can fix, and would otherwise never guess."""

    @pytest.mark.parametrize("message", [
        "Error code: 429 - {'error': {'code': 'insufficient_quota'}}",
        "You have no credits remaining. Add credits to continue.",
        "credit_balance_exhausted",
        "You exceeded your current quota, please check your plan and billing details",
    ])
    def test_quota_exhaustion_is_named(self, message):
        assert _classify_failure(RuntimeError(message)) == "insufficient_quota"

    def test_quota_wins_over_the_bare_429_it_arrives_with(self):
        """Both strings are present in a real OpenAI quota error. If 429 were
        checked first this would read as 'wait a bit', which is the opposite
        of the correct action — nobody is going to wait their way into credit."""
        real = ("Error code: 429 - {'error': {'message': 'You have no credits "
                "remaining.', 'type': 'insufficient_quota'}}")
        assert _classify_failure(RuntimeError(real)) == "insufficient_quota"


class TestRateLimitStaysSeparate:
    """Same HTTP status, opposite advice: here, waiting IS the fix."""

    @pytest.mark.parametrize("message", [
        "Rate limit reached for gpt-4.1-mini",
        "rate_limit_exceeded",
        "Error code: 429 - too many requests",
    ])
    def test_rate_limit_is_named(self, message):
        assert _classify_failure(RuntimeError(message)) == "rate_limited"


class TestCredentialsAndFallback:
    @pytest.mark.parametrize("message", [
        "Error code: 401 - invalid_api_key",
        "Incorrect API key provided",
        "unauthorized",
    ])
    def test_bad_credentials_are_named(self, message):
        assert _classify_failure(RuntimeError(message)) == "invalid_credentials"

    def test_anything_else_keeps_the_generic_code(self):
        """The fallback must stay — inventing a specific cause for an unknown
        failure is worse than admitting it is unknown."""
        assert _classify_failure(ValueError("some novel parser explosion")) == "transcription_failed"

    def test_the_developer_message_is_never_swallowed(self):
        """Classification narrows the CODE; the raw text still has to reach
        the log and the fallback message, or the cause is lost anyway."""
        from noctusai_lib.integrations.documents.transcription import Transcription
        t = Transcription(error="transcription_failed", error_message="boom")
        assert not t.ok and t.error_message == "boom"

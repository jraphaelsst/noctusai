"""`noctusai_lib.integrations.outbound_webhook` — the delivery attempt.

The assertions that carry weight are about what does NOT happen: a failed
delivery must not raise, and a 4xx must not be retried. Both consumers
persist the outcome, so an exception escaping `send` is how a payload
gets lost, and spending a retry budget on a body the subscriber has
already refused is how a transient failure later gets no retries at all.
"""
from __future__ import annotations

import httpx
import pytest

from noctusai_lib.integrations.outbound_webhook import (
    RESPONSE_BODY_LIMIT,
    DeliveryAttempt,
    DeliveryFailureKind,
    FakeOutboundWebhookSender,
    HttpxOutboundWebhookSender,
    failure,
    make_outbound_webhook_sender,
    success,
    truncate_body,
)


class _StubResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _StubClient:
    """Minimal injected http client — records, then answers."""

    def __init__(self, response=None, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "content": content, "headers": headers, "timeout": timeout}
        )
        if self._raises is not None:
            raise self._raises
        return self._response


class TestOutcomeClassification:
    @pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
    @pytest.mark.asyncio
    async def test_any_2xx_is_success(self, status):
        client = _StubClient(_StubResponse(status, "ok"))
        sender = HttpxOutboundWebhookSender(http_client=client)

        attempt = await sender.send(url="https://x.test/h", body="{}")

        assert attempt.succeeded is True
        assert attempt.status_code == status

    @pytest.mark.asyncio
    async def test_a_500_is_a_failure_not_an_exception(self):
        client = _StubClient(_StubResponse(500, "boom"))
        sender = HttpxOutboundWebhookSender(http_client=client)

        attempt = await sender.send(url="https://x.test/h", body="{}")

        assert attempt.succeeded is False
        assert attempt.failure_kind is DeliveryFailureKind.HTTP_ERROR
        assert attempt.status_code == 500

    @pytest.mark.asyncio
    async def test_a_timeout_is_reported_not_raised(self):
        client = _StubClient(raises=httpx.TimeoutException("too slow"))
        sender = HttpxOutboundWebhookSender(http_client=client)

        attempt = await sender.send(url="https://x.test/h", body="{}")

        assert attempt.succeeded is False
        assert attempt.failure_kind is DeliveryFailureKind.TIMEOUT

    @pytest.mark.asyncio
    async def test_a_transport_error_is_reported_not_raised(self):
        client = _StubClient(raises=httpx.ConnectError("refused"))
        sender = HttpxOutboundWebhookSender(http_client=client)

        attempt = await sender.send(url="https://x.test/h", body="{}")

        assert attempt.succeeded is False
        assert attempt.failure_kind is DeliveryFailureKind.TRANSPORT_ERROR

    @pytest.mark.asyncio
    async def test_response_body_is_truncated_before_it_reaches_a_row(self):
        client = _StubClient(_StubResponse(500, "x" * 50_000))
        sender = HttpxOutboundWebhookSender(http_client=client)

        attempt = await sender.send(url="https://x.test/h", body="{}")

        assert len(attempt.response_body) == RESPONSE_BODY_LIMIT


class TestRetryability:
    """`is_retryable` lives on the outcome so both consumers share one
    judgement — two copies would eventually disagree about 429."""

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
    def test_a_4xx_is_not_retryable(self, status):
        assert failure(status_code=status).is_retryable is False

    @pytest.mark.parametrize("status", [408, 429])
    def test_the_two_documented_4xx_exceptions_are_retryable(self, status):
        assert failure(status_code=status).is_retryable is True

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_a_5xx_is_retryable(self, status):
        assert failure(status_code=status).is_retryable is True

    def test_a_timeout_is_retryable(self):
        assert failure(kind=DeliveryFailureKind.TIMEOUT).is_retryable is True

    def test_a_transport_error_is_retryable(self):
        assert failure(kind=DeliveryFailureKind.TRANSPORT_ERROR).is_retryable is True

    def test_a_success_is_never_retryable(self):
        assert success().is_retryable is False


class TestHeaders:
    @pytest.mark.asyncio
    async def test_caller_headers_win_over_the_defaults(self):
        """A consumer forwarding a vendor's request verbatim must be able
        to override even Content-Type."""
        client = _StubClient(_StubResponse(200))
        sender = HttpxOutboundWebhookSender(http_client=client)

        await sender.send(
            url="https://x.test/h",
            body="{}",
            headers={"Content-Type": "text/plain", "Authorization": "Basic abc"},
        )

        sent = client.calls[0]["headers"]
        assert sent["Content-Type"] == "text/plain"
        assert sent["Authorization"] == "Basic abc"

    @pytest.mark.asyncio
    async def test_a_user_agent_identifies_us_to_the_subscriber(self):
        client = _StubClient(_StubResponse(200))
        sender = HttpxOutboundWebhookSender(http_client=client)

        await sender.send(url="https://x.test/h", body="{}")

        assert "NoctusAI" in client.calls[0]["headers"]["User-Agent"]


class TestFake:
    @pytest.mark.asyncio
    async def test_scripted_outcomes_are_consumed_in_order(self):
        sender = FakeOutboundWebhookSender(
            outcomes=[failure(status_code=503), failure(status_code=503), success()]
        )

        first = await sender.send(url="u", body="b")
        second = await sender.send(url="u", body="b")
        third = await sender.send(url="u", body="b")

        assert [first.succeeded, second.succeeded, third.succeeded] == [
            False,
            False,
            True,
        ]

    @pytest.mark.asyncio
    async def test_the_default_outcome_repeats_once_the_script_runs_out(self):
        """A finite script plus an infinite default is what lets a test
        say "fail twice then succeed" without also pinning how many times
        the consumer retries."""
        sender = FakeOutboundWebhookSender(outcomes=[failure(status_code=500)])

        await sender.send(url="u", body="b")
        after = await sender.send(url="u", body="b")

        assert after.succeeded is True

    @pytest.mark.asyncio
    async def test_requests_are_recorded_for_assertions(self):
        sender = FakeOutboundWebhookSender()

        await sender.send(url="https://x.test/h", body='{"a":1}', headers={"H": "v"})

        assert sender.call_count == 1
        assert sender.last_request.url == "https://x.test/h"
        assert sender.last_request.body == '{"a":1}'
        assert sender.last_request.headers == {"H": "v"}


class TestFactory:
    def test_fake_branch(self):
        assert isinstance(
            make_outbound_webhook_sender(use_fake=True), FakeOutboundWebhookSender
        )

    def test_real_branch(self):
        assert isinstance(
            make_outbound_webhook_sender(), HttpxOutboundWebhookSender
        )

    @pytest.mark.asyncio
    async def test_both_branches_satisfy_the_same_surface(self):
        """The point of the factory: a consumer selects once and never
        branches on environment again."""
        for sender in (
            make_outbound_webhook_sender(use_fake=True),
            make_outbound_webhook_sender(http_client=_StubClient(_StubResponse(200))),
        ):
            attempt = await sender.send(url="https://x.test/h", body="{}")
            assert isinstance(attempt, DeliveryAttempt)


class TestTruncateBody:
    def test_none_survives_as_none(self):
        assert truncate_body(None) is None

    def test_short_text_is_untouched(self):
        assert truncate_body("hi") == "hi"

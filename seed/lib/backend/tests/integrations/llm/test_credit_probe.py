"""`llm.credit_probe` — the one "no credit vs rate limit vs bad key" classifier
and the OpenAI probe over an injected `httpx` transport (no network)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from noctusai_lib.integrations.llm.credit_probe import (
    CreditProbe,
    FakeCreditProbe,
    OpenAICreditProbe,
    classify_provider_failure,
    make_credit_probe,
)

AT = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
NO_CREDIT = json.dumps({"error": {"message": "You have no credits remaining.", "type": "insufficient_quota",
                                  "code": "insufficient_quota"}})


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, "{}", "ok"),
        (429, NO_CREDIT, "sem_credito"),
        (400, "credit_balance_too_low", "sem_credito"),
        (429, '{"error": {"type": "requests", "code": "rate_limit_exceeded"}}', "limite"),
        (401, '{"error": {"code": "invalid_api_key"}}', "chave_invalida"),
        (500, "boom", "erro"),
        (None, "", "erro"),
    ],
)
def test_classifier(status, body, expected) -> None:
    assert classify_provider_failure(status, body) == expected


def _probe(status: int, body: str, seen: list) -> OpenAICreditProbe:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICreditProbe(http_client=client, now=lambda: AT)


def test_openai_probe_reports_no_credit_with_one_token_call() -> None:
    seen: list = []
    result = asyncio.run(_probe(429, NO_CREDIT, seen).probe("sk-test"))
    assert result.status == "sem_credito" and not result.ok
    assert result.http_status == 429 and result.checked_at == AT
    [request] = seen
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert json.loads(request.content)["max_tokens"] == 1


def test_openai_probe_ok_and_missing_key() -> None:
    seen: list = []
    probe = _probe(200, "{}", seen)
    assert asyncio.run(probe.probe("sk")).ok
    assert asyncio.run(probe.probe(None)).status == "sem_chave"
    assert len(seen) == 1  # no call without a key


def test_openai_probe_connection_error_is_erro() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = asyncio.run(OpenAICreditProbe(http_client=client).probe("sk"))
    assert result.status == "erro" and "ConnectError" in result.message


def test_fake_and_factory() -> None:
    fake = make_credit_probe(use_fake=True)
    assert isinstance(fake, FakeCreditProbe) and isinstance(fake, CreditProbe)
    fake.status = "sem_credito"
    assert asyncio.run(fake.probe("k")).status == "sem_credito"
    assert asyncio.run(fake.probe("")).status == "sem_chave"
    assert isinstance(make_credit_probe(), OpenAICreditProbe)
    with pytest.raises(ValueError):
        make_credit_probe("gemini")

"""Tests for the absorbed scheduling support services (Wave 2.3):
sanitization (pure-logic PII redaction), retry (seed-RetryPolicy
composition), metrics + anomaly + per-conversation rate-limit singletons,
and the W2.1 register() seam contract.
"""
from __future__ import annotations

import json

import pytest

from noctusai_lib.domain.chatbot import ToolCall, ToolResult
from app.modules.scheduling import register
from app.modules.scheduling.metrics import NoopCounter, configure_counter, get_counter
from app.modules.scheduling.retry import RETRY_POLICY_CALENDAR, retry_call
from app.modules.scheduling.sanitization import (
    sanitize_tool_result,
    wrap_handler,
)


def test_sanitize_redacts_email_and_phone_and_cpf():
    raw = json.dumps(
        {
            "email": "corretor@imobiliaria.com.br",
            "phone": "+55 11 99999-9999",
            "cpf": "123.456.789-00",
        }
    )
    out = sanitize_tool_result(raw)
    assert "corretor@imobiliaria.com.br" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out
    assert "[REDACTED_CPF]" in out


def test_sanitize_is_idempotent():
    raw = "contato corretor@x.com"
    once = sanitize_tool_result(raw)
    twice = sanitize_tool_result(once)
    assert once == twice


def test_wrap_handler_sanitizes_tool_result():
    def _handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            content=json.dumps({"email": "a@b.com"}),
        )

    wrapped = wrap_handler(_handler)
    result = wrapped(ToolCall(call_id="x", name="t", arguments={}))
    assert "a@b.com" not in result.content
    assert "[REDACTED_EMAIL]" in result.content


def test_retry_call_succeeds_first_try_no_sleep():
    calls = {"n": 0}

    def _ok():
        calls["n"] += 1
        return "done"

    out = retry_call(_ok, policy=RETRY_POLICY_CALENDAR, sleep=lambda _s: None)
    assert out == "done"
    assert calls["n"] == 1


def test_retry_call_retries_then_succeeds():
    state = {"n": 0}

    def _flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    out = retry_call(
        _flaky,
        policy=RETRY_POLICY_CALENDAR,
        transient_exceptions=(RuntimeError,),
        sleep=lambda _s: None,
    )
    assert out == "ok"
    assert state["n"] == 3


def test_retry_call_exhausts_and_reraises():
    def _always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        retry_call(
            _always_fail,
            policy=RETRY_POLICY_CALENDAR,
            transient_exceptions=(RuntimeError,),
            sleep=lambda _s: None,
        )


def test_metrics_default_is_noop_counter():
    assert isinstance(get_counter(), NoopCounter)
    configure_counter(NoopCounter())  # idempotent
    assert isinstance(get_counter(), NoopCounter)


def test_register_contract_returns_module_registration():
    reg = register()
    # ModuleRegistration shape from app.main (W2.1 seam contract).
    assert hasattr(reg, "routers")
    assert hasattr(reg, "standard_routers")
    assert len(reg.routers) == 1
    assert reg.standard_routers == ("health",)
    # The contributed router carries the scheduling prefix.
    assert any(
        getattr(r, "path", "").startswith("/api/scheduling")
        for r in reg.routers[0].routes
    )

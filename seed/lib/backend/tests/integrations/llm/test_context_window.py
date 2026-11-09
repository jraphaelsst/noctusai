"""`context_window.fit_history`: fits a history into a token budget without ever breaking a tool pair."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm.context_window import SUMMARY_PREFIX, SummaryCache, estimate_tokens, fit_history
from noctusai_lib.integrations.llm.tool_calling import ChatMessage, ToolCall, ToolResult


def _chat(n: int, size: int = 90) -> list[dict]:
    out = []
    for i in range(n):
        out.append({"role": "user", "content": f"u{i} " + "x" * size})
        out.append({"role": "assistant", "content": f"a{i} " + "y" * size})
    out.append({"role": "user", "content": "latest"})
    return out


def test_history_that_fits_is_returned_untouched():
    msgs = _chat(3)
    r = fit_history(msgs, max_tokens=100_000)
    assert r.messages == msgs and all(a is b for a, b in zip(r.messages, msgs)) and not r.trimmed


def test_over_budget_drops_oldest_keeps_latest_and_opens_on_user():
    msgs = _chat(30)
    r = fit_history(msgs, max_tokens=600)
    assert r.trimmed and r.messages[-1]["content"] == "latest"
    assert r.messages[0]["role"] == "user"
    assert r.tokens_after <= 600
    assert r.messages == msgs[len(msgs) - len(r.messages):], "a contiguous newest suffix, order preserved"


def test_latest_unit_kept_even_when_it_alone_exceeds_budget():
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "z" * 5000}]
    r = fit_history(msgs, max_tokens=50)
    assert r.messages == [msgs[-1]]


def test_leading_system_is_pinned():
    msgs = [("system", "regra")] + [("user" if i % 2 == 0 else "assistant", "m" * 90) for i in range(40)] + [("user", "fim")]
    r = fit_history(msgs, max_tokens=500)
    assert r.messages[0] == ("system", "regra") and r.messages[-1] == ("user", "fim") and r.trimmed


def test_tool_call_never_separated_from_its_result():
    call = ChatMessage.assistant("", [ToolCall("c1", "lookup", {"code": "X"})])
    res = ChatMessage.tool(ToolResult("c1", "r" * 300))
    msgs = [ChatMessage.user("q0" + "x" * 300), call, res, ChatMessage.assistant("ok"), ChatMessage.user("latest")]
    for budget in range(10, 400, 7):
        r = fit_history(msgs, max_tokens=budget, start_with_user=False)
        roles = [m.role for m in r.messages]
        assert ("tool" in roles) == any(m.tool_calls for m in r.messages), f"orphan at budget {budget}"
        if "tool" in roles:
            assert roles.index("tool") > 0 and r.messages[roles.index("tool") - 1].tool_calls


def test_dict_tool_messages_stay_paired():
    msgs = [
        {"role": "user", "content": "q" * 300},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "r" * 300},
        {"role": "user", "content": "latest"},
    ]
    for budget in range(10, 400, 11):
        roles = [m["role"] for m in fit_history(msgs, max_tokens=budget, start_with_user=False).messages]
        assert roles[0] != "tool"
        assert ("tool" in roles) == ("assistant" in roles)


def test_hysteresis_trims_below_budget_so_the_window_moves_in_steps():
    r = fit_history(_chat(30), max_tokens=1000, low_water=0.5)
    assert r.tokens_after <= 500


def test_summarizer_called_only_over_threshold_and_cached_per_conversation():
    calls = []

    def summ(dropped):
        calls.append(len(dropped))
        return "resumo"

    cache = SummaryCache()
    msgs = _chat(30)
    kw = dict(max_tokens=600, summarizer=summ, conversation_key="c1", summary_cache=cache, summarize_over_tokens=50)
    a = fit_history(msgs, **kw)
    b = fit_history(msgs, **kw)
    assert len(calls) == 1, "second fit hits the per-conversation cache"
    assert a.summary == "resumo" == b.summary
    assert a.messages[0]["content"].startswith(SUMMARY_PREFIX)
    fit_history(msgs, **{**kw, "summarize_over_tokens": 10**9, "conversation_key": "c2"})
    assert len(calls) == 1, "below the threshold: no summarizer call at all"


def test_summarizer_failure_degrades_to_plain_trimming():
    def boom(_):
        raise RuntimeError("down")

    r = fit_history(_chat(30), max_tokens=600, summarizer=boom, summarize_over_tokens=1)
    assert r.trimmed and r.summary is None and r.messages[-1]["content"] == "latest"


def test_invalid_args_raise():
    with pytest.raises(ValueError):
        fit_history([], max_tokens=0)
    with pytest.raises(ValueError):
        fit_history([], max_tokens=10, low_water=0)


def test_estimator_is_conservative():
    assert estimate_tokens("a" * 30) == 10 and estimate_tokens("") == 0

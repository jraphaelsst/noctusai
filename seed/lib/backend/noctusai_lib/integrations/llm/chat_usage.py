"""`chat_completion_with_usage` -- one chat call that ALSO returns what it cost.

`chat_completion` returns text only (usage goes to the configured `UsageSink`), so every caller that must
attribute cost to ONE call -- an eval judge, an AI draft generator with a per-run spend cap -- used to install
a process-wide capturing sink behind a lock. This entry point uses the `coletar_uso()` scope instead: the SAME
`UsageEvent`s the sink receives, collected per task context, so concurrent calls never see each other's events
and nothing global is mutated.

Missing usage (no event recorded -- a provider that does not report) is reported as `usage=None`, never as a
silent zero: the caller decides how to treat an unmeasured call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .chat import chat_completion
from .usage import UsageEvent, coletar_uso

__all__ = ["ChatCompletionResult", "ChatUsage", "chat_completion_with_usage"]


@dataclass(frozen=True)
class ChatUsage:
    """The summed usage of the events one call recorded."""

    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    events: int


@dataclass(frozen=True)
class ChatCompletionResult:
    text: str
    #: ``None`` when no usage event was recorded for the call (unmeasured, NOT zero).
    usage: Optional[ChatUsage]


def _sum(events: list[UsageEvent]) -> ChatUsage:
    return ChatUsage(
        cost_usd=sum(e.cost_estimate_usd or 0.0 for e in events),
        prompt_tokens=sum(e.prompt_tokens or 0 for e in events),
        completion_tokens=sum(e.completion_tokens or 0 for e in events),
        cache_creation_input_tokens=sum(e.cache_creation_input_tokens or 0 for e in events),
        cache_read_input_tokens=sum(e.cache_read_input_tokens or 0 for e in events),
        events=len(events),
    )


async def chat_completion_with_usage(messages: list[dict], **kwargs: Any) -> ChatCompletionResult:
    """`chat_completion(messages, **kwargs)` plus the call's own usage. Same arguments, same exceptions."""
    with coletar_uso() as eventos:
        text = await chat_completion(messages, **kwargs)
    return ChatCompletionResult(text=text, usage=_sum(eventos) if eventos else None)

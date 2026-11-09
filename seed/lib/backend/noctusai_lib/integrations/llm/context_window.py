"""Server-side context-window management: fit a conversation history into a token budget.

A client (or a thread store) can hand the server more history than a model should read. The server owns
the fit, not the client: this module trims the OLDEST turns until the history is within `max_tokens`.

Rules (each is a test):

* **A history that already fits is returned untouched** - same list contents, same objects, byte-identical
  prompt. The fit only ever acts on a history that is over budget.
* **Atomic units.** An assistant message that carries tool calls and the tool results that answer it form
  ONE unit; a unit is kept or dropped whole, so a `tool_call` is never cut from its `tool_result` (every
  provider rejects an orphan on either side).
* **The latest unit is always kept** (the turn being answered), even when it alone exceeds the budget -
  per-message size is a validation concern of the caller, not something to silently cut here.
* **Leading system messages are pinned** (`pin_system`). Provider-order rule: when the kept window would
  start with an assistant turn, those leading assistant units are dropped too (`start_with_user`).
* **Hysteresis.** When it must trim, it trims down to `low_water` x budget, not to the brim, so the window
  moves in steps: the kept prefix stays stable across consecutive turns (prompt-cache friendly) and an
  optional summary is not recomputed every turn.
* **Pure trimming first.** An optional `summarizer` is called only when the dropped text exceeds
  `summarize_over_tokens`; its result is memoised per conversation in `SummaryCache`. A summarizer that
  raises or returns nothing degrades LOUDLY (logged) to plain trimming - the turn is never blocked by it.

Token counting is a conservative estimator by default (`estimate_tokens`: UTF-8 bytes / 3, over-counts
pt-BR/English prose so the fit errs on the side of trimming too much, never too little). Pass `count_tokens`
to use a real tokenizer.

Messages may be dicts (`{"role", "content", ...}`), `ChatMessage`-like objects (`.role`/`.content`/
`.tool_calls`/`.tool_call_id`) or `(role, text)` tuples. `KB § PATTERNS/ai/ai-engineering-canon.md` §3.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: per-message framing overhead (role markers, separators) charged on top of the content estimate
_MESSAGE_OVERHEAD_TOKENS = 4
SUMMARY_PREFIX = "[Resumo da conversa anterior]"

TokenCounter = Callable[[str], int]
Summarizer = Callable[[Sequence[Any]], Optional[str]]


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: UTF-8 bytes / 3 (rounded up). Real tokenizers average ~3.5-4.5 bytes/token
    on prose, so this over-counts and the fit trims early rather than overflowing the window."""
    return -(-len(text.encode("utf-8")) // 3)


def _get(m: Any, key: str, idx: int | None = None) -> Any:
    if isinstance(m, tuple):
        return m[idx] if idx is not None and idx < len(m) else None
    if isinstance(m, dict):
        return m.get(key)
    return getattr(m, key, None)


def _role(m: Any) -> str:
    return str(_get(m, "role", 0) or "")


def _text(m: Any) -> str:
    c = _get(m, "content", 1)
    if c is None:
        c = ""
    if not isinstance(c, str):
        c = json.dumps(c, ensure_ascii=False, default=str)
    calls = _get(m, "tool_calls")
    if calls and not isinstance(m, tuple):
        c += json.dumps(calls, ensure_ascii=False, default=str)
    return c


def _has_tool_calls(m: Any) -> bool:
    if isinstance(m, tuple):
        return False
    if _role(m) == "assistant" and _get(m, "tool_calls"):
        return True
    content = _get(m, "content")  # Anthropic-style blocks
    return _role(m) == "assistant" and isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content)


def _is_tool_result(m: Any) -> bool:
    if isinstance(m, tuple):
        return False
    if _role(m) == "tool" or _get(m, "tool_call_id"):
        return True
    content = _get(m, "content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _units(messages: Sequence[Any]) -> list[list[Any]]:
    """Group into atomic units: an assistant tool-call message + the tool results after it stay together; a
    stray tool result with no opener attaches to the unit before it so it is never separated either."""
    units: list[list[Any]] = []
    for m in messages:
        if _is_tool_result(m) and units:
            units[-1].append(m)
        else:
            units.append([m])
    return units


@dataclass(frozen=True)
class FitResult:
    messages: list[Any]
    #: messages removed from the window (oldest first); empty when the history already fit
    dropped: list[Any] = field(default_factory=list)
    tokens_before: int = 0
    tokens_after: int = 0
    summary: Optional[str] = None

    @property
    def trimmed(self) -> bool:
        return bool(self.dropped)


class SummaryCache:
    """Per-conversation memo of summaries: `(conversation_key, digest of the summarised messages) -> text`.
    Bounded LRU, thread-safe. The digest makes a hit exact: the same dropped prefix is never summarised twice."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max = max_entries
        self._data: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, conversation_key: str, digest: str) -> Optional[str]:
        with self._lock:
            v = self._data.get((conversation_key, digest))
            if v is not None:
                self._data.move_to_end((conversation_key, digest))
            return v

    def put(self, conversation_key: str, digest: str, summary: str) -> None:
        with self._lock:
            self._data[(conversation_key, digest)] = summary
            self._data.move_to_end((conversation_key, digest))
            while len(self._data) > self._max:
                self._data.popitem(last=False)


DEFAULT_SUMMARY_CACHE = SummaryCache()


def _digest(messages: Sequence[Any]) -> str:
    h = hashlib.sha256()
    for m in messages:
        h.update(_role(m).encode())
        h.update(b"\x00")
        h.update(_text(m).encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()


def fit_history(
    messages: Sequence[Any],
    *,
    max_tokens: int,
    count_tokens: TokenCounter = estimate_tokens,
    pin_system: bool = True,
    start_with_user: bool = True,
    low_water: float = 0.75,
    summarizer: Optional[Summarizer] = None,
    summarize_over_tokens: int = 4000,
    conversation_key: Optional[str] = None,
    summary_cache: SummaryCache = DEFAULT_SUMMARY_CACHE,
    summary_role: str = "user",
) -> FitResult:
    """Fit `messages` into `max_tokens`; see the module docstring for the rules."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 < low_water <= 1:
        raise ValueError("low_water must be in (0, 1]")

    def cost(m: Any) -> int:
        return count_tokens(_text(m)) + _MESSAGE_OVERHEAD_TOKENS

    msgs = list(messages)
    total = sum(cost(m) for m in msgs)
    if total <= max_tokens:
        return FitResult(msgs, [], total, total)

    n_pinned = 0
    if pin_system:
        while n_pinned < len(msgs) and _role(msgs[n_pinned]) == "system":
            n_pinned += 1
    pinned, body = msgs[:n_pinned], msgs[n_pinned:]
    units = _units(body)
    pinned_cost = sum(cost(m) for m in pinned)
    target = max(int(max_tokens * low_water), 1)

    kept_units: list[list[Any]] = []
    used = pinned_cost
    for unit in reversed(units):
        c = sum(cost(m) for m in unit)
        if kept_units and used + c > target:
            break
        kept_units.append(unit)  # the newest unit is kept whatever its size
        used += c
    kept_units.reverse()
    n_dropped_units = len(units) - len(kept_units)
    if start_with_user:  # a window must open on a user turn (provider ordering); never empties the window
        while len(kept_units) > 1 and _role(kept_units[0][0]) == "assistant":
            kept_units.pop(0)
            n_dropped_units += 1
    dropped = [m for u in units[:n_dropped_units] for m in u]
    kept = [m for u in kept_units for m in u]

    summary: Optional[str] = None
    if summarizer is not None and dropped and sum(cost(m) for m in dropped) > summarize_over_tokens:
        digest = _digest(dropped)
        if conversation_key is not None:
            summary = summary_cache.get(conversation_key, digest)
        if summary is None:
            try:
                summary = summarizer(dropped)
            except Exception:
                logger.exception("context_window: summarizer failed; falling back to plain trimming")
                summary = None
            if summary and conversation_key is not None:
                summary_cache.put(conversation_key, digest, summary)
    out = [*pinned]
    if summary:
        out.append(_summary_message(msgs, summary_role, f"{SUMMARY_PREFIX}\n{summary}"))
    out.extend(kept)
    after = sum(cost(m) for m in out)
    logger.info(
        "context_window: trimmed %d message(s), %d -> %d est. tokens (budget %d, summary=%s)",
        len(dropped), total, after, max_tokens, bool(summary),
    )
    return FitResult(out, dropped, total, after, summary)


def _summary_message(like: Sequence[Any], role: str, text: str) -> Any:
    """A summary message shaped like the history's own messages (dict / tuple / object-with-`role`-`content`)."""
    sample = like[0]
    if isinstance(sample, tuple):
        return (role, text)
    if isinstance(sample, dict):
        return {"role": role, "content": text}
    from .tool_calling import ChatMessage  # objects: the platform's own normalized message
    if role == "system":
        return ChatMessage.system(text)
    return ChatMessage.assistant(text) if role == "assistant" else ChatMessage.user(text)


__all__ = ["FitResult", "SummaryCache", "estimate_tokens", "fit_history", "DEFAULT_SUMMARY_CACHE", "SUMMARY_PREFIX"]

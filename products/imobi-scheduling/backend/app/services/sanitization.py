"""PII sanitization for LLM-tool dispatch outputs — Phase 11 security hardening.

**Why this layer exists.** When a tool handler (e.g. `lookup_property`)
returns a payload containing a corretor's phone number, an end-user's
full name, or any PII, that payload is fed back into the LLM
conversation as a `{"role": "tool", "content": ...}` message. Two
risks follow:

  1. **Prompt-injection amplification.** If an attacker can influence
     what the tool returns (e.g. by crafting a property search that
     matches an attacker-controlled record), embedded PII becomes
     leverage for social-engineering downstream users.
  2. **LGPD exposure surface.** Tool results land in `tool_call_audits`
     (per `KB § PATTERNS/llm-tool-audit.md`); unsanitized PII bloats
     the LGPD-controlled rows + makes redaction queries more
     expensive.

**Sanitization scope** (mirrors `KB § PATTERNS/llm-bot-security.md § 2a`):

  - Brazilian phone numbers (`(11) 99999-9999`, `+5511999999999`,
    `11 99999-9999` — high-recall pattern).
  - Email addresses (RFC-shape).
  - CPF (`123.456.789-00` / 11 digits) — Brazilian individual tax ID.
  - CNPJ (`12.345.678/0001-90` / 14 digits) — Brazilian business tax ID.
  - URLs hosting credentials (`https://user:pw@host`) — defense against
    a malicious tool leaking auth in a debug payload.

**Not scoped here**: full-name redaction (too high false-positive rate
without a corretor/user roster lookup), generic numeric strings (would
break the property/condo IDs the bot legitimately echoes back).

**Seam shape**: a single function `sanitize_tool_result(content: str) -> str`
plus `wrap_handler(handler) -> handler` that composes onto the
`build_tool_handler` output. The conversation framework wiring at
`app/services/conversation.py::_build_processor` swaps the unwrapped
handler for the wrapped one. No call-site change at any tool impl.

**Seed lift destination**: pure-logic shaping (no IO). Exemption test
per `KB § PATTERNS/seed-fake-real-adapter.md` § Exemption fires —
"would a Fake exercise different code than the Real?" No. So no
Fake/Real split. **N=2 destination**: `noctusai_lib.primitives.pii`
(stateless redactors → primitives layer per `KB § PATTERNS/seed-lib-layout.md`).
N=1 today; surface candidate logged in Improvements when a second
product needs PII redaction.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

logger = logging.getLogger(__name__)


# Email — RFC-shape sufficient for redaction (we don't need to validate).
_EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
)

# CNPJ — formatted (12.345.678/0001-90) OR digit-stream (14 digits).
_CNPJ_FORMATTED_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_CNPJ_DIGITS_RE = re.compile(r"\b\d{14}\b")

# CPF — formatted (123.456.789-00) OR digit-stream (11 digits).
_CPF_FORMATTED_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CPF_DIGITS_RE = re.compile(r"\b\d{11}\b")

# Brazilian phone numbers. Covers:
#   +5511999999999
#   +55 11 99999-9999
#   (11) 99999-9999
#   11 99999-9999
#   11999999999  (10-11 digits)
_PHONE_RE = re.compile(
    r"""
    (?:
      (?:\+?55[\s\-]?)?    # optional country code
      \(?\d{2}\)?[\s\-]?   # area code
      \d{4,5}[\s\-]?\d{4}  # subscriber
    )
    """,
    re.VERBOSE,
)

# URLs with embedded credentials — https://user:pw@host
_URL_CRED_RE = re.compile(
    r"https?://[^/\s:@]+:[^/\s@]+@[^\s]+"
)


# Order matters — apply longest/most specific first so digit-stream
# patterns don't eat formatted ones.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_URL_CRED_RE, "[REDACTED_URL_WITH_CREDS]"),
    (_EMAIL_RE, "[REDACTED_EMAIL]"),
    (_CNPJ_FORMATTED_RE, "[REDACTED_CNPJ]"),
    (_CPF_FORMATTED_RE, "[REDACTED_CPF]"),
    (_PHONE_RE, "[REDACTED_PHONE]"),
    # Digit-stream fallbacks AFTER formatted variants + phone.
    (_CNPJ_DIGITS_RE, "[REDACTED_CNPJ]"),
    (_CPF_DIGITS_RE, "[REDACTED_CPF]"),
]


def sanitize_tool_result(content: str) -> str:
    """Redact PII patterns from a tool-result `content` string.

    Idempotent — running twice on the same string yields the same
    output. The redaction tags themselves contain no PII patterns, so
    a re-sanitization pass is a no-op.

    Args:
        content: The raw tool-handler output (typically JSON-encoded).
            May be empty / non-PII — passed through unchanged.

    Returns:
        Sanitized string. Same shape as input (still parseable as
        JSON if input was JSON — the redaction tokens are quoted
        substrings when they appear inside JSON string values).
    """
    if not content:
        return content
    out = content
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def wrap_handler(
    handler: Callable[[ToolCall], ToolResult],
) -> Callable[[ToolCall], ToolResult]:
    """Return a `tool_handler` that sanitizes results before returning.

    Wraps a `Callable[[ToolCall], ToolResult]` (the seed's
    `ToolHandler` shape) so every tool result's `content` field is
    passed through `sanitize_tool_result`. Per the seed dispatcher
    (`seed/lib/backend/noctusai_lib/domain/chatbot/llm_dispatcher.py`),
    `tool_handler(call)` runs BEFORE `audit_writer(call, result)` —
    meaning the audit writer sees the sanitized content. This is the
    intended behavior: the unsanitized PII is already in the
    underlying DB rows the tool reads; the audit table's purpose is
    "did this tool fire?" not "what was the raw payload?".

    The redaction token count is debug-logged so ops can spot a tool
    that's leaking PII into the conversation surface.
    """

    def _sanitized_handler(call: ToolCall) -> ToolResult:
        raw = handler(call)
        sanitized_content = sanitize_tool_result(raw.content)
        if sanitized_content != raw.content:
            logger.debug(
                "Tool result sanitized: tool=%s call_id=%s redactions_applied=%d",
                call.name,
                call.call_id,
                sum(
                    sanitized_content.count(tag)
                    for _pat, tag in _PATTERNS
                ),
            )
        return ToolResult(call_id=raw.call_id, content=sanitized_content)

    return _sanitized_handler


def sanitize_json_payload(payload: dict) -> dict:
    """Deep-walk a dict + sanitize string values.

    Convenience for tests / callers that have the dict pre-JSON-dump.
    The runtime path uses `sanitize_tool_result` on the JSON string
    directly.

    Args:
        payload: Arbitrary dict (typically tool-handler output before
            it's JSON-encoded).

    Returns:
        New dict with PII redacted in string values. Lists + nested
        dicts are walked recursively. Non-string scalars (int, bool,
        None) pass through unchanged.
    """
    return _walk(payload)


def _walk(value):
    if isinstance(value, str):
        return sanitize_tool_result(value)
    if isinstance(value, dict):
        return {k: _walk(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v) for v in value]
    return value


__all__ = [
    "sanitize_tool_result",
    "sanitize_json_payload",
    "wrap_handler",
]

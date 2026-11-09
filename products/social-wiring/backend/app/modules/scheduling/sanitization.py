"""PII sanitization for LLM-tool dispatch outputs — security hardening (absorbed from imobi-scheduling, Wave 2.3).

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

**Seed lift (done)**: the patterns and the redaction live in the seed organ
`noctusai_lib.integrations.llm.guardrails.redaction` (`redact_pii`,
`redact_payload`, `count_redactions`); this module keeps only the product seam
(`wrap_handler` over the `ToolCall`/`ToolResult` shape) and the historical names.
"""
from __future__ import annotations

import logging
from typing import Callable

from noctusai_lib.domain.chatbot import ToolCall, ToolResult
from noctusai_lib.integrations.llm.guardrails import count_redactions, redact_payload, redact_pii

logger = logging.getLogger(__name__)


def sanitize_tool_result(content: str) -> str:
    """Redact PII patterns from a tool-result `content` string (idempotent; empty input passes through)."""
    return redact_pii(content)


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
                count_redactions(sanitized_content),
            )
        return ToolResult(call_id=raw.call_id, content=sanitized_content)

    return _sanitized_handler


def sanitize_json_payload(payload: dict) -> dict:
    """Deep-walk a dict + sanitize string values (lists/dicts walked, non-string scalars unchanged)."""
    return redact_payload(payload)


__all__ = [
    "sanitize_tool_result",
    "sanitize_json_payload",
    "wrap_handler",
]

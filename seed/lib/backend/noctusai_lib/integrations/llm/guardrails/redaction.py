"""PII redaction of text handed back to a model (tool results) -- moved from social-wiring ``scheduling/sanitization``.

Order matters: longest/most specific pattern first so the digit-stream fallbacks do not eat formatted ones. Idempotent: the
redaction tags contain no PII pattern. Scope (see ``KB § PATTERNS/security/llm-bot-security.md`` § 2a): credential URLs,
e-mail, CNPJ, CPF, Brazilian phones. NOT scoped: names (too many false positives without a roster) and generic numbers
(they would break the property/condo ids a bot legitimately echoes back).
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["REDACTION_PATTERNS", "count_redactions", "redact_payload", "redact_pii"]

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_CNPJ_FORMATTED_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_CNPJ_DIGITS_RE = re.compile(r"\b\d{14}\b")
_CPF_FORMATTED_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CPF_DIGITS_RE = re.compile(r"\b\d{11}\b")
# +5511999999999 / +55 11 99999-9999 / (11) 99999-9999 / 11 99999-9999 / 11999999999
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
_URL_CRED_RE = re.compile(r"https?://[^/\s:@]+:[^/\s@]+@[^\s]+")

REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_URL_CRED_RE, "[REDACTED_URL_WITH_CREDS]"),
    (_EMAIL_RE, "[REDACTED_EMAIL]"),
    (_CNPJ_FORMATTED_RE, "[REDACTED_CNPJ]"),
    (_CPF_FORMATTED_RE, "[REDACTED_CPF]"),
    (_PHONE_RE, "[REDACTED_PHONE]"),
    (_CNPJ_DIGITS_RE, "[REDACTED_CNPJ]"),
    (_CPF_DIGITS_RE, "[REDACTED_CPF]"),
]


def redact_pii(content: str) -> str:
    """``content`` with every PII pattern replaced by its tag; empty input passes through."""
    if not content:
        return content
    out = content
    for pattern, replacement in REDACTION_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def count_redactions(redacted: str) -> int:
    """How many redaction tags ``redacted`` carries (for debug logging; counts only)."""
    return sum(redacted.count(tag) for _pat, tag in REDACTION_PATTERNS)


def redact_payload(value: Any) -> Any:
    """Deep-walk a payload and redact its string values; lists/dicts are rebuilt, other scalars pass through."""
    if isinstance(value, str):
        return redact_pii(value)
    if isinstance(value, dict):
        return {k: redact_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    return value

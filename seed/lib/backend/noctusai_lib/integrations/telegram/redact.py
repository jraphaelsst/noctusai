"""Bot-token redaction -- the token rides in the Bot API URL path (``/bot<id>:<secret>/method``), so every
string that could carry a URL (error text, httpx INFO logs) passes through here. Never log a token."""
from __future__ import annotations

import logging
import re

_TOKEN_RE = re.compile(r"bot\d{3,}:[A-Za-z0-9_-]{10,}")
_BARE_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")


def redact(text: object) -> str:
    s = str(text)
    s = _TOKEN_RE.sub("bot<redacted>", s)
    return _BARE_RE.sub("<redacted-token>", s)


def mask_token(token: str) -> str:
    """UI form: only the last 4 characters survive."""
    return f"{'*' * 8}{token[-4:]}" if token and len(token) > 4 else "*" * 8


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def install_httpx_redaction() -> None:
    """httpx logs ``HTTP Request: POST https://api.telegram.org/bot<TOKEN>/...`` at INFO: redact it. Idempotent."""
    for name in ("httpx", "httpcore"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, _RedactFilter) for f in lg.filters):
            lg.addFilter(_RedactFilter())

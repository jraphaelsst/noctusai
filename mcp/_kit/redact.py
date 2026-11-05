"""Structural secret redaction for every connector tool result.

A connector tool result goes straight into a model's context — and from there into
transcripts, summaries and logs. A vendor API that echoes a secret back (WAHA's
``GET /api/sessions/{name}`` returns ``config.webhooks[].hmac.key`` in clear; the leak
that motivated this, 2026-11-04) must never carry it that far.

``redact_secret_fields`` walks a JSON-shaped value and replaces the VALUE of every
secret-named field with ``"[redacted]"``. It is key-name based, so it needs no
knowledge of which secrets exist; the per-integration value-based redactors
(``redact_secrets`` / ``redact_api_key`` …) stay for free-text error messages.

Names that DESCRIBE a secret without being one (``token_prefix``, ``api_key_hint``,
``token_mascarado``, ``*_id``, ``*_at``, ``has_*``) are kept.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[redacted]"

#: A field whose (normalized) name ENDS in one of these holds a secret.
_SECRET_NAME = re.compile(
    r"(?:^|_)(?:api_?key|apikey|secret|client_secret|password|passwd|passphrase|"
    r"token|access_token|refresh_token|id_token|bearer|authorization|cookie|"
    r"private_key|signing_key|hmac_key|webhook_secret|session_key|credential|credentials)$"
)
#: …unless it is one of these descriptive shapes.
_DESCRIPTIVE = re.compile(r"(?:_prefix|_hint|_mascarado|_masked|_id|_ids|_at|_count|_type|_kind|_name)$|^has_|^is_")


def _norm(key: str) -> str:
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")


def _is_secret(key: str, parent: str) -> bool:
    k = _norm(key)
    if not k or _DESCRIPTIVE.search(k):
        return False
    if _SECRET_NAME.search(k):
        return True
    # `{"hmac": {"key": "..."}}` / `{"auth": {"key": ...}}`: a bare `key` under a
    # secret-ish parent is the secret itself.
    return k in {"key", "value"} and _norm(parent) in {"hmac", "auth", "signature", "signing", "secret", "credentials"}


def redact_secret_fields(value: Any, _parent: str = "") -> Any:
    """Return a copy of ``value`` with every secret-named field's value replaced."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_secret(k, _parent) and v not in (None, "", [], {}):
                out[k] = REDACTED
            else:
                out[k] = redact_secret_fields(v, str(k))
        return out
    if isinstance(value, list):
        return [redact_secret_fields(v, _parent) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_secret_fields(v, _parent) for v in value)
    return value


__all__ = ["REDACTED", "redact_secret_fields"]

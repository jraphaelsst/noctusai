"""Secret scrubbing for provider bodies (`InvoiceResult.raw`, webhook `raw`)."""
from __future__ import annotations

from typing import Any

_SECRET_KEY_FRAGMENTS = (
    "token", "senha", "password", "secret", "authorization", "certificado", "pfx",
    "api_key", "apikey",
)
REDACTED = "[redacted]"


def scrub(value: Any, *, extra_secrets: tuple[str, ...] = ()) -> Any:
    """Return a deep copy with secret-named keys and known secret strings removed."""
    secrets = tuple(s for s in extra_secrets if s)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if any(f in str(k).lower() for f in _SECRET_KEY_FRAGMENTS):
                out[k] = REDACTED
            else:
                out[k] = scrub(v, extra_secrets=secrets)
        return out
    if isinstance(value, list):
        return [scrub(v, extra_secrets=secrets) for v in value]
    if isinstance(value, str) and secrets:
        for s in secrets:
            if s in value:
                value = value.replace(s, REDACTED)
    return value

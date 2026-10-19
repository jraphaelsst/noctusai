"""Sentry event scrubbers: no request bodies, tokens, headers or PII leave the process.

Wired by ``configure_app`` as ``before_send`` / ``before_send_transaction``.
Defence in depth next to ``send_default_pii=False``,
``max_request_body_size="never"`` and ``include_local_variables=False``.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[Filtered]"

_SENSITIVE_KEYS = {
    "prompt", "texto", "conteudo", "system", "messages", "contexto",
    "cpf", "rg", "telefone", "phone", "email",
}
_TOKEN_QS = re.compile(
    r"([?&;]?)([^=&;\s]*(?:token|key|secret|password|code|signature|auth)[^=&;\s]*)=[^&;\s#]*",
    re.IGNORECASE,
)


def _is_sensitive_key(key: Any) -> bool:
    return isinstance(key, str) and key.lower() in _SENSITIVE_KEYS


def _scrub_value(value: Any) -> Any:
    """Recursively redact values under sensitive keys."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_sensitive_key(k) else _scrub_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def scrub_url(url: str) -> str:
    """Drop the whole query string — tokens ride there more often than not."""
    return url.split("?", 1)[0] if isinstance(url, str) else url


def scrub_event(event: dict[str, Any], hint: Any = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("headers", None)
        request.pop("env", None)
        request.pop("query_string", None)
        if "url" in request:
            request["url"] = scrub_url(request["url"])
    if "extra" in event:
        event["extra"] = _scrub_value(event["extra"])
    if "contexts" in event:
        event["contexts"] = _scrub_value(event["contexts"])
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        breadcrumbs = breadcrumbs.get("values")
    for crumb in breadcrumbs or []:
        if isinstance(crumb, dict):
            if "data" in crumb:
                crumb["data"] = _scrub_value(crumb["data"])
            if isinstance(crumb.get("message"), str):
                crumb["message"] = _TOKEN_QS.sub(r"\1\2=" + REDACTED, crumb["message"])
    user = event.get("user")
    if isinstance(user, dict):
        for k in ("email", "ip_address", "username"):
            user.pop(k, None)
    return event


def before_send(event: dict[str, Any], hint: Any = None) -> dict[str, Any]:
    return scrub_event(event, hint)


def before_send_transaction(event: dict[str, Any], hint: Any = None) -> dict[str, Any]:
    return scrub_event(event, hint)

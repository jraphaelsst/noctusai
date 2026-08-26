"""Connector-local error taxonomy, capability gates, redaction, PII policy.

There is no connector-side HTTP for the vendor API here:
`noctusai_lib.integrations.imovelweb` owns that client and the product
receiver imports the same module, so the map an agent reads and the code
that runs in production are one thing. This module maps that package's
errors into the connector's own type, so every tool's `error` envelope has
one shape regardless of which layer raised it.

The two non-obvious jobs live here too, because both are policy rather
than plumbing:

- **`redact`** — a tool result goes straight into a model's context
  window. This connector holds THREE secrets (the OAuth `client_secret`,
  the bearer token it exchanges for, and the callback header value we
  registered), and all three have to be stripped from every result, not
  just from error messages.
- **`strip_pii`** — `identificationId` is a CPF. LGPD minimization says
  we do not store it (`KB § INTEGRATIONS/imovelweb.md § 9`), and the same
  reasoning applies harder to a transcript: a CPF pasted into a context
  window is a CPF in a log we do not control.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from _kit.errors import confirmation_required_message
from noctusai_lib.integrations.imovelweb import (
    ImovelWebConfigError,
    ImovelWebError,
    redact_secrets,
)

#: Keys whose VALUE is a national identifier, in every spelling the vendor
#: uses across its five callback languages plus the pull API.
PII_KEYS = frozenset({
    "identificationId", "identificacionId", "identificationid",
    "cpf", "dni", "documento", "numeroDocumento",
})

#: Replaces a PII value. Keeping the key is deliberate — dropping it would
#: hide the fact that the vendor sent one, which is itself the finding.
PII_PLACEHOLDER = "***PII-REDACTED***"


class ImovelWebApiError(Exception):
    """Connector-side error carrying an HTTP-ish `status`.

    424 = not configured · 412 = confirmation required · 502 = upstream
    unreachable/undecodable · anything else = the vendor's own status,
    passed through so a 429 stays a 429 and a caller can back off.
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ConfirmationRequiredError(ImovelWebApiError):
    """A write tool was called without `confirm=true`.

    Raised BEFORE any side effect — the gate is the point, so it must be
    the first thing the handler evaluates, ahead of even reading settings.
    """

    def __init__(self, action: str, effect: str = "") -> None:
        super().__init__(
            confirmation_required_message(action, effect, noun="write action"),
            status=412,
        )


def require_api_configured(settings) -> None:
    """Gate every credentialed OpenNavent call."""
    if not settings.api_configured:
        missing = [
            name
            for name, value in (
                ("IMOVELWEB_CLIENT_ID", settings.client_id),
                ("IMOVELWEB_CLIENT_SECRET", settings.client_secret),
            )
            if not value
        ]
        if settings.base_url is None:
            missing.append(f"a known region (IMOVELWEB_REGION={settings.region!r})")
        raise ImovelWebApiError(
            "The ImovelWeb / OpenNavent API is not configured — missing "
            f"{', '.join(missing)}. Set them in mcp/imovelweb/.env. "
            "Credentials are issued by integracao@imovelweb.com.br: one "
            "request for sandbox, a second for production after testing.",
            status=424,
        )


def require_receiver_configured(settings) -> None:
    """Gate `imovelweb.webhook.simulate`, which POSTs at OUR receiver."""
    if not settings.receiver_configured:
        raise ImovelWebApiError(
            "The ImovelWeb receiver is not configured — set "
            "IMOVELWEB_RECEIVER_URL and IMOVELWEB_WEBHOOK_SECRET in "
            "mcp/imovelweb/.env. Unlike Grupo OLX, WE choose this secret; "
            "it must match what the product receiver validates, or the "
            "simulation proves nothing.",
            status=424,
        )


def map_seed_error(exc: BaseException) -> ImovelWebApiError:
    """Seed error → connector error, preserving status and message.

    Subclass before parent: `ImovelWebConfigError` IS an `ImovelWebError`,
    and collapsing them erases the difference between "we are not set up"
    (fixable by configuration, 424) and "the vendor said no" (theirs,
    maybe transient, 502-or-their-status). An operator who has once seen
    the first reported as the second stops trusting the status line.
    """
    if isinstance(exc, ImovelWebApiError):
        return exc
    if isinstance(exc, ImovelWebConfigError):
        return ImovelWebApiError(exc.message, status=424)
    if isinstance(exc, ImovelWebError):
        return ImovelWebApiError(exc.message, status=exc.status or 502)
    return ImovelWebApiError(str(exc), status=502)


def redact(value: Any, settings, client: Any = None) -> Any:
    """Strip every known secret out of an arbitrary result structure.

    Serialize → replace → parse, rather than walking the tree, so a secret
    embedded mid-string (`"failed with client_secret=abc"`) is caught as
    well as one sitting in its own field.

    `client.redact` is consulted when present because only the client
    knows the CURRENT bearer token; the Fake deliberately does not expose
    it (`tests/integrations/imovelweb/test_adapter.py` pins that the Fake
    matches the Real surface except for `redact`), hence the probe rather
    than an assumption.

    A serialization failure RAISES. Returning the value unredacted on the
    error path would leak exactly what this function exists to prevent,
    and doing it silently would be the worst version of that.
    """
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        raise ImovelWebApiError(
            f"refusing to return a result that could not be serialized for "
            f"redaction: {type(exc).__name__}. The value is withheld rather "
            "than surfaced unredacted.",
            status=500,
        ) from exc

    if client is not None and hasattr(client, "redact"):
        text = client.redact(text) or text
    text = redact_secrets(text, *settings.known_secrets) or text
    return json.loads(text)


def strip_pii(value: Any) -> tuple[Any, int]:
    """Replace every national-identifier value; return `(value, count)`.

    The count is returned rather than logged so the tool can say
    `pii_redacted: 2` in its own result — an operator needs to know a CPF
    arrived even when they must not see it.
    """
    removed = 0

    def _walk(node: Any) -> Any:
        nonlocal removed
        if isinstance(node, dict):
            out = {}
            for key, item in node.items():
                if key in PII_KEYS and item not in (None, ""):
                    removed += 1
                    out[key] = PII_PLACEHOLDER
                else:
                    out[key] = _walk(item)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(value), removed


__all__ = [
    "ConfirmationRequiredError",
    "ImovelWebApiError",
    "PII_KEYS",
    "PII_PLACEHOLDER",
    "map_seed_error",
    "redact",
    "require_api_configured",
    "require_receiver_configured",
    "strip_pii",
]

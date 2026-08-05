"""Omie typed errors + fault classification.

Omie does not use HTTP status codes to describe *what* went wrong — it
answers a failed call with a SOAP-flavoured JSON body::

    {"faultstring": "A chave de acesso não está preenchida ou não é válida.",
     "faultcode": "SOAP-ENV:Server"}

…and a status that is frequently 500/403 regardless of the actual cause.
Verified live (2026-08-05): an invalid `app_key` answers **HTTP 403** with
exactly that `faultstring`.

So the meaning lives in the Portuguese `faultstring`, and the host LLM
cannot branch on it reliably. This module does that classification once,
here, and hands back a typed subclass with a stable `error_class` name —
the whole point of the connector-MCP typed-error contract.

One classification is load-bearing beyond ergonomics: Omie signals
"you paged past the end" as a *fault*, not an empty list. `OmieEmptyPage`
exists so the paginator can stop cleanly instead of reporting a failure
for a perfectly normal end-of-data — while never silently swallowing a
real error.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from _kit.errors import confirmation_required_message


class OmieApiError(Exception):
    """Base Omie error. `status` feeds the `_kit.errors.typed_error` contract."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        faultstring: Optional[str] = None,
        faultcode: Optional[str] = None,
    ):
        super().__init__(message)
        self.status = status
        self.faultstring = faultstring
        self.faultcode = faultcode


class OmieConfigError(OmieApiError):
    """No/!bad environment credentials. 424 — the connector cannot even try."""

    def __init__(self, message: str, *, status: int = 424, **kw):
        super().__init__(message, status=status, **kw)


class OmieAuthError(OmieApiError):
    """app_key/app_secret rejected, or the key lacks access to the resource."""


class OmieNotFound(OmieApiError):
    """The requested record does not exist in this environment."""


class OmieValidationError(OmieApiError):
    """Omie rejected the payload (missing/invalid field, business rule)."""


class OmieRateLimited(OmieApiError):
    """Rate limit or the 30-min consecutive-failure block (HTTP 425)."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kw):
        super().__init__(message, **kw)
        self.retry_after = retry_after


class OmieEmptyPage(OmieApiError):
    """'Não existem registros para a página N' — end of data, not a failure.

    Raised so callers make an explicit decision; `paginate` treats it as a
    clean stop, single calls surface it as a typed (non-fatal) result.
    """


class OmieReadOnlyEnvironment(OmieApiError):
    """A mutating call was aimed at an environment pinned `readonly`."""

    def __init__(self, message: str, **kw):
        super().__init__(message, status=403, **kw)


class ConfirmationRequiredError(OmieApiError):
    """Confirm-then-execute guard for writes (the house connector idiom)."""

    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            confirmation_required_message(action, effect, noun="write action"),
            status=412,
        )


# --- fault classification ---------------------------------------------------
# Matched against the lower-cased faultstring. Order matters: first hit wins.
_FAULT_RULES: tuple[tuple[re.Pattern, type, Optional[int]], ...] = (
    (re.compile(r"n[aã]o existem registros para a p[aá]gina"), OmieEmptyPage, 404),
    (re.compile(r"chave de acesso|app_?key|app_?secret|n[aã]o autorizado|acesso negado"), OmieAuthError, 401),
    (re.compile(r"too many requests|excedeu.*(limite|requisi)|consumo.*limite"), OmieRateLimited, 429),
    (re.compile(r"n[aã]o (cadastrad|encontrad|localizad)|inexistente|n[aã]o existe"), OmieNotFound, 404),
    (re.compile(r"obrigat[oó]ri|inv[aá]lid|n[aã]o informad|j[aá] (existe|cadastrad)|duplicad|erro de valida"), OmieValidationError, 422),
)


def classify_fault(
    faultstring: str,
    *,
    http_status: Optional[int] = None,
    faultcode: Optional[str] = None,
    tag: str = "",
) -> OmieApiError:
    """Map an Omie `faultstring` onto a typed error.

    `http_status` is kept as the fallback status when no rule matches, so
    an unrecognised fault is still reported honestly (never re-labelled as
    a success, never flattened to a generic 500).
    """
    fs = (faultstring or "").strip()
    low = fs.lower()
    if http_status == 425:
        return OmieRateLimited(
            f"{tag} — blocked by Omie for ~30 min after repeated failures "
            f"(HTTP 425): {fs}",
            status=425,
            retry_after=1800.0,
            faultstring=fs,
            faultcode=faultcode,
        )
    for pattern, cls, status in _FAULT_RULES:
        if pattern.search(low):
            return cls(
                f"{tag} — {fs}" if tag else fs,
                status=status or http_status,
                faultstring=fs,
                faultcode=faultcode,
            )
    return OmieApiError(
        f"{tag} — {fs}" if tag else fs,
        status=http_status,
        faultstring=fs,
        faultcode=faultcode,
    )


def fault_from_body(body: str, *, http_status: Optional[int], tag: str) -> Optional[OmieApiError]:
    """Build a typed error from a response body iff it carries an Omie fault.

    Returns `None` when the body is not an Omie fault envelope, so the
    caller falls through to its default handling (the `_kit.transport`
    `on_http_error` hook contract).
    """
    if not body:
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "faultstring" not in data:
        return None
    return classify_fault(
        str(data.get("faultstring") or ""),
        http_status=http_status,
        faultcode=data.get("faultcode"),
        tag=tag,
    )


__all__ = [
    "OmieApiError",
    "OmieAuthError",
    "OmieConfigError",
    "OmieEmptyPage",
    "OmieNotFound",
    "OmieRateLimited",
    "OmieReadOnlyEnvironment",
    "OmieValidationError",
    "ConfirmationRequiredError",
    "classify_fault",
    "fault_from_body",
]

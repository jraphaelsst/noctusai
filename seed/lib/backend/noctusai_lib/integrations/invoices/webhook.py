"""Invoice webhook parsing - shared by Fake and Focus.

Auth: the per-org token arrives in a HEADER (never the query string), compared
in constant time, FAIL-CLOSED (an unset/empty expected token rejects every
request). The body is parsed only after auth and is NEVER authoritative: the
handler re-reads `provider.get(kind, ref)` (contract 2.6).

Focus delivers the same JSON as the consult endpoint (one document per POST);
the event type is not in the body, so `kind` is inferred: `chave_nfe` => NF-e,
`cnpj_prestador` => NFS-e (municipal or national - both are `InvoiceKind.NFSE`).
"""
from __future__ import annotations

import hmac
import json
from typing import Callable, Mapping, Optional

from .errors import InvoiceProviderError, InvoiceWebhookAuthError
from .refs import _REF
from .scrub import scrub
from .types import InvoiceEvent, InvoiceKind, InvoiceStatus

#: Header the Focus gatilho is registered with (`authorization_header`).
WEBHOOK_TOKEN_HEADER = "X-Invoice-Webhook-Token"


def _REF_OK(value: str) -> bool:
    return bool(_REF.match(value))


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for k, v in headers.items():
        if str(k).lower() == wanted:
            return str(v)
    return ""


def verify_webhook_token(
    provider: str, headers: Mapping[str, str], *, token: Optional[str]
) -> None:
    """Raise `InvoiceWebhookAuthError` unless the header token matches."""
    if not token:  # fail-closed: unset secret never authenticates
        raise InvoiceWebhookAuthError(provider)
    supplied = _header(headers, WEBHOOK_TOKEN_HEADER)
    ok = hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))
    if not supplied or not ok:
        raise InvoiceWebhookAuthError(provider)


def parse_webhook_event(
    provider: str,
    headers: Mapping[str, str],
    body: bytes,
    *,
    token: Optional[str],
    map_status: Callable[[str], Optional[InvoiceStatus]],
) -> InvoiceEvent:
    verify_webhook_token(provider, headers, token=token)
    data: object = None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        data = None  # a JSON error message quotes body text: never chain it
    if not isinstance(data, dict) or not data.get("ref"):
        raise InvoiceProviderError(provider, "webhook invalido", code="webhook_invalido")
    if not _REF_OK(str(data["ref"])):
        raise InvoiceProviderError(provider, "webhook invalido", code="webhook_invalido")
    kind: Optional[InvoiceKind] = None
    if "chave_nfe" in data or "cnpj_emitente" in data:
        kind = InvoiceKind.NFE
    elif "cnpj_prestador" in data:
        kind = InvoiceKind.NFSE
    hint = map_status(str(data.get("status", ""))) if data.get("status") is not None else None
    return InvoiceEvent(
        ref=str(data["ref"]),
        kind=kind,
        status_hint=hint,
        raw=scrub(data, extra_secrets=(token,)),
    )

"""Certificate bytes, password and tokens never reach a log record, an
exception (message, args, cause chain) or `raw` - across every failure path."""
import base64
import logging

import httpx
import pytest

from noctusai_lib.integrations.invoices import (
    FocusNFeInvoiceProvider,
    InvoiceKind,
    InvoiceProviderError,
)
from tests.integrations.invoices.conftest import (
    ACCOUNT_TOKEN,
    COMPANY_BODY_NACIONAL,
    COMPANY_TOKEN,
    PFX_PASSWORD,
    sample_request,
)
from noctusai_lib.integrations.rate_limit import VirtualClock


def _secrets(pfx: bytes) -> list[str]:
    b64 = base64.b64encode(pfx).decode()
    basic = [base64.b64encode(f"{t}:".encode()).decode() for t in (ACCOUNT_TOKEN, COMPANY_TOKEN)]
    # any 32+ char window of the pfx base64 counts as a leak (a truncated echo is still one)
    slices = [b64[i : i + 32] for i in range(0, len(b64) - 32, 16)]
    return [ACCOUNT_TOKEN, COMPANY_TOKEN, PFX_PASSWORD, b64, pfx.hex(), *basic, *slices]


def _exc_walk(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _exception_text(exc: BaseException) -> str:
    parts, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(f"{exc!s} {exc!r} {exc.args!r} {getattr(exc, 'reasons', '')!r}")
        exc = exc.__cause__ or exc.__context__  # walk BOTH links, suppress flag or not
    return " ".join(parts)


def _echoing_transport(kind: str):
    """A hostile provider/transport that echoes secrets into every failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        echo = request.headers.get("Authorization", "") + request.content.decode(errors="ignore")
        if kind == "timeout":
            raise httpx.ReadTimeout(f"timeout {echo}", request=request)
        if kind == "network":
            raise httpx.ConnectError(f"boom {echo}", request=request)
        if kind == "500":
            return httpx.Response(500, text=echo)
        if kind == "400":
            return httpx.Response(400, json={"codigo": "requisicao_invalida", "mensagem": echo})
        if kind == "decoding":
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=b"not-gzip" + echo.encode())
        if kind == "echo400":
            return httpx.Response(
                400, json={"codigo": "requisicao_invalida", "mensagem": echo, "erros": [{"mensagem": echo}]}
            )
        if kind == "garbage":
            return httpx.Response(200, text=echo)
        return httpx.Response(200, json=COMPANY_BODY_NACIONAL)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("kind", ["timeout", "network", "500", "400", "garbage", "decoding", "echo400"])
def test_no_secret_in_logs_or_exceptions_on_any_failure(kind, pfx_bundle, caplog):
    pfx, _ = pfx_bundle
    focus = FocusNFeInvoiceProvider(
        account_token=ACCOUNT_TOKEN, default_company_token=COMPANY_TOKEN,
        transport=_echoing_transport(kind), clock=VirtualClock(),
    )
    caplog.set_level(logging.DEBUG)
    calls = [
        lambda: focus.upload_certificate("123", pfx=pfx, password=PFX_PASSWORD),
        lambda: focus.issue(sample_request(InvoiceKind.NFE)),
        lambda: focus.get(InvoiceKind.NFE, "r"),
        lambda: focus.verify_credentials(),
    ]
    raised = 0
    for call in calls:
        try:
            call()
        except InvoiceProviderError as exc:
            raised += 1
            text = _exception_text(exc)
            for secret in _secrets(pfx):
                assert secret not in text
            # no raw httpx exception (it carries .request.headers) anywhere in the chain
            assert not any(isinstance(e, httpx.HTTPError) for e in _exc_walk(exc))
    assert raised >= 2
    logged = " ".join(r.getMessage() + repr(r.args) + str(r.exc_text) for r in caplog.records)
    for secret in _secrets(pfx):
        assert secret not in logged


def test_wrong_password_exception_carries_no_password_or_bytes(pfx_bundle):
    pfx, _ = pfx_bundle
    focus = FocusNFeInvoiceProvider(account_token=ACCOUNT_TOKEN, transport=_echoing_transport("ok"))
    with pytest.raises(InvoiceProviderError) as exc:
        focus.upload_certificate("123", pfx=pfx, password="the-wrong-password")
    text = _exception_text(exc.value)
    assert "the-wrong-password" not in text and base64.b64encode(pfx).decode() not in text


def test_provider_repr_hides_tokens():
    focus = FocusNFeInvoiceProvider(account_token=ACCOUNT_TOKEN, default_company_token=COMPANY_TOKEN)
    assert ACCOUNT_TOKEN not in repr(focus) and COMPANY_TOKEN not in repr(focus)

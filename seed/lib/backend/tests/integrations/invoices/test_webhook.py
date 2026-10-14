import json

import pytest

from noctusai_lib.integrations.invoices import (
    FakeInvoiceProvider,
    FocusNFeInvoiceProvider,
    InvoiceKind,
    InvoiceProviderError,
    InvoiceStatus,
    InvoiceWebhookAuthError,
    WEBHOOK_TOKEN_HEADER,
)

TOKEN = "wh-secret-123456"
NFSE_BODY = json.dumps({"cnpj_prestador": "1", "ref": "r1", "status": "autorizado"}).encode()
NFE_BODY = json.dumps({"cnpj_emitente": "1", "ref": "r2", "status": "processando_autorizacao"}).encode()


@pytest.fixture(params=["focus", "fake"])
def provider(request):
    if request.param == "fake":
        return FakeInvoiceProvider()
    return FocusNFeInvoiceProvider(account_token="a")


def _h(value=TOKEN, name=WEBHOOK_TOKEN_HEADER):
    return {name: value}


def test_valid_token_header_case_insensitive(provider):
    body = NFSE_BODY if provider.name == "focusnfe" else json.dumps({"ref": "r1", "status": "authorized"}).encode()
    event = provider.parse_webhook(_h(name=WEBHOOK_TOKEN_HEADER.lower()), body, token=TOKEN)
    assert event.ref == "r1" and event.status_hint is InvoiceStatus.AUTHORIZED


def test_kind_inferred_and_hint_only():
    focus = FocusNFeInvoiceProvider(account_token="a")
    e = focus.parse_webhook(_h(), NFE_BODY, token=TOKEN)
    assert e.kind is InvoiceKind.NFE and e.status_hint is InvoiceStatus.PROCESSING
    assert focus.parse_webhook(_h(), NFSE_BODY, token=TOKEN).kind is InvoiceKind.NFSE


@pytest.mark.parametrize("supplied", ["", "wrong", TOKEN + "x", TOKEN[:-1]])
def test_wrong_or_missing_token_rejected(provider, supplied):
    with pytest.raises(InvoiceWebhookAuthError):
        provider.parse_webhook(_h(supplied), NFSE_BODY, token=TOKEN)


@pytest.mark.parametrize("expected", [None, ""])
def test_fail_closed_when_no_token_configured(provider, expected):
    with pytest.raises(InvoiceWebhookAuthError):
        provider.parse_webhook(_h(""), NFSE_BODY, token=expected)
    with pytest.raises(InvoiceWebhookAuthError):
        provider.parse_webhook(_h("anything"), NFSE_BODY, token=expected)


def test_token_in_query_string_style_is_not_accepted(provider):
    with pytest.raises(InvoiceWebhookAuthError):
        provider.parse_webhook({}, NFSE_BODY, token=TOKEN)


def test_bad_body_after_auth_is_generic_error(provider):
    for body in (b"not json", b"[]", b'{"status":"autorizado"}'):
        with pytest.raises(InvoiceProviderError) as exc:
            provider.parse_webhook(_h(), body, token=TOKEN)
        assert exc.value.code == "webhook_invalido"


def test_unknown_status_hint_is_none_not_error():
    focus = FocusNFeInvoiceProvider(account_token="a")
    body = json.dumps({"cnpj_prestador": "1", "ref": "r", "status": "novo_status"}).encode()
    assert focus.parse_webhook(_h(), body, token=TOKEN).status_hint is None


def test_raw_is_scrubbed_of_tokens():
    focus = FocusNFeInvoiceProvider(account_token="a")
    body = json.dumps({"cnpj_prestador": "1", "ref": "r", "status": "autorizado", "token": "leak", "nota": TOKEN}).encode()
    raw = focus.parse_webhook(_h(), body, token=TOKEN).raw
    assert "leak" not in json.dumps(raw) and TOKEN not in json.dumps(raw)

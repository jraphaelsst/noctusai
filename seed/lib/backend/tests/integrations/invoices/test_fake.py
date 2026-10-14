import pytest

from noctusai_lib.integrations.invoices import (
    CertificateInfo,
    CompanyRequest,
    FakeInvoiceProvider,
    InvoiceKind,
    InvoiceNotFound,
    InvoiceProvider,
    InvoiceProviderError,
    InvoiceStatus,
    NfseMode,
)
from tests.integrations.invoices.conftest import CNPJ, PFX_PASSWORD, sample_request

REASON = "Pedido cancelado a pedido do cliente"


def _ready(fake, *, nfe=True, mode=NfseMode.NACIONAL, pfx=None):
    company = fake.ensure_company(CompanyRequest(cnpj=CNPJ, legal_name="Loja", nfse_mode=mode, enable_nfe=nfe))
    if pfx:
        fake.upload_certificate(company.ref, pfx=pfx, password=PFX_PASSWORD)
    return company


def test_satisfies_protocol():
    assert isinstance(FakeInvoiceProvider(), InvoiceProvider)


def test_round_trip_company_cert_issue_authorized_cancel(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake, pfx=pfx_bundle[0])
    assert company.nfse_mode is NfseMode.NACIONAL
    info = fake.upload_certificate(company.ref, pfx=pfx_bundle[0], password=PFX_PASSWORD)
    assert info.subject_cnpj == CNPJ

    result = fake.issue(sample_request(company_ref=company.ref))
    assert result.status is InvoiceStatus.AUTHORIZED and result.number and result.pdf_url
    assert fake.endpoints["org-ord1-nfse-1"] == "/v2/nfsen"
    assert fake.get(InvoiceKind.NFSE, "org-ord1-nfse-1").status is InvoiceStatus.AUTHORIZED
    assert fake.fetch_document(result.pdf_url).startswith(b"%PDF")

    cancelled = fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason=REASON)
    assert cancelled.status is InvoiceStatus.CANCELLED
    assert fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason=REASON).status is InvoiceStatus.CANCELLED


def test_issue_is_idempotent_on_ref(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake, pfx=pfx_bundle[0])
    a = fake.issue(sample_request(company_ref=company.ref))
    b = fake.issue(sample_request(company_ref=company.ref))
    assert a == b and a.number == b.number


def test_scripted_rejection(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake, pfx=pfx_bundle[0])
    fake.script_rejection("org-ord1-nfse-1", ["Regime Especial de Tributacao ausente"])
    result = fake.issue(sample_request(company_ref=company.ref))
    assert result.status is InvoiceStatus.REJECTED
    assert result.rejection_reasons == ["Regime Especial de Tributacao ausente"]
    with pytest.raises(InvoiceProviderError) as exc:
        fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason=REASON)
    assert exc.value.code == "nao_autorizada"


def test_async_authorization_then_cancel_refusal(pfx_bundle):
    fake = FakeInvoiceProvider(auto_authorize=False)
    company = _ready(fake, pfx=pfx_bundle[0])
    assert fake.issue(sample_request(company_ref=company.ref)).status is InvoiceStatus.PROCESSING
    with pytest.raises(InvoiceProviderError):
        fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason=REASON)
    fake.authorize(InvoiceKind.NFSE, "org-ord1-nfse-1")
    fake.script_cancel_refusal("org-ord1-nfse-1", ["fora do prazo"])
    with pytest.raises(InvoiceProviderError) as exc:
        fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason=REASON)
    assert exc.value.code == "cancel_refused" and exc.value.reasons == ["fora do prazo"]


def test_set_nfse_mode_switches_endpoint(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake, mode=NfseMode.MUNICIPAL, pfx=pfx_bundle[0])
    fake.issue(sample_request(ref="r-muni", company_ref=company.ref))
    assert fake.endpoints["r-muni"] == "/v2/nfse"
    assert fake.set_nfse_mode(company.ref, NfseMode.NACIONAL).nfse_mode is NfseMode.NACIONAL
    fake.issue(sample_request(ref="r-nac", company_ref=company.ref))
    assert fake.endpoints["r-nac"] == "/v2/nfsen"


def test_certificate_required_and_not_found_and_short_reason(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake)
    with pytest.raises(InvoiceProviderError) as exc:
        fake.issue(sample_request(company_ref=company.ref))
    assert exc.value.code == "certificado_ausente"
    with pytest.raises(InvoiceNotFound):
        fake.get(InvoiceKind.NFSE, "nope")
    fake.script_certificate(CertificateInfo(valid_until=pfx_bundle[1], subject_cnpj=CNPJ))
    fake.upload_certificate(company.ref, pfx=b"ignored", password="x")
    fake.issue(sample_request(company_ref=company.ref))
    with pytest.raises(InvoiceProviderError) as exc:
        fake.cancel(InvoiceKind.NFSE, "org-ord1-nfse-1", reason="curto")
    assert exc.value.code == "justificativa_invalida"


def test_cnpj_change_drops_certificate(pfx_bundle):
    fake = FakeInvoiceProvider()
    company = _ready(fake, pfx=pfx_bundle[0])
    fake.ensure_company(CompanyRequest(cnpj="99999999000199", legal_name="Loja", company_ref=company.ref))
    with pytest.raises(InvoiceProviderError):
        fake.issue(sample_request(company_ref=company.ref))

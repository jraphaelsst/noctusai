import pytest

from noctusai_lib.integrations.invoices import (
    CompanyTokenStore,
    InvoiceEnvironment,
    InvoiceProviderError,
    NfseMode,
    ProviderCompany,
)
from noctusai_lib.security.token_store import FakeCredentialStore

ORG = "org-1"


def company(cnpj="12345678000190", token="tok-1"):
    return ProviderCompany(ref="123", cnpj=cnpj, nfse_mode=NfseMode.NACIONAL, nfe_enabled=True, nfse_enabled=True, company_token=token)


def test_round_trip_and_resolver():
    store = CompanyTokenStore(FakeCredentialStore(), environment=InvoiceEnvironment.HOMOLOGACAO)
    assert store.put(ORG, company()) is False
    assert store.get(ORG, "123") == "tok-1"
    assert store.resolver_for(ORG)("123") == "tok-1"
    assert store.get("other-org", "123") is None


def test_cnpj_change_rotates():
    store = CompanyTokenStore(FakeCredentialStore(), environment=InvoiceEnvironment.HOMOLOGACAO)
    store.put(ORG, company())
    assert store.put(ORG, company(cnpj="99999999000199", token="tok-2")) is True
    assert store.get(ORG, "123") == "tok-2"


def test_environment_mismatch_refused():
    backing = FakeCredentialStore()
    CompanyTokenStore(backing, environment=InvoiceEnvironment.HOMOLOGACAO).put(ORG, company())
    prod = CompanyTokenStore(backing, environment=InvoiceEnvironment.PRODUCAO)
    with pytest.raises(InvoiceProviderError) as exc:
        prod.get(ORG, "123")
    assert exc.value.code == "token_environment_mismatch"


def test_missing_token_and_delete():
    store = CompanyTokenStore(FakeCredentialStore(), environment=InvoiceEnvironment.HOMOLOGACAO)
    with pytest.raises(InvoiceProviderError):
        store.put(ORG, company(token=None))
    store.put(ORG, company())
    assert store.delete(ORG, "123") is True and store.get(ORG, "123") is None


def test_repr_hides_company_token():
    assert "tok-1" not in repr(company())

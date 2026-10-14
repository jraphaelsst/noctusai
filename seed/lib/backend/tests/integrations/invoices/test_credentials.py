import dataclasses

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


def store_for(backing=None, env=InvoiceEnvironment.HOMOLOGACAO):
    return CompanyTokenStore(backing or FakeCredentialStore(), environment=env)


def test_sink_round_trip_and_resolver():
    store = store_for()
    store.sink_for(ORG)("123", "12345678000190", "tok-1")
    assert store.resolver_for(ORG)("123") == "tok-1"
    assert store.resolver_for("other-org")("123") is None


def test_no_public_getter():
    assert not hasattr(store_for(), "get")


def test_cnpj_change_rotates():
    store = store_for()
    store.put(ORG, "123", "12345678000190", "tok-1")
    assert store.put(ORG, "123", "99999999000199", "tok-2") is True
    assert store.resolver_for(ORG)("123") == "tok-2"


def test_environment_mismatch_refused():
    backing = FakeCredentialStore()
    store_for(backing).put(ORG, "123", "12345678000190", "tok-1")
    with pytest.raises(InvoiceProviderError) as exc:
        store_for(backing, InvoiceEnvironment.PRODUCAO).resolver_for(ORG)("123")
    assert exc.value.code == "token_environment_mismatch"


def test_missing_token_and_delete():
    store = store_for()
    with pytest.raises(InvoiceProviderError):
        store.put(ORG, "123", "1", None)
    store.put(ORG, "123", "1", "tok-1")
    assert store.delete(ORG, "123") is True and store.resolver_for(ORG)("123") is None


def test_provider_company_has_no_token_field_to_serialize():
    names = {f.name for f in dataclasses.fields(ProviderCompany)}
    assert not any("token" in n for n in names)
    company = ProviderCompany(ref="1", cnpj="2", nfse_mode=NfseMode.NACIONAL, nfe_enabled=True, nfse_enabled=True)
    assert "token" not in str(dataclasses.asdict(company)).lower()

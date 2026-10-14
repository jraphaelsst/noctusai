import pytest

from noctusai_lib.integrations.invoices import InvoiceCertificateError, inspect_pkcs12
from tests.integrations.invoices.conftest import CNPJ, PFX_PASSWORD, build_pfx


def test_reads_cnpj_from_icp_brasil_san_and_expiry(pfx_bundle):
    pfx, not_after = pfx_bundle
    info = inspect_pkcs12(pfx, PFX_PASSWORD)
    assert info.subject_cnpj == CNPJ
    assert info.valid_until == not_after


def test_falls_back_to_cn_suffix_when_no_san_oid():
    pfx, _ = build_pfx(cnpj=None, cn_suffix="98765432000110")
    assert inspect_pkcs12(pfx, PFX_PASSWORD).subject_cnpj == "98765432000110"


def test_no_cnpj_anywhere_is_none_not_error():
    pfx, _ = build_pfx(cnpj=None)
    assert inspect_pkcs12(pfx, PFX_PASSWORD).subject_cnpj is None


def test_wrong_password_and_garbage_are_the_same_generic_error(pfx_bundle):
    pfx, _ = pfx_bundle
    errors = []
    for blob, pw in ((pfx, "wrong-password-123"), (b"not a pkcs12 file", PFX_PASSWORD)):
        with pytest.raises(InvoiceCertificateError) as exc:
            inspect_pkcs12(blob, pw)
        errors.append((exc.value.code, str(exc.value), exc.value.args))
        assert pw not in str(exc.value)
        assert exc.value.__cause__ is None
    assert errors[0] == errors[1]


def test_san_oid_wins_over_cn_when_present():
    pfx, _ = build_pfx(cnpj=CNPJ, cn_suffix="98765432000110")
    assert inspect_pkcs12(pfx, PFX_PASSWORD).subject_cnpj == CNPJ


def test_expected_cnpj_mismatch_and_missing_raise(pfx_bundle):
    from noctusai_lib.integrations.invoices.errors import InvoiceCertificateCnpjMismatch

    pfx, _ = pfx_bundle
    assert inspect_pkcs12(pfx, PFX_PASSWORD, expected_cnpj="12.345.678/0001-90").subject_cnpj == CNPJ
    with pytest.raises(InvoiceCertificateCnpjMismatch):
        inspect_pkcs12(pfx, PFX_PASSWORD, expected_cnpj="99999999000199")
    nopfx, _ = build_pfx(cnpj=None)
    with pytest.raises(InvoiceCertificateCnpjMismatch):
        inspect_pkcs12(nopfx, PFX_PASSWORD, expected_cnpj=CNPJ)


def test_size_password_limits_and_private_key_required(pfx_bundle):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509

    pfx, _ = pfx_bundle
    with pytest.raises(InvoiceCertificateError):
        inspect_pkcs12(b"x" * (64 * 1024 + 1), PFX_PASSWORD)
    with pytest.raises(InvoiceCertificateError):
        inspect_pkcs12(pfx, "p" * 129)
    _k, cert, _ = pkcs12.load_key_and_certificates(pfx, PFX_PASSWORD.encode())
    cert_only = pkcs12.serialize_key_and_certificates(b"t", None, cert, None, serialization.BestAvailableEncryption(b"pw"))
    with pytest.raises(InvoiceCertificateError):
        inspect_pkcs12(cert_only, "pw")

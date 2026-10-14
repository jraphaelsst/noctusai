"""Local A1 (PKCS#12) inspection - run BEFORE a certificate is forwarded.

Reads the expiry and the e-CNPJ's CNPJ so a store cannot upload a certificate
that belongs to another company. This is MISTAKE-PROOFING, not authentication:
there is NO ICP-Brasil chain validation here (a forged certificate with the right
OID passes); SEFAZ / the prefeitura reject a bad signature at issue time. The `.pfx` bytes and password live only for
this call; nothing is logged, stored or placed in an exception (one generic
`InvoiceCertificateError` covers a corrupt file AND a wrong password).

CNPJ source: ICP-Brasil puts the responsible company's CNPJ in the
SubjectAlternativeName otherName with OID 2.16.76.1.3.3 (PrintableString /
UTF8String of 14 digits). Many issuers ALSO append `:<cnpj>` to the subject CN;
that is used only as a fallback.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from .errors import InvoiceCertificateCnpjMismatch, InvoiceCertificateError
from .types import CertificateInfo

#: ICP-Brasil: CNPJ of the legal entity (e-CNPJ).
OID_ICP_BRASIL_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")

_DIGITS14 = re.compile(r"(?<!\d)(\d{14})(?!\d)")


def _der_string_value(der: bytes) -> str:
    """Decode a DER string TLV (tag, length, content) to text."""
    if len(der) < 2:
        return ""
    length = der[1]
    offset = 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(der[2 : 2 + n], "big")
        offset = 2 + n
    return der[offset : offset + length].decode("utf-8", errors="ignore")


def _cnpj_from_san(cert: x509.Certificate) -> tuple[bool, Optional[str]]:
    """(oid_present, cnpj). When the ICP-Brasil OID is present it is the ONLY source."""
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return False, None
    present = False
    for name in san.value:
        if isinstance(name, x509.OtherName) and name.type_id == OID_ICP_BRASIL_CNPJ:
            present = True
            found = _DIGITS14.search(_der_string_value(name.value))
            if found:
                return True, found.group(1)
    return present, None


def _cnpj_from_subject_cn(cert: x509.Certificate) -> Optional[str]:
    for attr in cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME):
        found = _DIGITS14.search(str(attr.value))
        if found:
            return found.group(1)
    return None


def _not_after(cert: x509.Certificate) -> datetime.datetime:
    getter = getattr(cert, "not_valid_after_utc", None)
    if getter is not None:
        return getter
    return cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)  # pragma: no cover


MAX_PFX_BYTES = 64 * 1024
MAX_PASSWORD_CHARS = 128


def inspect_pkcs12(
    pfx: bytes, password: str, *, expected_cnpj: Optional[str] = None
) -> CertificateInfo:
    """Open `pfx` locally and return expiry + CNPJ.

    Enforces <= 64 KB and a <= 128-char password, and requires a private key.
    With `expected_cnpj`, a certificate whose CNPJ differs (or has none) raises
    `InvoiceCertificateCnpjMismatch` before anything can be forwarded.

    Raises `InvoiceCertificateError` (generic) for an oversized/corrupt file, a
    wrong password, a bundle with no certificate or no private key.
    """
    cert = None
    key = None
    if len(pfx or b"") <= MAX_PFX_BYTES and len(password or "") <= MAX_PASSWORD_CHARS:
        try:
            key, cert, _chain = pkcs12.load_key_and_certificates(
                pfx, password.encode("utf-8") if password else None
            )
        except Exception:  # noqa: BLE001 - deliberately swallowed: see module doc
            cert = None  # raised below, outside the except: no __context__ chain
    if cert is None or key is None:
        raise InvoiceCertificateError()
    oid_present, san_cnpj = _cnpj_from_san(cert)
    cnpj = san_cnpj if oid_present else _cnpj_from_subject_cn(cert)
    if expected_cnpj is not None:
        digits = re.sub(r"\D", "", expected_cnpj)
        if cnpj is None or cnpj != digits:
            raise InvoiceCertificateCnpjMismatch()
    return CertificateInfo(valid_until=_not_after(cert), subject_cnpj=cnpj)

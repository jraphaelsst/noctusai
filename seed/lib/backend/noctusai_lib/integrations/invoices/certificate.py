"""Local A1 (PKCS#12) inspection - run BEFORE a certificate is forwarded.

Reads the expiry and the e-CNPJ's CNPJ so a store cannot upload a certificate
that belongs to another company. The `.pfx` bytes and password live only for
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

from .errors import InvoiceCertificateError
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


def _cnpj_from_san(cert: x509.Certificate) -> Optional[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return None
    for name in san.value:
        if isinstance(name, x509.OtherName) and name.type_id == OID_ICP_BRASIL_CNPJ:
            found = _DIGITS14.search(_der_string_value(name.value))
            if found:
                return found.group(1)
    return None


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


def inspect_pkcs12(pfx: bytes, password: str) -> CertificateInfo:
    """Open `pfx` locally and return expiry + CNPJ.

    Raises `InvoiceCertificateError` (generic) for a corrupt file, a wrong
    password or a bundle with no certificate.
    """
    cert = None
    try:
        _key, cert, _chain = pkcs12.load_key_and_certificates(
            pfx, password.encode("utf-8") if password else None
        )
    except Exception:  # noqa: BLE001 - deliberately swallowed: see module doc
        cert = None  # raised below, outside the except: no __context__ chain
    if cert is None:
        raise InvoiceCertificateError()
    return CertificateInfo(
        valid_until=_not_after(cert),
        subject_cnpj=_cnpj_from_san(cert) or _cnpj_from_subject_cn(cert),
    )

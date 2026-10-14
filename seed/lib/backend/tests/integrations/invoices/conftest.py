"""Shared fixtures: a generated ICP-Brasil-style A1 certificate and a Focus
adapter wired to an `httpx.MockTransport` (no network, no monkeypatching)."""
from __future__ import annotations

import datetime
import json
from typing import Any, Callable, Optional

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from noctusai_lib.integrations.invoices import (
    Address,
    FocusNFeInvoiceProvider,
    InvoiceEnvironment,
    InvoiceItem,
    InvoiceKind,
    InvoiceRequest,
    InvoiceTaker,
)
from noctusai_lib.integrations.invoices.certificate import OID_ICP_BRASIL_CNPJ
from noctusai_lib.integrations.rate_limit import VirtualClock

CNPJ = "12345678000190"
PFX_PASSWORD = "s3nha-do-pfx-XYZ"
ACCOUNT_TOKEN = "acct-token-AAAA1111"
COMPANY_TOKEN = "co-token-BBBB2222"


def _der_utf8(text: str) -> bytes:
    raw = text.encode()
    return bytes([0x0C, len(raw)]) + raw


def build_pfx(
    *,
    cnpj: Optional[str] = CNPJ,
    password: str = PFX_PASSWORD,
    cn_suffix: Optional[str] = None,
    days: int = 365,
) -> tuple[bytes, datetime.datetime]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cn = "LOJA TESTE LTDA" + (f":{cn_suffix}" if cn_suffix else "")
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    not_after = (now + datetime.timedelta(days=days)).replace(microsecond=0)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(not_after)
    )
    if cnpj:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.OtherName(OID_ICP_BRASIL_CNPJ, _der_utf8(cnpj))]
            ),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())
    pfx = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None, serialization.BestAvailableEncryption(password.encode())
    )
    return pfx, not_after


@pytest.fixture(scope="session")
def pfx_bundle() -> tuple[bytes, datetime.datetime]:
    return build_pfx()


class FocusStub:
    """Records requests; `routes` maps (METHOD, path) -> (status, body | callable)."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Any] = {}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"codigo": "nao_encontrado", "mensagem": "Nota fiscal nao encontrada"})
        if callable(route):
            route = route(request)
        status, body = route
        if isinstance(body, (bytes, str)):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]

    @staticmethod
    def body(request: httpx.Request) -> dict[str, Any]:
        return json.loads(request.content or b"{}")


@pytest.fixture
def stub() -> FocusStub:
    return FocusStub()


@pytest.fixture
def make_focus(stub: FocusStub) -> Callable[..., FocusNFeInvoiceProvider]:
    def _make(**kw: Any) -> FocusNFeInvoiceProvider:
        kw.setdefault("account_token", ACCOUNT_TOKEN)
        kw.setdefault("default_company_token", COMPANY_TOKEN)
        kw.setdefault("environment", InvoiceEnvironment.HOMOLOGACAO)
        kw.setdefault("clock", VirtualClock())
        return FocusNFeInvoiceProvider(transport=httpx.MockTransport(stub.handler), **kw)

    return _make


def sample_request(kind: InvoiceKind = InvoiceKind.NFSE, ref: str = "org-ord1-nfse-1", company_ref: str = "123") -> InvoiceRequest:
    item = InvoiceItem(
        description="Consultoria", quantity=1, unit_cents=150000, total_cents=150000,
        service_code="0107", nbs_code="1.0101.10.00", cfop="5102", ncm="49111090",
        c_class_trib="000001",
    )
    return InvoiceRequest(
        ref=ref,
        kind=kind,
        company_ref=company_ref,
        issued_on=datetime.datetime(2026, 10, 13, 12, 0, tzinfo=datetime.timezone.utc),
        competence=datetime.date(2026, 10, 13),
        taker=InvoiceTaker(
            name="Fulano de Tal", doc="12345678909", email="f@x.com",
            address=Address(street="Rua A", number="1", district="Centro", city_ibge="3550308", state="SP", zip_code="01234567"),
        ),
        items=[item],
        total_cents=150000,
        iss_rate_bps=500,
        additional_info="Pedido 1",
    )


COMPANY_BODY_NACIONAL = {
    "id": 123, "cnpj": CNPJ, "inscricao_municipal": "123456", "codigo_municipio": "3550308",
    "regime_tributario": 1, "habilita_nfe": True, "habilita_nfse": False,
    "habilita_nfsen_producao": False, "habilita_nfsen_homologacao": True,
    "token_producao": "tok-prod-SECRET", "token_homologacao": COMPANY_TOKEN,
}
COMPANY_BODY_MUNICIPAL = {
    **COMPANY_BODY_NACIONAL, "habilita_nfse": True, "habilita_nfsen_homologacao": False,
}

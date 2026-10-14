"""In-memory `InvoiceProvider` for tests and local dev - no network, no clock.

Simulates what consumers must handle: company registration with a token,
certificate upload (parsed with the real `inspect_pkcs12`), NFS-e mode
exclusion, async authorization (`auto_authorize=False` + `authorize(ref)`),
scriptable rejection, idempotent issue on `ref`, cancel rules.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional

from .certificate import inspect_pkcs12
from .errors import InvoiceNotFound, InvoiceProviderError
from .refs import validate_ref
from .types import (
    CertificateInfo,
    CompanyRequest,
    InvoiceEvent,
    InvoiceKind,
    InvoiceRequest,
    InvoiceResult,
    InvoiceStatus,
    NfseMode,
    ProviderCompany,
)
from .webhook import parse_webhook_event

_FAKE_STATUS = {
    "processing": InvoiceStatus.PROCESSING,
    "authorized": InvoiceStatus.AUTHORIZED,
    "rejected": InvoiceStatus.REJECTED,
    "cancelled": InvoiceStatus.CANCELLED,
    "error": InvoiceStatus.ERROR,
}


class FakeInvoiceProvider:
    name = "fake"

    def __init__(
        self,
        *,
        auto_authorize: bool = True,
        require_certificate: bool = True,
        token_sink: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        self._token_sink = token_sink
        self._auto_authorize = auto_authorize
        self._require_certificate = require_certificate
        self._companies: dict[str, ProviderCompany] = {}
        self._certs: dict[str, CertificateInfo] = {}
        self._docs: dict[tuple[str, str], InvoiceResult] = {}
        self._reject_refs: dict[str, list[str]] = {}
        self._refuse_cancel: dict[str, list[str]] = {}
        self._scripted_cert: Optional[CertificateInfo] = None
        self._seq = 0
        #: Last endpoint a doc went through (`/v2/nfse` vs `/v2/nfsen`...), for assertions.
        self.endpoints: dict[str, str] = {}

    # ── scripting ────────────────────────────────────────────────────
    def script_rejection(self, ref: str, reasons: list[str]) -> None:
        """The next `issue` for `ref` ends `rejected` with `reasons`."""
        self._reject_refs[ref] = list(reasons)

    def script_cancel_refusal(self, ref: str, reasons: list[str]) -> None:
        """`cancel(ref)` raises as if the provider refused (window passed)."""
        self._refuse_cancel[ref] = list(reasons)

    def script_certificate(self, info: CertificateInfo) -> None:
        """Make `upload_certificate` return `info` instead of parsing the pfx."""
        self._scripted_cert = info

    def authorize(self, kind: InvoiceKind, ref: str) -> InvoiceResult:
        doc = self._doc(kind, ref)
        if doc.status is not InvoiceStatus.PROCESSING:
            return doc
        done = self._authorized(doc)
        self._docs[(kind.value, ref)] = done
        return done

    # ── company / certificate ────────────────────────────────────────
    def verify_credentials(self) -> None:
        return None

    def _company_view(self, ref: str, cnpj: str, mode: NfseMode, nfe: bool) -> ProviderCompany:
        return ProviderCompany(
            ref=ref,
            cnpj=cnpj,
            nfse_mode=mode,
            nfe_enabled=nfe,
            nfse_enabled=True,
        )

    def ensure_company(self, request: CompanyRequest) -> ProviderCompany:
        ref = request.company_ref or f"fake-co-{request.cnpj}"
        old = self._companies.get(ref)
        company = self._company_view(ref, request.cnpj, request.nfse_mode, request.enable_nfe)
        if old is not None and old.cnpj != request.cnpj:
            self._certs.pop(ref, None)  # a CNPJ change invalidates the certificate
        self._companies[ref] = company
        if self._token_sink is not None:
            self._token_sink(ref, request.cnpj, f"fake-token-{ref}")
        return company

    def _company(self, ref: str) -> ProviderCompany:
        try:
            return self._companies[ref]
        except KeyError:
            raise InvoiceProviderError(
                "fake", "empresa nao encontrada", code="empresa_nao_encontrada", status=404
            ) from None

    def upload_certificate(
        self,
        company_ref: str,
        *,
        pfx: bytes,
        password: str,
        expected_cnpj: Optional[str] = None,
    ) -> CertificateInfo:
        validate_ref(company_ref, "fake")
        self._company(company_ref)
        info = self._scripted_cert or inspect_pkcs12(pfx, password, expected_cnpj=expected_cnpj)
        self._certs[company_ref] = info
        return info

    def set_nfse_mode(self, company_ref: str, mode: NfseMode) -> ProviderCompany:
        current = self._company(company_ref)
        updated = self._company_view(current.ref, current.cnpj, mode, current.nfe_enabled)
        self._companies[company_ref] = updated
        return updated

    # ── documents ────────────────────────────────────────────────────
    def _endpoint(self, kind: InvoiceKind, mode: NfseMode) -> str:
        if kind is InvoiceKind.NFE:
            return "/v2/nfe"
        return "/v2/nfsen" if mode is NfseMode.NACIONAL else "/v2/nfse"

    def _authorized(self, base: InvoiceResult) -> InvoiceResult:
        self._seq += 1
        n = self._seq
        ref = base.ref
        return InvoiceResult(
            ref=ref,
            kind=base.kind,
            status=InvoiceStatus.AUTHORIZED,
            number=str(n),
            series="1",
            access_key=(f"FAKE{n:040d}" if base.kind is InvoiceKind.NFE else None),
            verification_code=(f"VER{n:05d}" if base.kind is InvoiceKind.NFSE else None),
            pdf_url=f"https://fake.invoices.test/{ref}.pdf",
            xml_url=f"https://fake.invoices.test/{ref}.xml",
        )

    def issue(self, request: InvoiceRequest) -> InvoiceResult:
        validate_ref(request.ref, "fake")
        key = (request.kind.value, request.ref)
        if key in self._docs:  # idempotent on ref
            return self._docs[key]
        company = self._company(request.company_ref)
        if self._require_certificate and request.company_ref not in self._certs:
            raise InvoiceProviderError(
                "fake", "certificado digital ausente", code="certificado_ausente"
            )
        if request.kind is InvoiceKind.NFE and not company.nfe_enabled:
            raise InvoiceProviderError("fake", "NF-e nao habilitada", code="nfe_nao_habilitada")
        self.endpoints[request.ref] = self._endpoint(request.kind, company.nfse_mode)
        base = InvoiceResult(
            ref=request.ref, kind=request.kind, status=InvoiceStatus.PROCESSING
        )
        if request.ref in self._reject_refs:
            result = InvoiceResult(
                ref=request.ref,
                kind=request.kind,
                status=InvoiceStatus.REJECTED,
                rejection_reasons=self._reject_refs[request.ref],
            )
        elif self._auto_authorize:
            result = self._authorized(base)
        else:
            result = base
        self._docs[key] = result
        return result

    def _doc(self, kind: InvoiceKind, ref: str) -> InvoiceResult:
        try:
            return self._docs[(kind.value, ref)]
        except KeyError:
            raise InvoiceNotFound("fake", ref) from None

    def get(
        self, kind: InvoiceKind, ref: str, *, company_ref: Optional[str] = None
    ) -> InvoiceResult:
        return self._doc(kind, ref)

    def cancel(
        self,
        kind: InvoiceKind,
        ref: str,
        *,
        reason: str,
        company_ref: Optional[str] = None,
    ) -> InvoiceResult:
        doc = self._doc(kind, ref)
        if len((reason or "").strip()) < 15:
            raise InvoiceProviderError(
                "fake", "justificativa invalida", code="justificativa_invalida"
            )
        if doc.status is InvoiceStatus.CANCELLED:
            return doc
        if doc.status is not InvoiceStatus.AUTHORIZED:
            raise InvoiceProviderError("fake", "nota nao autorizada", code="nao_autorizada")
        if ref in self._refuse_cancel:
            raise InvoiceProviderError(
                "fake",
                "cancelamento recusado pelo provedor",
                code="cancel_refused",
                reasons=self._refuse_cancel[ref],
            )
        cancelled = InvoiceResult(
            ref=doc.ref,
            kind=doc.kind,
            status=InvoiceStatus.CANCELLED,
            number=doc.number,
            series=doc.series,
            access_key=doc.access_key,
            verification_code=doc.verification_code,
            pdf_url=doc.pdf_url,
            xml_url=doc.xml_url,
        )
        self._docs[(kind.value, ref)] = cancelled
        return cancelled

    def fetch_document(self, url: str) -> bytes:
        known = {d.pdf_url for d in self._docs.values()} | {d.xml_url for d in self._docs.values()}
        if url not in known:
            raise InvoiceProviderError("fake", "documento nao encontrado", code="not_found", status=404)
        return b"%PDF-fake" if url.endswith(".pdf") else b"<fake-xml/>"

    def parse_webhook(
        self, headers: Mapping[str, str], body: bytes, *, token: Optional[str]
    ) -> InvoiceEvent:
        return parse_webhook_event(
            "fake", headers, body, token=token, map_status=lambda s: _FAKE_STATUS.get(s)
        )

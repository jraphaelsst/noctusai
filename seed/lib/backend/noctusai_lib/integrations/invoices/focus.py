"""Focus NFe adapter (https://doc.focusnfe.com.br) - NF-e, municipal NFS-e,
NFS-e Nacional, companies and A1 certificates.

Lifted from `products/adconnect/backend/app/services/nfe_service.py` with its
defects fixed: lookups/cancels go by OUR `ref` (never the access key); an unknown
provider status raises `InvoiceProviderError(code="unknown_status")` instead of
silently reading `pendente`; a 404 is `InvoiceNotFound`; and raw exceptions /
provider bodies are NEVER logged or put in exception messages (the adconnect
code logged `exc` at lines 293/352/374 - an httpx error can carry the
Authorization header).

VERIFIED against doc.focusnfe.com.br (2026-10-13), see KB INTEGRATIONS/invoices.md:
  hosts + Basic auth (token as user, blank password) · POST/PUT/GET /v2/empresas
  incl. `habilita_nfse` vs `habilita_nfsen_producao|homologacao` mutual exclusion,
  `arquivo_certificado_base64` + `senha_certificado` + `certificado_especifico`,
  response `id`/`token_producao`/`token_homologacao` · POST/GET/DELETE
  /v2/nfe/{ref} · /v2/nfse/{ref} · /v2/nfsen/{ref} (`ref` query param on POST) ·
  statuses autorizado / processando_autorizacao / cancelado / erro_autorizacao /
  erro_cancelamento · response fields (chave_nfe, numero, serie,
  caminho_danfe, caminho_xml_nota_fiscal, url_danfse, codigo_verificacao, erros[]) ·
  NF-e item schema · NFS-e municipal prestador/tomador/servico schema (incl. the
  Reforma Tributaria `ibs_cbs_*` / `codigo_nbs` service fields) · cancel needs a
  15..255 char `justificativa` · webhooks: POST, one document per call, retries
  for up to 48 h, header auth (`authorization` + `authorization_header`).

UNVERIFIED (marked `UNVERIFIED:` below; exercised only by the opt-in live
homologacao test): `denegado` NF-e status · tax-situation defaults for NF-e
items · NFS-e Nacional fields not on the public field list (`razao_social_tomador`,
`email_tomador`, `codigo_opcao_simples_nacional` values, `tributacao_iss` value,
IBS/CBS key names on /nfsen) · `codigo_cancelamento` on /nfsen cancel · whether
`/v2/empresas/{id}` also accepts a CNPJ · whether document `caminho_*` downloads
need auth · `regime_tributario` present on the company GET.
"""
from __future__ import annotations

import base64
import logging
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

import httpx

from noctusai_lib.integrations.rate_limit import Clock, paced_call, parse_retry_after

from .certificate import inspect_pkcs12
from .errors import InvoiceNotFound, InvoiceProviderError
from .scrub import scrub
from .types import (
    CertificateInfo,
    CompanyRequest,
    InvoiceEnvironment,
    InvoiceEvent,
    InvoiceKind,
    InvoiceRequest,
    InvoiceResult,
    InvoiceStatus,
    NfseMode,
    ProviderCompany,
)
from .webhook import parse_webhook_event

logger = logging.getLogger(__name__)

PROVIDER = "focusnfe"
RATE_BUCKET = "focusnfe"

BASE_URLS: dict[InvoiceEnvironment, str] = {
    InvoiceEnvironment.HOMOLOGACAO: "https://homologacao.focusnfe.com.br",
    InvoiceEnvironment.PRODUCAO: "https://api.focusnfe.com.br",
}
#: Hosts `fetch_document` may contact (SSRF allowlist). The S3 host and the
#: national portal appear in documented `url_danfse` / `url` examples.
_DOWNLOAD_HOSTS = frozenset(
    {
        "api.focusnfe.com.br",
        "homologacao.focusnfe.com.br",
        "focusnfe.s3.sa-east-1.amazonaws.com",
        "www.nfse.gov.br",
    }
)
_FOCUS_HOSTS = frozenset({"api.focusnfe.com.br", "homologacao.focusnfe.com.br"})
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024

_STATUS_MAP: dict[str, InvoiceStatus] = {
    "processando_autorizacao": InvoiceStatus.PROCESSING,
    "autorizado": InvoiceStatus.AUTHORIZED,
    "cancelado": InvoiceStatus.CANCELLED,
    "erro_autorizacao": InvoiceStatus.REJECTED,
    "denegado": InvoiceStatus.REJECTED,  # UNVERIFIED: NF-e denied by SEFAZ
}
#: 422 codes meaning "this ref already exists" -> idempotent re-issue = read it.
_ALREADY_EXISTS_CODES = frozenset(
    {"already_processed", "pending_operation", "nfe_autorizada"}
)
_REGIME_CODE = {"simples": 1, "simples_excess": 2, "normal": 3, "mei": 4}
_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,60}$")

#: UNVERIFIED policy default (adconnect assumed Simples Nacional too): the NF-e
#: item tax situations SEFAZ requires. Override via `nfe_item_tax_defaults`.
DEFAULT_NFE_ITEM_TAX = {
    "icms_origem": 0,
    "icms_situacao_tributaria": "102",
    "pis_situacao_tributaria": "07",
    "cofins_situacao_tributaria": "07",
}


class _RateLimited(Exception):
    def __init__(self, retry_after: Optional[float]) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


def _reais(cents: int) -> float:
    return float((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v not in (None, "")}


def company_flags(mode: NfseMode, environment: InvoiceEnvironment, enable_nfe: bool) -> dict[str, bool]:
    """The `habilita_*` block. NFS-e municipal and NFS-e Nacional are mutually
    exclusive on Focus - exactly one channel is ever switched on."""
    nacional = mode is NfseMode.NACIONAL
    return {
        "habilita_nfe": enable_nfe,
        "habilita_nfse": not nacional,
        "habilita_nfsen_producao": nacional and environment is InvoiceEnvironment.PRODUCAO,
        "habilita_nfsen_homologacao": nacional and environment is InvoiceEnvironment.HOMOLOGACAO,
    }


def map_focus_status(raw: str) -> Optional[InvoiceStatus]:
    return _STATUS_MAP.get(raw)


class FocusNFeInvoiceProvider:
    name = PROVIDER

    def __init__(
        self,
        *,
        account_token: str,
        environment: InvoiceEnvironment = InvoiceEnvironment.HOMOLOGACAO,
        company_tokens: Optional[Callable[[str], Optional[str]]] = None,
        default_company_token: Optional[str] = None,
        nfe_item_tax_defaults: Optional[dict[str, Any]] = None,
        timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        if not account_token:
            raise ValueError("FocusNFeInvoiceProvider requires a non-empty account_token")
        self._account_token = account_token
        self._environment = environment
        self._company_tokens = company_tokens
        self._default_company_token = default_company_token
        self._nfe_tax = dict(DEFAULT_NFE_ITEM_TAX, **(nfe_item_tax_defaults or {}))
        self._base_url = BASE_URLS[environment]
        self._clock = clock
        # No default auth on the client: the token differs per call (account vs company).
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:  # never include tokens
        return f"FocusNFeInvoiceProvider(environment={self._environment.value!r})"

    # ── HTTP primitive ───────────────────────────────────────────────

    def _send(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> tuple[int, dict[str, Any]]:
        def _once() -> tuple[int, dict[str, Any]]:
            # Raise OUTSIDE the `except` so no httpx exception (whose text can echo
            # headers/body) is left on the new error's __context__ chain.
            failure: Optional[str] = None
            response: Optional[httpx.Response] = None
            try:
                response = self._client.request(
                    method, path, json=json, params=params, auth=httpx.BasicAuth(token, "")
                )
            except httpx.TimeoutException:
                failure = "timeout"
            except httpx.TransportError:
                failure = "transporte"
            if failure == "timeout":
                raise InvoiceProviderError(
                    PROVIDER, "tempo esgotado ao chamar o provedor", code="timeout", retryable=True
                )
            if failure is not None or response is None:
                raise InvoiceProviderError(
                    PROVIDER, "falha de rede ao chamar o provedor", code="transporte", retryable=True
                )
            if response.status_code == 429:
                raise _RateLimited(parse_retry_after(response.headers.get("Retry-After")))
            return response.status_code, self._json(response)

        try:
            status, body = paced_call(
                _once,
                bucket=RATE_BUCKET,
                is_retryable=lambda e: isinstance(e, _RateLimited),
                retry_after=lambda e: getattr(e, "retry_after", None),
                clock=self._clock,
            )
        except _RateLimited:
            limited = True
        else:
            limited = False
        if limited:
            raise InvoiceProviderError(
                PROVIDER, "limite de requisicoes do provedor", code="rate_limited",
                status=429, retryable=True,
            )
        logger.debug("focusnfe %s %s -> %s", method, path, status)
        return status, body

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # ── error mapping (generic by construction) ──────────────────────

    @staticmethod
    def _reasons(body: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        for err in body.get("erros") or []:
            if isinstance(err, dict) and err.get("mensagem"):
                text = str(err["mensagem"])
                if err.get("correcao"):
                    text = f"{text} ({err['correcao']})"
                reasons.append(text[:300])
        if not reasons:
            for key in ("mensagem_sefaz", "mensagem"):
                if body.get(key):
                    reasons.append(str(body[key])[:300])
                    break
        return reasons

    def _raise(self, status: int, body: dict[str, Any], *, ref: str = "") -> InvoiceProviderError:
        if status in (401, 403):
            return InvoiceProviderError(
                PROVIDER, "credenciais do provedor invalidas", code="credenciais_invalidas", status=status
            )
        if status == 404:
            return InvoiceNotFound(PROVIDER, ref)
        if status >= 500:
            return InvoiceProviderError(
                PROVIDER, "provedor indisponivel", code="provedor_indisponivel",
                status=status, retryable=True,
            )
        raw_code = str(body.get("codigo") or "").lower()
        code = raw_code if _SAFE_CODE.match(raw_code) else "erro_provedor"
        return InvoiceProviderError(
            PROVIDER, "requisicao recusada pelo provedor", code=code, status=status,
            reasons=self._reasons(body),
        )

    # ── tokens ───────────────────────────────────────────────────────

    def _company_token(self, company_ref: Optional[str]) -> str:
        token: Optional[str] = None
        if company_ref and self._company_tokens is not None:
            token = self._company_tokens(company_ref)
        token = token or self._default_company_token
        if not token:
            raise InvoiceProviderError(
                PROVIDER, "token da empresa ausente", code="company_token_ausente"
            )
        return token

    # ── account ──────────────────────────────────────────────────────

    def verify_credentials(self) -> None:
        status, body = self._send("GET", "/v2/empresas", token=self._account_token)
        if status >= 400:
            raise self._raise(status, body)

    # ── companies ────────────────────────────────────────────────────

    def _company_from_body(
        self, body: dict[str, Any], fallback_mode: Optional[NfseMode]
    ) -> ProviderCompany:
        if body.get("id") is None:
            raise InvoiceProviderError(
                PROVIDER, "resposta de empresa invalida", code="resposta_invalida"
            )
        prod = self._environment is InvoiceEnvironment.PRODUCAO
        municipal = bool(body.get("habilita_nfse"))
        nacional = bool(body.get("habilita_nfsen_producao" if prod else "habilita_nfsen_homologacao"))
        if municipal and nacional:
            raise InvoiceProviderError(
                PROVIDER, "empresa com NFS-e municipal e nacional ativas", code="nfse_mode_conflict"
            )
        mode = NfseMode.NACIONAL if nacional else NfseMode.MUNICIPAL if municipal else (
            fallback_mode or NfseMode.MUNICIPAL
        )
        token = body.get("token_producao" if prod else "token_homologacao")
        return ProviderCompany(
            ref=str(body["id"]),
            cnpj=str(body.get("cnpj") or ""),
            nfse_mode=mode,
            nfe_enabled=bool(body.get("habilita_nfe")),
            nfse_enabled=municipal or nacional,
            company_token=str(token) if token else None,
        )

    def _get_company_body(self, company_ref: str) -> dict[str, Any]:
        status, body = self._send("GET", f"/v2/empresas/{company_ref}", token=self._account_token)
        if status >= 400:
            raise self._raise(status, body, ref=company_ref)
        return body

    def ensure_company(self, request: CompanyRequest) -> ProviderCompany:
        a = request.address
        payload = _compact(
            {
                "nome": request.legal_name,
                "nome_fantasia": request.trade_name,
                "cnpj": request.cnpj,
                "inscricao_municipal": request.inscricao_municipal,
                "inscricao_estadual": request.inscricao_estadual,
                "regime_tributario": _REGIME_CODE.get(request.tax_regime),
                "logradouro": a.street,
                "numero": a.number,
                "complemento": a.complement,
                "bairro": a.district,
                "municipio": a.city,
                "cep": a.zip_code,
                "uf": a.state,
                "email": request.email,
            }
        )
        payload.update(company_flags(request.nfse_mode, self._environment, request.enable_nfe))
        if request.company_ref:
            # UNVERIFIED: that the PUT response carries the token pair; if not,
            # the token is None and the caller keeps its stored one.
            status, body = self._send(
                "PUT", f"/v2/empresas/{request.company_ref}", token=self._account_token, json=payload
            )
        else:
            status, body = self._send("POST", "/v2/empresas", token=self._account_token, json=payload)
        if status >= 400:
            raise self._raise(status, body, ref=request.company_ref or "")
        if body.get("id") is None and request.company_ref:
            body = {**self._get_company_body(request.company_ref), **body}
        return self._company_from_body(body, request.nfse_mode)

    def upload_certificate(
        self, company_ref: str, *, pfx: bytes, password: str
    ) -> CertificateInfo:
        info = inspect_pkcs12(pfx, password)  # fails generically BEFORE any send
        payload: Optional[dict[str, Any]] = {
            "arquivo_certificado_base64": base64.b64encode(pfx).decode("ascii"),
            "senha_certificado": password,
            # Without this Focus propagates the cert to every company sharing the CNPJ root.
            "certificado_especifico": True,
        }
        try:
            status, body = self._send(
                "PUT", f"/v2/empresas/{company_ref}", token=self._account_token, json=payload
            )
        finally:
            payload = None  # drop the only copy of the secret payload
        if status >= 400:
            raise self._raise(status, body, ref=company_ref)
        return info

    def set_nfse_mode(self, company_ref: str, mode: NfseMode) -> ProviderCompany:
        flags = company_flags(mode, self._environment, enable_nfe=False)
        flags.pop("habilita_nfe")  # leave the NF-e switch untouched
        status, body = self._send(
            "PUT", f"/v2/empresas/{company_ref}", token=self._account_token, json=flags
        )
        if status >= 400:
            raise self._raise(status, body, ref=company_ref)
        return self._company_from_body(self._get_company_body(company_ref), mode)

    # ── documents ────────────────────────────────────────────────────

    def _absolute(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if path.startswith("/"):
            return f"{self._base_url}{path}"
        return path

    def _result(self, kind: InvoiceKind, ref: str, body: dict[str, Any]) -> InvoiceResult:
        raw_status = body.get("status")
        status = _STATUS_MAP.get(str(raw_status)) if raw_status is not None else None
        if status is None:
            # NEVER default to "pending": an unmapped status is a surfaced error.
            raise InvoiceProviderError(
                PROVIDER, "status desconhecido retornado pelo provedor", code="unknown_status"
            )
        key = body.get("chave_nfe")
        if isinstance(key, str) and key.startswith("NFe"):
            key = key[3:]
        pdf = body.get("caminho_danfe") if kind is InvoiceKind.NFE else body.get("url_danfse")
        number = body.get("numero")
        return InvoiceResult(
            ref=ref,
            kind=kind,
            status=status,
            number=str(number) if number is not None else None,
            series=str(body["serie"]) if body.get("serie") is not None else None,
            access_key=key,
            verification_code=body.get("codigo_verificacao"),
            pdf_url=self._absolute(pdf),
            xml_url=self._absolute(body.get("caminho_xml_nota_fiscal")),
            rejection_reasons=self._reasons(body) if status is InvoiceStatus.REJECTED else [],
            raw=scrub(body, extra_secrets=(self._account_token, self._default_company_token or "")),
        )

    @staticmethod
    def _paths(kind: InvoiceKind, ref: str) -> list[str]:
        if kind is InvoiceKind.NFE:
            return [f"/v2/nfe/{ref}"]
        # A store can cut over municipal -> nacional AFTER issuing, so a lookup
        # cannot trust the current mode: probe both channels.
        return [f"/v2/nfsen/{ref}", f"/v2/nfse/{ref}"]

    def _locate(
        self, kind: InvoiceKind, ref: str, token: str
    ) -> tuple[str, dict[str, Any]]:
        for path in self._paths(kind, ref):
            status, body = self._send("GET", path, token=token)
            if status == 404:
                continue
            if status >= 400:
                raise self._raise(status, body, ref=ref)
            return path, body
        raise InvoiceNotFound(PROVIDER, ref)

    def get(
        self, kind: InvoiceKind, ref: str, *, company_ref: Optional[str] = None
    ) -> InvoiceResult:
        _path, body = self._locate(kind, ref, self._company_token(company_ref))
        return self._result(kind, ref, body)

    def cancel(
        self,
        kind: InvoiceKind,
        ref: str,
        *,
        reason: str,
        company_ref: Optional[str] = None,
    ) -> InvoiceResult:
        text = (reason or "").strip()
        if not 15 <= len(text) <= 255:
            raise InvoiceProviderError(
                PROVIDER, "justificativa deve ter entre 15 e 255 caracteres", code="justificativa_invalida"
            )
        token = self._company_token(company_ref)
        path, body = self._locate(kind, ref, token)
        current = self._result(kind, ref, body)
        if current.status is InvoiceStatus.CANCELLED:
            return current  # idempotent
        if current.status is InvoiceStatus.PROCESSING:
            raise InvoiceProviderError(PROVIDER, "nota ainda em processamento", code="em_processamento")
        if current.status is not InvoiceStatus.AUTHORIZED:
            raise InvoiceProviderError(PROVIDER, "nota nao autorizada", code="nao_autorizada")
        # UNVERIFIED: /nfsen cancel may also require `codigo_cancelamento`
        # (its doc says justificativa is needed "if the cancel code is 4").
        status, resp = self._send("DELETE", path, token=token, json={"justificativa": text})
        if status >= 400:
            raise self._raise(status, resp, ref=ref)
        if resp.get("status") == "erro_cancelamento":
            raise InvoiceProviderError(
                PROVIDER, "cancelamento recusado pelo provedor", code="cancel_refused",
                reasons=self._reasons(resp),
            )
        if resp.get("status") != "cancelado":
            raise InvoiceProviderError(
                PROVIDER, "status desconhecido retornado pelo provedor", code="unknown_status"
            )
        return self.get(kind, ref, company_ref=company_ref)

    # ── issue ────────────────────────────────────────────────────────

    def issue(self, request: InvoiceRequest) -> InvoiceResult:
        token = self._company_token(request.company_ref)
        company = self._get_company_body(request.company_ref)
        mode = self._company_from_body(company, None).nfse_mode
        if request.kind is InvoiceKind.NFE:
            path, payload = "/v2/nfe", self._nfe_payload(request, company)
        elif mode is NfseMode.NACIONAL:
            path, payload = "/v2/nfsen", self._nfsen_payload(request, company)
        else:
            path, payload = "/v2/nfse", self._nfse_payload(request, company)

        status, body = self._send("POST", path, token=token, json=payload, params={"ref": request.ref})
        if status in (200, 201, 202):
            return self._result(request.kind, request.ref, body)
        if status == 422:
            code = str(body.get("codigo") or "").lower()
            if code in _ALREADY_EXISTS_CODES:
                return self.get(request.kind, request.ref, company_ref=request.company_ref)
            if code in ("permissao_negada", "erro_validacao") or code.startswith("requisicao"):
                raise self._raise(status, body, ref=request.ref)
            # Synchronous pre-validation failure: a business rejection, not a crash.
            return InvoiceResult(
                ref=request.ref,
                kind=request.kind,
                status=InvoiceStatus.REJECTED,
                rejection_reasons=self._reasons(body) or ["rejeitada pelo provedor"],
                raw=scrub(body),
            )
        raise self._raise(status, body, ref=request.ref)

    # ── payload builders ─────────────────────────────────────────────

    @staticmethod
    def _regime(company: dict[str, Any]) -> Optional[int]:
        value = company.get("regime_tributario")  # UNVERIFIED: present on company GET
        return int(value) if str(value or "").isdigit() else None

    def _nfe_payload(self, r: InvoiceRequest, company: dict[str, Any]) -> dict[str, Any]:
        t, a = r.taker, r.taker.address
        doc_key = "cnpj" if len(t.doc) == 14 else "cpf"
        items = []
        for idx, it in enumerate(r.items, start=1):
            items.append(
                {
                    "numero_item": idx,
                    "codigo_produto": str(idx),
                    "descricao": it.description,
                    "cfop": it.cfop,
                    "codigo_ncm": it.ncm,
                    "unidade_comercial": "UN",
                    "unidade_tributavel": "UN",
                    "quantidade_comercial": it.quantity,
                    "quantidade_tributavel": it.quantity,
                    "valor_unitario_comercial": _reais(it.unit_cents),
                    "valor_unitario_tributavel": _reais(it.unit_cents),
                    "valor_bruto": _reais(it.total_cents),
                    "inclui_no_total": 1,
                    **self._nfe_tax,
                }
            )
        return _compact(
            {
                "natureza_operacao": "Venda de mercadoria",
                "data_emissao": r.issued_on.isoformat(),
                "tipo_documento": 1,
                "finalidade_emissao": 1,
                "consumidor_final": 1,
                "presenca_comprador": 2,
                "modalidade_frete": 9,
                "cnpj_emitente": company.get("cnpj"),
                "nome_destinatario": t.name,
                f"{doc_key}_destinatario": t.doc,
                "indicador_inscricao_estadual_destinatario": 9,
                "logradouro_destinatario": a.street,
                "numero_destinatario": a.number,
                "bairro_destinatario": a.district,
                "municipio_destinatario": a.city,
                "uf_destinatario": a.state,
                "cep_destinatario": a.zip_code,
                "informacoes_adicionais_contribuinte": r.additional_info,  # UNVERIFIED name
                "valor_produtos": _reais(r.total_cents),
                "valor_total": _reais(r.total_cents),
                "items": items,
            }
        )

    @staticmethod
    def _discriminacao(r: InvoiceRequest) -> str:
        lines = [f"{it.description} ({it.quantity:g} x R$ {_reais(it.unit_cents):.2f})" for it in r.items]
        if r.additional_info:
            lines.append(r.additional_info)
        return "; ".join(lines)

    def _nfse_payload(self, r: InvoiceRequest, company: dict[str, Any]) -> dict[str, Any]:
        t, a = r.taker, r.taker.address
        first = r.items[0]
        regime = self._regime(company)
        servico = _compact(
            {
                "valor_servicos": _reais(r.total_cents),
                "item_lista_servico": first.service_code,
                "codigo_tributario_municipio": first.service_code,
                "discriminacao": self._discriminacao(r),
                "codigo_municipio": company.get("codigo_municipio"),
                "aliquota": r.iss_rate_bps / 10000 if r.iss_rate_bps else None,
                "codigo_nbs": first.nbs_code,
                "ibs_cbs_classificacao_tributaria": first.c_class_trib,
            }
        )
        servico["iss_retido"] = r.iss_retained
        servico.update(r.ibs_cbs or {})
        return {
            "data_emissao": r.issued_on.isoformat(),
            "natureza_operacao": "1",
            "optante_simples_nacional": regime in (1, 2, 4),
            "prestador": _compact(
                {
                    "cnpj": company.get("cnpj"),
                    "inscricao_municipal": company.get("inscricao_municipal"),
                    "codigo_municipio": company.get("codigo_municipio"),
                }
            ),
            "tomador": _compact(
                {
                    ("cnpj" if len(t.doc) == 14 else "cpf"): t.doc,
                    "razao_social": t.name,
                    "email": t.email,
                    "endereco": _compact(
                        {
                            "logradouro": a.street,
                            "numero": a.number,
                            "bairro": a.district,
                            "codigo_municipio": a.city_ibge,
                            "uf": a.state,
                            "cep": a.zip_code,
                        }
                    ),
                }
            ),
            "servico": servico,
        }

    def _nfsen_payload(self, r: InvoiceRequest, company: dict[str, Any]) -> dict[str, Any]:
        t = r.taker
        first = r.items[0]
        regime = self._regime(company)
        # UNVERIFIED value codes follow the national DPS standard (1 nao optante,
        # 2 MEI, 3 ME/EPP); the public field list only describes them as strings.
        simples = "2" if regime == 4 else "3" if regime in (1, 2) else "1"
        payload = _compact(
            {
                "data_emissao": r.issued_on.isoformat(),
                "data_competencia": r.competence.isoformat(),
                "codigo_municipio_emissora": company.get("codigo_municipio"),
                "cnpj_prestador": company.get("cnpj"),
                "codigo_opcao_simples_nacional": simples,
                ("cnpj_tomador" if len(t.doc) == 14 else "cpf_tomador"): t.doc,
                "razao_social_tomador": t.name,  # UNVERIFIED field name
                "email_tomador": t.email,  # UNVERIFIED field name
                "codigo_municipio_prestacao": company.get("codigo_municipio"),
                "codigo_tributacao_nacional_iss": first.service_code,
                "descricao_servico": self._discriminacao(r),
                "valor_servico": _reais(r.total_cents),
                "tributacao_iss": 1,  # UNVERIFIED value: 1 = operacao tributavel
                "ibs_cbs_classificacao_tributaria": first.c_class_trib,  # UNVERIFIED key on /nfsen
                "codigo_nbs": first.nbs_code,  # UNVERIFIED key on /nfsen
            }
        )
        payload.update(r.ibs_cbs or {})  # caller-supplied provider keys, UNVERIFIED on /nfsen
        return payload

    # ── documents download / webhook ─────────────────────────────────

    def fetch_document(self, url: str) -> bytes:
        absolute = self._absolute(url) or ""
        parsed = urlparse(absolute)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or host not in _DOWNLOAD_HOSTS:
            raise InvoiceProviderError(PROVIDER, "url de documento nao permitida", code="url_nao_permitida")
        # Credentials only ever go to Focus's own hosts, never S3 / the national portal.
        auth = httpx.BasicAuth(self._account_token, "") if host in _FOCUS_HOSTS else None
        response: Optional[httpx.Response] = None
        try:
            response = self._client.get(absolute, auth=auth, follow_redirects=False)
        except httpx.HTTPError:
            response = None
        if response is None:
            raise InvoiceProviderError(
                PROVIDER, "falha ao baixar documento", code="transporte", retryable=True
            )
        if response.status_code == 404:
            raise InvoiceNotFound(PROVIDER, absolute)
        if response.status_code >= 400:
            raise self._raise(response.status_code, {}, ref=absolute)
        if len(response.content) > _MAX_DOCUMENT_BYTES:
            raise InvoiceProviderError(PROVIDER, "documento excede o limite", code="documento_grande")
        return response.content

    def parse_webhook(
        self, headers: Mapping[str, str], body: bytes, *, token: Optional[str]
    ) -> InvoiceEvent:
        return parse_webhook_event(
            PROVIDER, headers, body, token=token, map_status=map_focus_status
        )

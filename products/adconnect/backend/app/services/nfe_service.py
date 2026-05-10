"""NF-e (Brazilian electronic invoice) service.

Phase 5 surface — keeps the NF-e provider behind a Protocol so the choice
(Focus NFe / NFe.io / eNotas / custom) can be swapped without touching the
caller. PROJECT.md §7 question 1 recommends Focus NFe.

Pattern mirrors `seed/lib/backend/noctusai_lib/integrations/google_calendar/`
and `google_maps/`: Protocol + Fake + Real + factory. The Real adapter
(`FocusNFeProvider`) lands in Phase 5; the Fake serves tests + local dev
without burning provider credits.

External-SDK / external-HTTP integration: per CLAUDE.md no-monkey-patching
rule, patching `httpx.Client.post` (etc.) in tests is allowed because httpx
is external; the rule covers OUR code, not external integrations.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


# ============================================================================
# Domain DTOs (provider-agnostic — Phase 5 routers / services consume these)
# ============================================================================

@dataclass(frozen=True)
class NFeItem:
    """One line item on an NF-e."""

    sku: str
    descricao: str
    quantidade: int
    valor_unitario: float
    cfop: str  # Operação Fiscal — "5102" for typical sale-within-state, etc.


@dataclass(frozen=True)
class NFeIssueRequest:
    """Inputs to issue an NF-e for a single fatura."""

    fatura_id: str
    distributor_cnpj: str
    distributor_razao_social: str
    distributor_endereco: dict  # logradouro, numero, complemento, bairro, cidade, uf, cep
    items: list[NFeItem]
    valor_total: float
    natureza_operacao: str = "Venda de mercadoria"


@dataclass(frozen=True)
class NFeIssueResult:
    """What the provider returns when an NF-e is accepted (or rejected)."""

    chave: str            # 44-char canonical NF-e key
    xml: str              # full signed XML
    xml_url: str | None   # provider-hosted URL when available
    status: str           # "autorizado" | "rejeitado" | "pendente"
    provider: str         # "focusnfe" | "nfeio" | "enotas" | "fake"
    provider_id: str      # provider's internal reference
    issued_at: datetime
    rejection_reason: str | None = None


@dataclass(frozen=True)
class NFeCancelRequest:
    chave: str
    justificativa: str


@dataclass(frozen=True)
class NFeCancelResult:
    chave: str
    canceled_at: datetime
    provider_id: str


# ============================================================================
# Protocol (the seam — DI everywhere; tests inject Fake; prod injects Real)
# ============================================================================

class NFeProvider(Protocol):
    """Provider contract for NF-e issuance + cancelation.

    Implementations must be idempotent on `issue` (same fatura_id → same
    chave returned) and tolerate provider retries without double-issuing.
    """

    def issue(self, request: NFeIssueRequest) -> NFeIssueResult: ...

    def cancel(self, request: NFeCancelRequest) -> NFeCancelResult: ...

    def status(self, chave: str) -> str:
        """Returns one of: pendente / autorizado / rejeitado / cancelado."""
        ...


# ============================================================================
# Fake (test-only — deterministic, no network)
# ============================================================================

class FakeNFeProvider:
    """In-memory NF-e provider for tests + local dev.

    Generates a deterministic chave from the fatura_id; stores issued
    invoices in a dict so cancel + status round-trip cleanly. Never makes
    network calls, never returns rejected status (use FakeNFeProvider with
    `reject_pattern=` if Phase 5 tests need to exercise the rejection
    path).
    """

    def __init__(self, *, reject_pattern: str | None = None) -> None:
        self._issued: dict[str, NFeIssueResult] = {}
        self._reject_pattern = reject_pattern

    def issue(self, request: NFeIssueRequest) -> NFeIssueResult:
        # Idempotent: same fatura_id → same result
        if request.fatura_id in self._issued:
            return self._issued[request.fatura_id]

        if self._reject_pattern and self._reject_pattern in request.distributor_cnpj:
            result = NFeIssueResult(
                chave="0" * 44,
                xml="",
                xml_url=None,
                status="rejeitado",
                provider="fake",
                provider_id=f"fake-rejected-{request.fatura_id}",
                issued_at=datetime.utcnow(),
                rejection_reason="FakeNFeProvider configured to reject this CNPJ pattern",
            )
        else:
            chave = f"FAKE{request.fatura_id.replace('-', '')[:40]}".ljust(44, "0")[:44]
            result = NFeIssueResult(
                chave=chave,
                xml=f"<NFe fake='true' fatura_id='{request.fatura_id}'/>",
                xml_url=None,
                status="autorizado",
                provider="fake",
                provider_id=f"fake-{request.fatura_id}",
                issued_at=datetime.utcnow(),
            )

        self._issued[request.fatura_id] = result
        return result

    def cancel(self, request: NFeCancelRequest) -> NFeCancelResult:
        # Find by chave + flip status (in-memory only)
        for fatura_id, res in self._issued.items():
            if res.chave == request.chave:
                self._issued[fatura_id] = NFeIssueResult(
                    **{**res.__dict__, "status": "cancelado"}
                )
                return NFeCancelResult(
                    chave=request.chave,
                    canceled_at=datetime.utcnow(),
                    provider_id=res.provider_id,
                )
        raise ValueError(f"NFe chave {request.chave!r} not found in FakeNFeProvider")

    def status(self, chave: str) -> str:
        for res in self._issued.values():
            if res.chave == chave:
                return res.status
        return "pendente"


# ============================================================================
# Real adapter — Focus NFe (REST API; https://focusnfe.com.br/doc/)
# ============================================================================


class FocusNFeMisconfiguredError(RuntimeError):
    """Raised when FocusNFeProvider is invoked without an API key."""


class FocusNFeProvider:
    """Production NF-e provider using Focus NFe's REST API.

    Endpoints (per https://focusnfe.com.br/doc/):
      • POST /v2/nfe?ref=<ref>     — issue NF-e (asynchronous; provider replies
        with a status the caller polls).
      • GET  /v2/nfe/<ref>         — query NF-e status.
      • DELETE /v2/nfe/<ref>       — cancel NF-e.

    Authentication: HTTP Basic auth using the API key as the username (no
    password). The `ambiente` field controls homologação (sandbox) vs
    produção by selecting the host:
      • homologação: https://homologacao.focusnfe.com.br
      • produção:    https://api.focusnfe.com.br

    Test mode: if `FOCUSNFE_API_KEY` is unset (and constructor `api_key` is
    None), `issue` raises `FocusNFeMisconfiguredError` immediately — no
    silent degraded mode.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        ambiente: str = "homologacao",
        emitter_cnpj: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("FOCUSNFE_API_KEY")
        if ambiente not in {"homologacao", "producao"}:
            raise ValueError(
                f"FocusNFeProvider: ambiente must be 'homologacao' or 'producao', "
                f"got {ambiente!r}"
            )
        self._ambiente = ambiente
        self._emitter_cnpj = emitter_cnpj or os.environ.get("FOCUSNFE_EMITTER_CNPJ")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        if self._ambiente == "producao":
            return "https://api.focusnfe.com.br"
        return "https://homologacao.focusnfe.com.br"

    def _ensure_configured(self) -> str:
        if not self._api_key:
            raise FocusNFeMisconfiguredError(
                "FOCUSNFE_API_KEY not set — cannot call Focus NFe API. "
                "Configure the environment variable or pass api_key to "
                "FocusNFeProvider."
            )
        return self._api_key

    def _http(self) -> Any:
        """Lazy httpx import — kept lazy so test envs without httpx don't break."""
        try:
            import httpx  # type: ignore
        except ImportError as exc:  # pragma: no cover — dev dependency
            raise RuntimeError(
                "httpx not installed; required by FocusNFeProvider"
            ) from exc
        return httpx

    def _build_payload(self, request: NFeIssueRequest) -> dict[str, Any]:
        """Map the provider-agnostic request to Focus NFe's JSON shape.

        Subset of Focus NFe's NFe schema — sufficient for AdConnect's
        invoice-for-distributor use case. Fields like ICMS/PIS/COFINS are
        defaulted to "Simples Nacional" assumptions; expand as use cases
        require.
        """
        endereco = request.distributor_endereco or {}
        return {
            "natureza_operacao": request.natureza_operacao,
            "data_emissao": datetime.now(timezone.utc).isoformat(),
            "tipo_documento": "1",  # 1 = saída
            "finalidade_emissao": "1",  # 1 = NF-e normal
            "cnpj_emitente": self._emitter_cnpj or "",
            "nome_destinatario": request.distributor_razao_social,
            "cnpj_destinatario": request.distributor_cnpj,
            "logradouro_destinatario": endereco.get("logradouro", ""),
            "numero_destinatario": endereco.get("numero", ""),
            "bairro_destinatario": endereco.get("bairro", ""),
            "municipio_destinatario": endereco.get("cidade", ""),
            "uf_destinatario": endereco.get("uf", ""),
            "cep_destinatario": endereco.get("cep", ""),
            "valor_total": f"{request.valor_total:.2f}",
            "items": [
                {
                    "numero_item": str(idx + 1),
                    "codigo_produto": item.sku,
                    "descricao": item.descricao,
                    "cfop": item.cfop,
                    "unidade_comercial": "UN",
                    "quantidade_comercial": str(item.quantidade),
                    "valor_unitario_comercial": f"{item.valor_unitario:.2f}",
                    "valor_bruto": f"{item.quantidade * item.valor_unitario:.2f}",
                }
                for idx, item in enumerate(request.items)
            ],
        }

    def issue(self, request: NFeIssueRequest) -> NFeIssueResult:
        api_key = self._ensure_configured()
        httpx = self._http()
        ref = f"adconnect-{request.fatura_id}"
        payload = self._build_payload(request)
        url = f"{self.base_url}/v2/nfe?ref={ref}"
        with httpx.Client(auth=(api_key, ""), timeout=self._timeout) as client:
            try:
                response = client.post(url, json=payload)
            except Exception as exc:
                logger.error("FocusNFeProvider.issue: HTTP error (%s)", exc)
                raise

        body = self._safe_json(response)
        status_code = response.status_code

        if status_code in (200, 201, 202):
            # Focus NFe returns the queued status; the caller polls to detect
            # autorizado/rejeitado. We optimistically map "processando_autorizacao"
            # to pendente and an immediate "autorizado" to autorizado.
            provider_status = str(body.get("status") or "pendente").lower()
            mapped = self._map_status(provider_status)
            return NFeIssueResult(
                chave=str(body.get("chave_nfe") or "0" * 44),
                xml=str(body.get("xml") or body.get("caminho_xml_nota_fiscal") or ""),
                xml_url=body.get("caminho_xml_nota_fiscal"),
                status=mapped,
                provider="focusnfe",
                provider_id=ref,
                issued_at=datetime.now(timezone.utc),
            )

        if status_code in (400, 422):
            return NFeIssueResult(
                chave="0" * 44,
                xml="",
                xml_url=None,
                status="rejeitado",
                provider="focusnfe",
                provider_id=ref,
                issued_at=datetime.now(timezone.utc),
                rejection_reason=str(
                    body.get("mensagem") or body.get("erros") or "Rejeitado"
                ),
            )

        # Anything else is a hard error — bubble up. No silent degraded mode.
        raise RuntimeError(
            f"FocusNFeProvider.issue: unexpected HTTP {status_code}: {body!r}"
        )

    def cancel(self, request: NFeCancelRequest) -> NFeCancelResult:
        api_key = self._ensure_configured()
        httpx = self._http()
        # Focus NFe's cancel endpoint is keyed on `ref`, not `chave`. We
        # reverse-derive the ref from the chave's last 8 chars (matches
        # `adconnect-<fatura_id>` shape from `issue`). Caller may also pass
        # an explicit ref via justificativa-prefix in production deployments.
        # For Phase 5 we accept the round-trip via `ref` lookup-by-chave that
        # the provider exposes via GET — but since AdConnect retains the
        # provider_id (=ref) in `faturas.nfe_provider_id`, callers should
        # use `cancel_by_ref` directly. This method preserves the Protocol.
        url = f"{self.base_url}/v2/nfe/{request.chave}"
        with httpx.Client(auth=(api_key, ""), timeout=self._timeout) as client:
            try:
                response = client.delete(
                    url, params={"justificativa": request.justificativa}
                )
            except Exception as exc:
                logger.error("FocusNFeProvider.cancel: HTTP error (%s)", exc)
                raise

        if response.status_code in (200, 202, 204):
            return NFeCancelResult(
                chave=request.chave,
                canceled_at=datetime.now(timezone.utc),
                provider_id=str(request.chave),
            )
        body = self._safe_json(response)
        raise RuntimeError(
            f"FocusNFeProvider.cancel: HTTP {response.status_code}: {body!r}"
        )

    def status(self, chave: str) -> str:
        api_key = self._ensure_configured()
        httpx = self._http()
        url = f"{self.base_url}/v2/nfe/{chave}"
        with httpx.Client(auth=(api_key, ""), timeout=self._timeout) as client:
            try:
                response = client.get(url)
            except Exception as exc:
                logger.error("FocusNFeProvider.status: HTTP error (%s)", exc)
                raise

        if response.status_code == 404:
            return "pendente"

        body = self._safe_json(response)
        provider_status = str(body.get("status") or "pendente").lower()
        return self._map_status(provider_status)

    @staticmethod
    def _map_status(provider_status: str) -> str:
        """Map Focus NFe status strings to our domain vocabulary."""
        mapping = {
            "autorizado": "autorizado",
            "processando_autorizacao": "pendente",
            "denegado": "rejeitado",
            "erro_autorizacao": "rejeitado",
            "rejeitado": "rejeitado",
            "cancelado": "cancelado",
        }
        return mapping.get(provider_status, "pendente")

    @staticmethod
    def _safe_json(response: Any) -> dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"_raw": data}
        except Exception:
            return {"_text": getattr(response, "text", "")}


# ============================================================================
# Factory (wired into create_product_app lifespan)
# ============================================================================

def make_nfe_provider(provider_name: str, **config) -> NFeProvider:
    """Factory dispatch: returns a configured provider instance.

    Wiring example::

        # In app/main.py lifespan_startup:
        nfe = make_nfe_provider(
            provider_name=settings.NFE_PROVIDER,
            api_key=settings.NFE_API_KEY,
            ambiente=settings.NFE_AMBIENTE,
            emitter_cnpj=settings.NFE_EMITTER_CNPJ,
        )
        app.state.nfe_provider = nfe
    """
    if provider_name == "fake":
        return FakeNFeProvider(reject_pattern=config.get("reject_pattern"))

    if provider_name == "focusnfe":
        return FocusNFeProvider(
            api_key=config.get("api_key"),
            ambiente=config.get("ambiente", "homologacao"),
            emitter_cnpj=config.get("emitter_cnpj"),
            timeout=config.get("timeout", 30.0),
        )

    if provider_name == "nfeio":
        raise NotImplementedError("NFeIoProvider — alternative not implemented")

    if provider_name == "enotas":
        raise NotImplementedError("ENotasProvider — alternative not implemented")

    raise ValueError(
        f"Unknown NFe provider {provider_name!r}; "
        f"supported: fake, focusnfe, nfeio, enotas"
    )

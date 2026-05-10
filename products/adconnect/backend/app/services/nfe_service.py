"""NF-e (Brazilian electronic invoice) service.

Phase 5 surface — keeps the NF-e provider behind a Protocol so the choice
(Focus NFe / NFe.io / eNotas / custom) can be swapped without touching the
caller. PROJECT.md §7 question 1 recommends Focus NFe; this skeleton stays
provider-agnostic so that decision can land cheaply.

Pattern mirrors `seed/lib/backend/noctusai_lib/integrations/google_calendar/`
and `google_maps/`: Protocol + Fake + Real + factory. The Real adapter is
authored when the provider is locked in Phase 5; the Fake serves Phase 5
tests + local dev without burning provider credits.

Status: SKELETON — Phase 5 fills in the Real adapter and wires the factory
into create_product_app's lifespan_startup so the global FaturaService
gets a configured NF-e backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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
# Factory (Phase 5 wires this into create_product_app lifespan)
# ============================================================================

def make_nfe_provider(provider_name: str, **config) -> NFeProvider:
    """Factory dispatch: returns a configured provider instance.

    Phase 5 fills in the Real adapter classes (FocusNFeProvider,
    NFeIoProvider, etc.); for now only `fake` is implemented.

    Phase 5 wiring example::

        # In app/main.py lifespan_startup:
        nfe = make_nfe_provider(
            provider_name=settings.NFE_PROVIDER,
            api_key=settings.NFE_API_KEY,
            cnpj=settings.NFE_EMITTER_CNPJ,
        )
        app.state.nfe_provider = nfe
    """
    if provider_name == "fake":
        return FakeNFeProvider(reject_pattern=config.get("reject_pattern"))

    if provider_name == "focusnfe":
        # TODO(adconnect-phase-5): land FocusNFeProvider against Focus NFe's
        # JSON API. Fields: api_key, ambiente (homologacao|producao), cnpj.
        raise NotImplementedError(
            "FocusNFeProvider — author in Phase 5. "
            "Reference docs: https://focusnfe.com.br/doc/"
        )

    if provider_name == "nfeio":
        raise NotImplementedError("NFeIoProvider — Phase 5 candidate (not selected)")

    if provider_name == "enotas":
        raise NotImplementedError("ENotasProvider — Phase 5 candidate (not selected)")

    raise ValueError(
        f"Unknown NFe provider {provider_name!r}; "
        f"supported: fake, focusnfe, nfeio, enotas"
    )

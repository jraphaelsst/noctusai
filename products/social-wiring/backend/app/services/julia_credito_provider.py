"""Lais wave 13 -- the credit-analysis provider seam (contract 15 / 17).

`CreditoProvider` is the Protocol the flow depends on; `FakeCreditoProvider` (dev / tests, records every call so
a test can assert "no consent -> no call"), `CredAlugaProvider` (the REAL stub: the owner has not chosen the
production provider yet -- Lais uses CredAluga -- so it REFUSES, loudly, with "provedor nao configurado") and the
per-org factory `make_credito_provider`.

What a provider may see: `ConsultaCredito` -- the contato's name / phone / operacao / imovel codigo. The CPF is
NOT in it: the platform stores only a salted hash + the last 3 digits (contract 17, `lais_slots_sensiveis`), so a
provider that needs the CPF in clear cannot be served until the owner decides how it is captured (see the marker
on `CredAlugaProvider`).

What a provider returns: `ResultadoCredito(status, resumo)` -- `resumo` is ONE short sentence; the service stores
nothing else (no score, no income, no raw payload).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

logger = logging.getLogger(__name__)

NAO_CONFIGURADO = "provedor não configurado"
RESUMO_MAX = 200
STATUS_RESULTADO = ("aprovado", "reprovado", "pendente")


class CreditoNaoConfigurado(Exception, IntegrationNotConfigured):
    """No usable provider for this org (none chosen, unknown name, credentials missing, or the Real is a stub)."""

    def __init__(self, motivo: str = NAO_CONFIGURADO) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class CreditoProviderErro(Exception):
    """The provider answered with a failure / was unreachable. The message is safe to log, never to show a lead."""


@dataclass(frozen=True)
class ConsultaCredito:
    org_id: str
    contato_id: str
    nome: Optional[str]
    telefone_e164: Optional[str]
    operacao: Optional[str]
    codigo_imovel: Optional[str] = None


@dataclass(frozen=True)
class ResultadoCredito:
    status: Literal["aprovado", "reprovado", "pendente"]
    resumo: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUS_RESULTADO:
            raise ValueError(f"credit provider returned an unknown status {self.status!r}")


@runtime_checkable
class CreditoProvider(Protocol):
    nome: str

    async def analisar(self, consulta: ConsultaCredito) -> ResultadoCredito: ...


@dataclass
class FakeCreditoProvider:
    """Deterministic provider: answers `resultado` (default approve), optionally raising `erro`.
    `chamadas` records every consulta so tests can prove the provider was (not) called."""

    nome: str = "fake"
    resultado: Literal["aprovado", "reprovado", "pendente"] = "aprovado"
    resumo: Optional[str] = None
    erro: Optional[Exception] = None
    chamadas: list[ConsultaCredito] = field(default_factory=list)

    async def analisar(self, consulta: ConsultaCredito) -> ResultadoCredito:
        self.chamadas.append(consulta)
        if self.erro is not None:
            raise self.erro
        return ResultadoCredito(self.resultado, self.resumo or f"Análise {self.resultado} (fake).")


class CredAlugaProvider:
    """REAL stub -- always refuses. NOC-REMEDIATE[lais-credito-provider]: the production provider is not chosen
    (Lais uses CredAluga). To build the Real the owner must provide: (1) the provider decision (CredAluga or
    another) and its API documentation / sandbox; (2) one credential PER ORG stored in the per-org credentials
    store under `api_key:credito_provider` (token/contract id issued to each imobiliaria); (3) how the lead's CPF
    reaches the provider -- the platform keeps only a hash + last 3 digits, so either the CPF is captured in clear
    at consent time and passed straight through (never persisted), or the provider's hosted consent/CPF link is
    sent to the lead; (4) the provider's status vocabulary mapped to aprovado | reprovado | pendente — 2026-10-15"""

    nome = "credaluga"

    def __init__(self, credencial: Optional[str] = None) -> None:
        self._credencial = credencial

    async def analisar(self, consulta: ConsultaCredito) -> ResultadoCredito:
        motivo = NAO_CONFIGURADO if not self._credencial else f"{NAO_CONFIGURADO} (integração real pendente)"
        raise CreditoNaoConfigurado(motivo)


#: provider name -> builder `(credencial) -> CreditoProvider`. A new provider is one line here + one adapter.
PROVIDERS: dict[str, Callable[[Optional[str]], CreditoProvider]] = {
    "fake": lambda _cred: FakeCreditoProvider(),
    "credaluga": lambda cred: CredAlugaProvider(cred),
}
PROVIDERS_CONHECIDOS: tuple[str, ...] = tuple(PROVIDERS)


def make_credito_provider(nome: Optional[str], *, credencial: Optional[str] = None, allow_fake: bool = False) -> CreditoProvider:
    """The org's provider. Pure factory: `nome` is the org config's `provider`; a missing / unknown name, or the
    Fake outside dev (it would approve every lead), raises `CreditoNaoConfigurado` -- never a silent default."""
    if not nome:
        raise CreditoNaoConfigurado()
    if nome == "fake" and not allow_fake:
        raise CreditoNaoConfigurado(f"{NAO_CONFIGURADO} (fake não permitido em produção)")
    builder = PROVIDERS.get(nome)
    if builder is None:
        raise CreditoNaoConfigurado(f"{NAO_CONFIGURADO} (provedor desconhecido)")
    return builder(credencial)


def credencial_da_org(org_id: Any, *, cfg: Any = None, store: Any = None) -> Optional[str]:
    """The org's LOCAL `api_key:credito_provider` secret, or None. Local tier only (like the agents token): a
    platform/env fallback would let one org's contract answer for another's."""
    from app.services import api_keys_store
    from app.services.credential_vault import EncryptionNotConfigured

    if store is None:
        try:
            store = api_keys_store.build_api_key_store(
                encryption_key=getattr(cfg, "encryption_key", None) if cfg is not None else None
            )
        except EncryptionNotConfigured:
            logger.warning("lais credito: ENCRYPTION_KEY unusable -- cannot read the provider credential")
            return None
    stored = api_keys_store.read_local_api_key(store, str(org_id), CREDENCIAL_KEY_NAME)
    return ((stored.tokens or {}).get("value") if stored else None) or None


CREDENCIAL_KEY_NAME = "credito_provider"

__all__ = [
    "CREDENCIAL_KEY_NAME", "CredAlugaProvider", "ConsultaCredito", "CreditoNaoConfigurado", "CreditoProvider",
    "CreditoProviderErro", "FakeCreditoProvider", "NAO_CONFIGURADO", "PROVIDERS", "PROVIDERS_CONHECIDOS",
    "RESUMO_MAX", "ResultadoCredito", "credencial_da_org", "make_credito_provider",
]

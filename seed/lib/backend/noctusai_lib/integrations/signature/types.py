"""E-signature value objects + Protocol — contract §1.1.

`SignatureAdapter` turns a generated document (PDF bytes, never a URL —
`DocumentoParaAssinar.conteudo`) plus a list of signers into a provider
envelope, and later resolves that envelope's lifecycle (pending → signed
copy back). Two adapters satisfy this Protocol: `FakeSignatureAdapter`
(deterministic, in-memory) and `D4SignAdapter` (the real D4Sign wire
calls) — see `fake.py` / `real.py`. Product code imports the Protocol +
value objects + `make_signature_adapter` from this package's `__init__`,
never `httpx` and never a vendor name.

Provider scope is D4Sign only (`projects/signature-integration-CONTRACT.md`
§0) — the Protocol admits ClickSign/DocuSign later without a shape change,
since nothing here is D4Sign-specific.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Protocol, Sequence, runtime_checkable

PapelSignatario = Literal[
    "comprador", "vendedor", "testemunha", "interveniente", "intermediario"
]
StatusAssinatura = Literal[
    "pendente", "parcial", "concluido", "cancelado", "expirado"
]


@dataclass(frozen=True)
class Signatario:
    """One person who must sign, as the caller knows them.

    `cpf` is digits-or-formatted, 11 characters when digits-only, and MUST
    pass `noctusai_lib.integrations.documents.cpf.is_valid` before this
    value object is handed to an adapter — validation lives at the product
    boundary (contract §3.1's `ASSINATURA_SIGNATARIO_INVALIDO`), not here,
    so this type stays a plain carrier.
    """

    nome: str
    email: str
    cpf: str
    papel: PapelSignatario
    ordem: int = 0  # 0 = no enforced signing order


@dataclass(frozen=True)
class DocumentoParaAssinar:
    """The document to send. `conteudo` is the ACTUAL bytes — never a URL.

    Contract F1: erp's scaffold posted `{"url": ...}` to a provider whose
    real upload contract is a binary body; that document was never
    uploaded. Every adapter here uploads `conteudo` directly.
    """

    nome: str  # filename shown in the provider UI, e.g. "Promessa - v3.pdf"
    conteudo: bytes
    mime_type: str = "application/pdf"


@dataclass(frozen=True)
class SignatarioRemoto:
    """One signer as the provider tracks them, once an envelope exists."""

    email: str
    external_id: str
    assinado_em: datetime | None = None


@dataclass(frozen=True)
class EnvelopeCriado:
    """Return value of `criar_envelope` — the freshly created envelope."""

    external_id: str  # provider's document/envelope id
    link_assinatura: str  # https URL an operator can open
    provedor: str  # "d4sign"
    signatarios: tuple[SignatarioRemoto, ...]
    criado_em: datetime  # tz-aware UTC


@dataclass(frozen=True)
class EventoAssinatura:
    """A point-in-time read of an envelope's status — `consultar`,
    `validar_webhook` and `cancelar` all return this shape."""

    external_id: str
    status: StatusAssinatura
    provedor: str
    ocorrido_em: datetime
    signatarios: tuple[SignatarioRemoto, ...] = ()
    documento_assinado_disponivel: bool = False


@runtime_checkable
class SignatureAdapter(Protocol):
    """The one seam every consumer reaches for. `FakeSignatureAdapter` and
    `D4SignAdapter` both satisfy this exactly — a consumer selects once
    (via `make_signature_adapter`) and never branches on which it got."""

    async def criar_envelope(
        self,
        documento: DocumentoParaAssinar,
        signatarios: Sequence[Signatario],
        *,
        mensagem: str | None = None,
    ) -> EnvelopeCriado:
        """`mensagem` is the operator-typed text from contract §3.1's
        optional `mensagem` field (<= 500 chars). `None` ⇒ the adapter's
        own default copy. Surfaced as a keyword-only Protocol parameter
        2026-09-17 — earlier versions of this Protocol had no way for a
        caller to pass it through at all, so `D4SignAdapter` always sent a
        fixed string regardless of what an operator typed
        (`NOC-REMEDIATE[d4sign-sendtosigner-message]`, contract §1.6)."""
        ...

    async def consultar(self, external_id: str) -> EventoAssinatura: ...

    async def baixar_assinado(self, external_id: str) -> bytes:
        """Raises `DocumentoAssinadoIndisponivel` when status != "concluido"."""
        ...

    def validar_webhook(
        self, corpo: bytes, cabecalhos: Mapping[str, str]
    ) -> EventoAssinatura:
        """Verify + parse an inbound webhook. Raises `WebhookInvalido` on a
        bad/absent signature. NEVER returns None. Synchronous on purpose:
        it is pure verification + parsing, no I/O."""
        ...

    async def cancelar(self, external_id: str, motivo: str) -> EventoAssinatura: ...


def is_forward_transition(
    atual: str | None, novo: str, *, terminais: frozenset[str]
) -> bool:
    """True iff assigning `novo` over `atual` does not regress a terminal
    status.

    Shared between every consumer of a `validar_webhook` event —
    `card_hub.assinatura_service.aplicar_evento_webhook` (social-wiring,
    consuming `StatusAssinatura` directly) and erp-imobiliario's
    `AssinaturaService.processar_webhook` (which maps `StatusAssinatura`
    onto its own `assinaturas.status` vocabulary first). Deliberately
    vocabulary-agnostic — the two consumers do not share a status enum, so
    each supplies its own `terminais` set rather than this function
    picking one.

    A webhook body carries no nonce/timestamp (`WebhookInvalido` only
    proves the HMAC matched, not that the delivery is fresh), so a
    captured `concluido`/`assinado` delivery replayed AFTER a later
    `cancelado` — or the reverse — stays "validly signed" forever at the
    transport layer. Without this guard, whichever delivery a provider
    happens to retry last silently wins, regressing a finished contract
    (2026-09-20 wiring audit, task 4).

    Once `atual` is a member of `terminais`, only re-applying the SAME
    value is accepted (an idempotent replay of the terminal event
    itself) — any different value is a regression and this returns
    False so the caller can refuse it and log loudly instead of
    silently overwriting the row.

    `atual=None` (no prior row / first event) is always a forward
    transition.
    """
    if atual is None:
        return True
    if atual not in terminais:
        return True
    return novo == atual


__all__ = [
    "DocumentoParaAssinar",
    "EnvelopeCriado",
    "EventoAssinatura",
    "PapelSignatario",
    "Signatario",
    "SignatarioRemoto",
    "SignatureAdapter",
    "StatusAssinatura",
    "is_forward_transition",
]

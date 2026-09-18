"""`FakeSignatureAdapter` — deterministic, stateful in-memory double.

Contract §1.3. No IO, no vendor, no network: a consumer's tests drive the
whole lifecycle (create → sign → download, or create → cancel, or an
inbound webhook) against the exact `SignatureAdapter` Protocol the real
D4Sign adapter satisfies. This is the seed's default (`make_signature_
adapter(real=False)` — the seed's own posture) and the only adapter that
may exist without any credential.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Mapping, get_args

from noctusai_lib.integrations.signature.exceptions import (
    DocumentoAssinadoIndisponivel,
    WebhookInvalido,
)
from noctusai_lib.integrations.signature.types import (
    DocumentoParaAssinar,
    EnvelopeCriado,
    EventoAssinatura,
    Signatario,
    SignatarioRemoto,
    StatusAssinatura,
)

_STATUS_VALORES = set(get_args(StatusAssinatura))


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _header(cabecalhos: Mapping[str, str], nome: str) -> str | None:
    """Case-insensitive header lookup — webhook frameworks hand this in
    with whatever casing the transport used."""
    alvo = nome.lower()
    for chave, valor in cabecalhos.items():
        if chave.lower() == alvo:
            return valor
    return None


@dataclass
class _EnvelopeState:
    """Internal, mutable — never handed to a caller. `consultar` /
    `validar_webhook` build a fresh, frozen `EventoAssinatura` from this
    each time."""

    documento: DocumentoParaAssinar
    signatarios: list[SignatarioRemoto] = field(default_factory=list)
    status: StatusAssinatura = "pendente"
    criado_em: datetime = field(default_factory=_agora)
    #: the caller-supplied `criar_envelope(..., mensagem=...)`, or `None`
    #: when the caller relied on the adapter's own default copy — a test
    #: double, not a real adapter, so recorded verbatim rather than
    #: substituted with a default (that substitution is `D4SignAdapter`'s
    #: job, contract §1.6 marker `d4sign-sendtosigner-message`).
    mensagem: str | None = None


class FakeSignatureAdapter:
    """Deterministic double satisfying `SignatureAdapter` exactly.

    - `criar_envelope` → `external_id = "fake-" + sha256(nome + emails)[:16]`.
    - `marcar_assinado(external_id, email)` (test-only helper) flips one
      signatario; all signed ⇒ `concluido`. The contract's shorthand
      (`marcar_assinado(email)`) omits `external_id`, but a single Fake
      instance tracks every envelope it created in a test — without the id
      two contracts signed by the same e-mail address would collide, so
      this keeps `external_id` as the first argument.
    - `baixar_assinado` returns fake bytes once `concluido`, else raises.
    - `validar_webhook` accepts `{"external_id": ..., "status": ...}` JSON
      with header `x-fake-signature: sha256(corpo).hexdigest()` — no
      secret, since this is the trusted dev/test double, not a security
      boundary. Anything else raises `WebhookInvalido`.
    """

    def __init__(self) -> None:
        self._envelopes: dict[str, _EnvelopeState] = {}
        #: Calls recorded for test assertions, mirroring the sibling Fakes
        #: in this package (`documents.fake.FakeIdentityExtractor.calls`).
        self.calls: list[tuple[str, str]] = []

    def _requer(self, external_id: str) -> _EnvelopeState:
        estado = self._envelopes.get(external_id)
        if estado is None:
            raise KeyError(
                f"FakeSignatureAdapter: unknown external_id {external_id!r}"
            )
        return estado

    async def criar_envelope(
        self,
        documento: DocumentoParaAssinar,
        signatarios: list[Signatario],
        *,
        mensagem: str | None = None,
    ) -> EnvelopeCriado:
        self.calls.append(("criar_envelope", documento.nome))
        material = documento.nome.encode("utf-8") + b"|" + b",".join(
            s.email.encode("utf-8") for s in signatarios
        )
        external_id = "fake-" + hashlib.sha256(material).hexdigest()[:16]
        remotos = tuple(
            SignatarioRemoto(email=s.email, external_id=f"{external_id}-{i}")
            for i, s in enumerate(signatarios)
        )
        criado_em = _agora()
        self._envelopes[external_id] = _EnvelopeState(
            documento=documento,
            signatarios=list(remotos),
            criado_em=criado_em,
            mensagem=mensagem,
        )
        return EnvelopeCriado(
            external_id=external_id,
            link_assinatura=f"https://fake.assinatura.local/{external_id}",
            provedor="d4sign",
            signatarios=remotos,
            criado_em=criado_em,
        )

    def marcar_assinado(self, external_id: str, email: str) -> None:
        """Test-only. Flips the named signatory's `assinado_em`; once every
        signatory in the envelope has signed, `status` becomes `concluido`
        (partially signed ⇒ `parcial`)."""
        estado = self._requer(external_id)
        atualizados = [
            replace(s, assinado_em=_agora()) if s.email == email else s
            for s in estado.signatarios
        ]
        estado.signatarios = atualizados
        if all(s.assinado_em is not None for s in atualizados):
            estado.status = "concluido"
        elif any(s.assinado_em is not None for s in atualizados):
            estado.status = "parcial"

    async def consultar(self, external_id: str) -> EventoAssinatura:
        estado = self._requer(external_id)
        return EventoAssinatura(
            external_id=external_id,
            status=estado.status,
            provedor="d4sign",
            ocorrido_em=_agora(),
            signatarios=tuple(estado.signatarios),
            documento_assinado_disponivel=estado.status == "concluido",
        )

    async def baixar_assinado(self, external_id: str) -> bytes:
        estado = self._requer(external_id)
        if estado.status != "concluido":
            raise DocumentoAssinadoIndisponivel(
                f"external_id={external_id} status={estado.status!r} != 'concluido'"
            )
        return b"%PDF-1.4 fake-signed ..."

    def validar_webhook(
        self, corpo: bytes, cabecalhos: Mapping[str, str]
    ) -> EventoAssinatura:
        assinatura = _header(cabecalhos, "x-fake-signature")
        if not assinatura:
            raise WebhookInvalido("missing x-fake-signature header")
        esperado = hashlib.sha256(corpo).hexdigest()
        if not hmac.compare_digest(esperado, assinatura):
            raise WebhookInvalido("x-fake-signature did not verify")

        try:
            payload = json.loads(corpo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebhookInvalido(f"malformed webhook body: {exc}") from exc

        external_id = payload.get("external_id")
        status = payload.get("status")
        if not external_id or status not in _STATUS_VALORES:
            raise WebhookInvalido(
                f"webhook body missing/invalid external_id or status: {payload!r}"
            )

        estado = self._envelopes.get(external_id)
        signatarios = tuple(estado.signatarios) if estado is not None else ()
        return EventoAssinatura(
            external_id=external_id,
            status=status,
            provedor="d4sign",
            ocorrido_em=_agora(),
            signatarios=signatarios,
            documento_assinado_disponivel=status == "concluido",
        )

    async def cancelar(self, external_id: str, motivo: str) -> EventoAssinatura:
        estado = self._requer(external_id)
        estado.status = "cancelado"
        return EventoAssinatura(
            external_id=external_id,
            status="cancelado",
            provedor="d4sign",
            ocorrido_em=_agora(),
            signatarios=tuple(estado.signatarios),
        )


__all__ = ["FakeSignatureAdapter"]

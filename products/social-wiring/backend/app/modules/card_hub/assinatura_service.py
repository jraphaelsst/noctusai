"""E-signature envelopes for a contract version — migration 134.

Contract: `projects/signature-integration-CONTRACT.md` §3.1-§3.4. Consumes
`noctusai_lib.integrations.signature` (Protocol + Fake + Real(D4Sign) +
factory, shipped by slice S-A) — this module never imports `httpx` and
never names D4Sign outside `card_hub.deps.get_signature_adapter_factory`'s
own `make_signature_adapter(real=True, ...)` call.

WHAT THIS OWNS
--------------
- `enviar` (§3.1): read a GENERATED version's PDF bytes off storage, hand
  them to the provider, and record the resulting envelope. Sets the
  contract's `status='enviado_assinatura'` in the SAME call — the FE never
  sets that itself.
- `obter` (§3.2): the most recent envelope for a contract, read-only.
  NEVER calls the provider — the webhook is the source of truth for an
  envelope's status, not a page render.
- `cancelar` (§3.3): cancel the live envelope at the provider and put the
  contract back in `em_revisao`.
- `aplicar_evento_webhook` (§3.4): the state-after a webhook delivers —
  idempotent on `(provedor, external_id, status)`, and on `concluido`
  downloads the signed PDF and stores it as a NEW version
  (`contratos_service.nova_versao_assinada`, `origem='assinado'`).

🔴 NO 2xx MAY EVER CARRY A MOCKED ENVELOPE (contract F1). `ProvedorNao
Configurado` from the adapter factory maps to the typed 422 below — it is
never swallowed into a fake success.

ERROR-TABLE ORDERING (§3.1) IS LOAD-BEARING
--------------------------------------------
`enviar` checks in the table's own order: signatários shape (400) ->
contrato/versão existence (404) -> an already-live envelope (409) -> the
version's provenance (422 `ASSINATURA_VERSAO_NAO_GERADA`) -> only THEN
does it ask `card_hub.deps.get_signature_adapter_factory` to build the
adapter, so `ProvedorNaoConfigurado` (422) and a provider transport error
(502) are always the LAST things checked, never ahead of a genuinely
malformed request's own 400/404/409.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional, Sequence
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.signature import (
    DocumentoAssinadoIndisponivel,
    DocumentoParaAssinar,
    EnvelopeRecusado,
    EventoAssinatura,
    ProvedorIndisponivel,
    ProvedorNaoConfigurado,
    Signatario,
    SignatureAdapter,
    is_forward_transition,
)
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub.deps import SignatureAdapterFactory
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

TABLE = "atendimento_contrato_assinaturas"

#: Loose on purpose — "is this shaped like an email" only. A stricter
#: check belongs to a mail-sending concern this module doesn't have; the
#: point here is to reject an obviously-wrong value with the contract's
#: OWN 400, not pydantic's generic 422 (`EmailStr` at the schema layer
#: would raise before this service ever ran, the wrong error shape).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_ENVELOPE_VIVO_STATUSES = ("pendente", "parcial")

#: Statuses `aplicar_evento_webhook` treats as terminal for
#: `is_forward_transition` — once a row reaches one of these, only a
#: repeat of the exact same value is accepted (2026-09-20 wiring audit,
#: task 4; the D4Sign webhook body carries no nonce/timestamp, so a
#: captured `cancelado` delivery replayed after the row already reached
#: `concluido` — or the reverse — must not silently win).
_ENVELOPE_TERMINAL_STATUSES = frozenset({"concluido", "cancelado", "expirado"})


def _t(client: Any, name: str = TABLE):
    return table_reads.table(client, name)


# ─── error taxonomy (contract §3.1 / §3.2 / §3.3 / §3.4) ──────────────────


class AssinaturaSemSignatarios(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="ASSINATURA_SEM_SIGNATARIOS",
            message="Informe ao menos um signatário.",
            status_code=400,
        )


class AssinaturaSignatarioInvalido(AppException):
    def __init__(self, nome: str) -> None:
        super().__init__(
            code="ASSINATURA_SIGNATARIO_INVALIDO",
            message=f"CPF ou e-mail inválido para {nome}.",
            status_code=400,
            details={"nome": nome},
        )


class ContratoNaoEncontrado(AppException):
    def __init__(self, contrato_id: Any) -> None:
        super().__init__(
            code="CONTRATO_NAO_ENCONTRADO",
            message="Contrato não encontrado.",
            status_code=404,
            details={"id": str(contrato_id)},
        )


class VersaoNaoEncontrada(AppException):
    def __init__(self, versao_id: Any) -> None:
        super().__init__(
            code="VERSAO_NAO_ENCONTRADA",
            message="Versão não encontrada.",
            status_code=404,
            details={"id": str(versao_id)},
        )


class AssinaturaJaEnviada(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="ASSINATURA_JA_ENVIADA",
            message="Este contrato já está em assinatura.",
            status_code=409,
        )


class AssinaturaVersaoNaoGerada(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="ASSINATURA_VERSAO_NAO_GERADA",
            message="Só uma versão gerada pode ir para assinatura.",
            status_code=422,
        )


class AssinaturaProvedorNaoConfigurado(AppException):
    def __init__(self, faltando: Sequence[str]) -> None:
        super().__init__(
            code="ASSINATURA_PROVEDOR_NAO_CONFIGURADO",
            message="Configure a plataforma de assinatura em Configurações.",
            status_code=422,
            details={"faltando": list(faltando)},
        )


class AssinaturaProvedorErro(AppException):
    def __init__(self, provedor_mensagem: Optional[str]) -> None:
        super().__init__(
            code="ASSINATURA_PROVEDOR_ERRO",
            message="A plataforma de assinatura recusou o envio.",
            status_code=502,
            details={"provedor_mensagem": provedor_mensagem},
        )


class AssinaturaNaoEncontrada(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="ASSINATURA_NAO_ENCONTRADA",
            message="Nenhuma assinatura em andamento para este contrato.",
            status_code=404,
        )


class AssinaturaNaoCancelavel(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="ASSINATURA_NAO_CANCELAVEL",
            message="Esta assinatura não pode mais ser cancelada.",
            status_code=409,
        )


class WebhookAssinaturaInvalida(AppException):
    """§3.4 — invalid/absent provider signature. Always 401, never 200."""

    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_ASSINATURA_INVALIDA",
            message="assinatura do webhook inválida",
            status_code=401,
        )


# ─── shared reads ──────────────────────────────────────────────────────────


def _live_envelope(client: Any, org_id: UUID, contrato_id: UUID) -> Optional[dict]:
    rows = (
        _t(client)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("contrato_id", str(contrato_id))
        .in_("status", list(_ENVELOPE_VIVO_STATUSES))
        .execute()
    ).data or []
    return rows[0] if rows else None


def _latest_envelope(client: Any, org_id: UUID, contrato_id: UUID) -> Optional[dict]:
    """The most recently created envelope for this contract, ANY status.

    §3.2's "live envelope" carries `concluido_em`/`cancelado_motivo` in its
    response, which only mean anything for a concluded/cancelled row — so
    "live" there reads as "current", not "in-flight". A contract can be
    RE-sent after a cancellation (§2's partial-unique index only forbids
    two simultaneously in-flight envelopes), so more than one row can exist
    per contract over time; this is the one to show.
    """
    rows = (
        _t(client).select("*").eq("org_id", str(org_id)).eq("contrato_id", str(contrato_id)).execute()
    ).data or []
    if not rows:
        return None
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[0]


def buscar_por_external_id(client: Any, provedor: str, external_id: str) -> Optional[dict]:
    """Webhook-only lookup — keyed on the provider's own id, unscoped by
    org (the webhook does not know the org until THIS lookup answers it).
    Migration 134's `(provedor, external_id)` UNIQUE index is exactly what
    this keys on."""
    rows = (
        _t(client).select("*").eq("provedor", provedor).eq("external_id", external_id).execute()
    ).data or []
    return rows[0] if rows else None


def _validar_signatarios(signatarios: Sequence[dict]) -> None:
    if not signatarios:
        raise AssinaturaSemSignatarios()
    for s in signatarios:
        nome = (s.get("nome") or "").strip()
        email = s.get("email") or ""
        cpf = s.get("cpf") or ""
        if not _EMAIL_RE.match(email) or not _cpf_is_valid(cpf):
            raise AssinaturaSignatarioInvalido(nome or "signatário")


def _sig_out(row: dict) -> dict:
    return {
        "assinatura_id": row["id"],
        "external_id": row["external_id"],
        "link_assinatura": row["link_assinatura"],
        "provedor": row["provedor"],
        "status": row["status"],
        "signatarios": row.get("signatarios") or [],
        "enviado_em": row["enviado_em"],
    }


def _sig_out_detalhe(row: dict) -> dict:
    return {
        **_sig_out(row),
        "concluido_em": row.get("concluido_em"),
        "versao_assinada_id": row.get("versao_assinada_id"),
        "cancelado_motivo": row.get("cancelado_motivo"),
    }


# ─── §3.1 — POST .../assinatura ─────────────────────────────────────────


async def enviar(
    client: Any,
    storage: StorageBackend,
    adapter_factory: SignatureAdapterFactory,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    versao_id: UUID,
    signatarios: Sequence[dict],
    mensagem: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    _validar_signatarios(signatarios)

    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    try:
        contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    except NotFoundError:
        raise ContratoNaoEncontrado(contrato_id) from None

    try:
        versao = contratos_svc.VERSOES_STORE.exigir(client, org_id, contrato_id, versao_id)
    except NotFoundError:
        raise VersaoNaoEncontrada(versao_id) from None

    if _live_envelope(client, org_id, contrato_id) is not None:
        raise AssinaturaJaEnviada()

    if versao.get("origem") != "gerado":
        raise AssinaturaVersaoNaoGerada()

    blob = await storage.get(bucket=contratos_svc.VERSOES_STORE.bucket, key=versao["storage_path"])
    if blob is None:
        # The DB row exists but its bytes are gone — a storage-layer defect,
        # not a business rule this contract names. Same 404 shape
        # `DocumentoStore.exigir` gives a missing/foreign id.
        raise NotFoundError(contratos_svc.VERSOES_STORE.table, str(versao_id))

    documento = DocumentoParaAssinar(
        nome=versao.get("nome_original") or f"contrato-{contrato_id}.pdf",
        conteudo=blob.data,
        mime_type="application/pdf",
    )
    remetentes = [
        Signatario(
            nome=s["nome"], email=s["email"], cpf=s["cpf"], papel=s["papel"],
            ordem=s.get("ordem", 0),
        )
        for s in signatarios
    ]

    try:
        adapter: SignatureAdapter = adapter_factory(str(org_id))
    except ProvedorNaoConfigurado as exc:
        raise AssinaturaProvedorNaoConfigurado(exc.faltando) from exc

    try:
        envelope = await adapter.criar_envelope(documento, remetentes)
    except (ProvedorIndisponivel, EnvelopeRecusado) as exc:
        raise AssinaturaProvedorErro(exc.details.get("provedor_mensagem")) from exc

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "contrato_id": str(contrato_id),
        "versao_id": str(versao_id),
        "provedor": envelope.provedor,
        "external_id": envelope.external_id,
        "link_assinatura": envelope.link_assinatura,
        "status": "pendente",
        "signatarios": [
            {"email": r.email, "external_id": r.external_id, "assinado_em": None}
            for r in envelope.signatarios
        ],
        "enviado_em": envelope.criado_em.isoformat(),
        "enviado_por": str(usuario_id) if usuario_id else None,
        "concluido_em": None,
        "versao_assinada_id": None,
        "cancelado_motivo": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    _t(client).insert(row).execute()

    # 🔴 The version's content was READ (its bytes were sent to the
    # provider) — same LGPD access-log call `contratos_service.url_versao`
    # makes for a content read, keyed to this version's own id.
    contratos_svc.VERSOES_STORE.log_acesso(client, org_id, versao_id, usuario_id, "view")

    # State-after (§3.1 point 3): the contract is ALREADY 'enviado_assinatura'
    # when this returns — the FE never sets it.
    contratos_svc.definir_status(
        client, org_id, contrato_id, "enviado_assinatura", usuario_id=usuario_id
    )

    return _sig_out(row)


# ─── §3.2 — GET .../assinatura (read-only, never calls the provider) ────


def obter(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    try:
        contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    except NotFoundError:
        raise ContratoNaoEncontrado(contrato_id) from None

    row = _latest_envelope(client, org_id, contrato_id)
    if row is None:
        raise AssinaturaNaoEncontrada()
    return _sig_out_detalhe(row)


# ─── §3.3 — POST .../assinatura/cancelar ────────────────────────────────


async def cancelar(
    client: Any,
    adapter_factory: SignatureAdapterFactory,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[Any],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    try:
        contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    except NotFoundError:
        raise ContratoNaoEncontrado(contrato_id) from None

    row = _latest_envelope(client, org_id, contrato_id)
    if row is None:
        raise AssinaturaNaoEncontrada()
    if row["status"] not in _ENVELOPE_VIVO_STATUSES:
        raise AssinaturaNaoCancelavel()

    try:
        adapter: SignatureAdapter = adapter_factory(str(org_id))
    except ProvedorNaoConfigurado as exc:
        raise AssinaturaProvedorNaoConfigurado(exc.faltando) from exc

    try:
        await adapter.cancelar(row["external_id"], motivo)
    except (ProvedorIndisponivel, EnvelopeRecusado) as exc:
        raise AssinaturaProvedorErro(exc.details.get("provedor_mensagem")) from exc

    _t(client).update(
        {"status": "cancelado", "cancelado_motivo": motivo, "updated_at": now_iso()}
    ).eq("id", row["id"]).execute()

    # State-after (§3.3): the contract returns to 'em_revisao'.
    contratos_svc.definir_status(
        client, org_id, contrato_id, "em_revisao", usuario_id=usuario_id
    )

    atualizado = dict(row)
    atualizado["status"] = "cancelado"
    atualizado["cancelado_motivo"] = motivo
    return _sig_out_detalhe(atualizado)


# ─── §3.4 — webhook state-after ─────────────────────────────────────────


async def aplicar_evento_webhook(
    client: Any,
    storage: StorageBackend,
    adapter: SignatureAdapter,
    evento: EventoAssinatura,
) -> dict:
    """The state-after a verified webhook event applies.

    Idempotent on `(provedor, external_id, status)` — a row whose `status`
    already equals the event's is a no-op, so a retried provider delivery
    never double-processes (never inserts a second signed version, never
    re-fires the contract status transition).

    An unknown `external_id` is NOT re-raised as an error — a retired
    envelope must not make the provider retry forever (contract §3.4).

    🔴 Monotonic once terminal (2026-09-20 wiring audit, task 4).
    `is_forward_transition` refuses any event that would move a row OFF
    a terminal status (`_ENVELOPE_TERMINAL_STATUSES`) onto a DIFFERENT
    value — a captured `cancelado` delivery replayed after `concluido`
    already landed (or the reverse) is logged loudly and dropped, never
    applied. A webhook body carries no nonce/timestamp, so `WebhookInvalido`
    proving the HMAC matched says nothing about the delivery being fresh.
    """
    row = buscar_por_external_id(client, evento.provedor, evento.external_id)
    if row is None:
        logger.warning(
            "assinatura webhook: unknown external_id=%s provedor=%s — ignored",
            evento.external_id, evento.provedor,
        )
        return {"ok": True, "ignorado": True}

    if row["status"] == evento.status:
        return {"ok": True}

    if not is_forward_transition(
        row["status"], evento.status, terminais=_ENVELOPE_TERMINAL_STATUSES
    ):
        logger.warning(
            "assinatura webhook: refusing regressive transition "
            "external_id=%s provedor=%s atual=%s novo=%s — assinatura_id=%s "
            "ja esta em estado terminal, evento ignorado",
            evento.external_id, evento.provedor, row["status"], evento.status,
            row["id"],
        )
        return {"ok": True, "ignorado": True, "motivo": "transicao_regressiva"}

    org_id = UUID(str(row["org_id"]))
    contrato_id = UUID(str(row["contrato_id"]))

    # Persisted BEFORE the download is attempted — a download failure below
    # must not lose the event (contract §3.4).
    patch: dict[str, Any] = {"status": evento.status, "updated_at": now_iso()}
    if evento.status == "concluido":
        patch["concluido_em"] = now_iso()
    _t(client).update(patch).eq("id", row["id"]).execute()

    if evento.status != "concluido":
        return {"ok": True}

    try:
        pdf_bytes = await adapter.baixar_assinado(evento.external_id)
    except (DocumentoAssinadoIndisponivel, ProvedorIndisponivel, EnvelopeRecusado) as exc:
        logger.error(
            "NOC-REMEDIATE[assinatura-download-retry]: signed PDF download "
            "failed for external_id=%s (assinatura_id=%s, contrato_id=%s): "
            "%s — event persisted as concluido, versao_assinada_id left NULL.",
            evento.external_id, row["id"], contrato_id, exc,
        )
        return {"ok": True}

    contrato = contratos_svc.obter_contrato(client, org_id, contrato_id)
    atendimento_id = UUID(str(contrato["atendimento_id"]))

    versao = await contratos_svc.nova_versao_assinada(
        client,
        storage,
        org_id,
        atendimento_id,
        contrato_id,
        data=pdf_bytes,
        content_type="application/pdf",
        filename=f"contrato-assinado-{evento.external_id}.pdf",
        usuario_id=None,
    )

    _t(client).update(
        {"versao_assinada_id": versao["id"], "updated_at": now_iso()}
    ).eq("id", row["id"]).execute()

    # State-after point 4: the contract itself becomes 'assinado'. No
    # usuario_id — a webhook is a system event, not an operator action.
    contratos_svc.definir_status(client, org_id, contrato_id, "assinado")

    return {"ok": True}


__all__ = [
    "TABLE",
    "AssinaturaJaEnviada",
    "AssinaturaNaoCancelavel",
    "AssinaturaNaoEncontrada",
    "AssinaturaProvedorErro",
    "AssinaturaProvedorNaoConfigurado",
    "AssinaturaSemSignatarios",
    "AssinaturaSignatarioInvalido",
    "AssinaturaVersaoNaoGerada",
    "ContratoNaoEncontrado",
    "VersaoNaoEncontrada",
    "WebhookAssinaturaInvalida",
    "aplicar_evento_webhook",
    "buscar_por_external_id",
    "cancelar",
    "enviar",
    "obter",
]

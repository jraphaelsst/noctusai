"""Optional e-signature for a contract, through the seed's `SignatureAdapter` Protocol (D4Sign real, Fake in tests).

Flow: `render_document` (stores `document_body`) -> `send_for_signature` (the rendered document becomes
the envelope; status `pendente`) -> the provider's webhook / `sync_signature` moves it to
`parcial` / `concluido` -> on `concluido` the contract records `signed_at` and, when it was still a
DRAFT, ACTIVATES (billing starts). The host mounts the provider webhook route itself and calls
`handle_signature_webhook`; this module never touches `httpx` or a vendor name.

Mounted by the router only when the host passes a `signature` adapter; without one every signature
route answers 409 `assinatura_nao_configurada` (never a silent 200).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.signature import DocumentoParaAssinar, Signatario
from noctusai_lib.integrations.signature.types import EventoAssinatura
from noctusai_lib.primitives.identificador import cpf_dv_valido

from . import documents
from ._common import Scope, now_iso, to_date
from .contracts import activate_contract, contract_lines, get_contract
from .documents import DocumentRenderer
from .errors import (
    ASSINATURA_EM_ANDAMENTO, ASSINATURA_NAO_CONFIGURADA, DOCUMENTO_NAO_GERADO, SIGNATARIO_INVALIDO, conflict, invalid,
)
from .types import ContractStatus, SignatureStatus

logger = logging.getLogger(__name__)

_LIVE = (SignatureStatus.PENDING.value, SignatureStatus.PARTIAL.value)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ROLES = ("comprador", "vendedor", "testemunha", "interveniente", "intermediario")


def require_adapter(adapter: Any) -> Any:
    if adapter is None:
        raise conflict(ASSINATURA_NAO_CONFIGURADA, "A assinatura eletrônica não está configurada neste ambiente.")
    return adapter


def render_document(s: Scope, contract_id: Any, template: Optional[str] = None) -> dict:
    """Render the contract text from `template` (or the default) and store it as `document_body`."""
    c = get_contract(s, contract_id)
    body = documents.render_contract_text(c, contract_lines(s, contract_id), template)
    s.tbl("contracts").update({"document_body": body, "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(contract_id)).execute()
    return {**c, "document_body": body}


def _signer(raw: Mapping[str, Any], idx: int) -> Signatario:
    cpf = re.sub(r"\D", "", str(raw.get("cpf") or ""))
    if len(cpf) != 11 or not cpf_dv_valido(cpf):
        raise invalid(f"signers.{idx}.cpf", "CPF do signatário inválido.", code=SIGNATARIO_INVALIDO)
    if not _EMAIL.match(str(raw.get("email") or "")):
        raise invalid(f"signers.{idx}.email", "E-mail do signatário inválido.", code=SIGNATARIO_INVALIDO)
    role = raw.get("role") or "comprador"
    if role not in _ROLES:
        raise invalid(f"signers.{idx}.role", "Papel do signatário inválido.", code=SIGNATARIO_INVALIDO)
    return Signatario(nome=str(raw["name"]).strip(), email=str(raw["email"]).strip(), cpf=cpf, papel=role, ordem=int(raw.get("order") or 0))


async def send_for_signature(s: Scope, adapter: Any, contract_id: Any, signers: list[Mapping[str, Any]], *,
                             message: Optional[str] = None, renderer: DocumentRenderer = documents.plain_text_document) -> dict:
    adapter = require_adapter(adapter)
    c = get_contract(s, contract_id)
    if c["status"] in ("terminated", "expired"):
        raise conflict("contrato_finalizado", "O contrato está encerrado.")
    if c.get("signature_status") in _LIVE:
        raise conflict(ASSINATURA_EM_ANDAMENTO, "Já existe uma assinatura em andamento para este contrato.")
    if not c.get("document_body"):
        raise conflict(DOCUMENTO_NAO_GERADO, "Gere o documento do contrato antes de enviar para assinatura.")
    parsed = [_signer(sg, i) for i, sg in enumerate(signers)]
    data, mime = renderer(c["title"], c["document_body"])
    envelope = await adapter.criar_envelope(
        DocumentoParaAssinar(nome=f"{c.get('number') or c['title']}.{'pdf' if mime == 'application/pdf' else 'txt'}", conteudo=data, mime_type=mime),
        parsed, mensagem=message,
    )
    patch = {"signature_provider": envelope.provedor, "signature_external_id": envelope.external_id,
             "signature_status": SignatureStatus.PENDING.value, "signed_at": None, "updated_at": now_iso()}
    s.tbl("contracts").update(patch).eq("org_id", s.org_id).eq("id", str(contract_id)).execute()
    return {**c, **patch, "signature_link": envelope.link_assinatura}


def apply_signature_event(s: Scope, contract: Mapping[str, Any], event: EventoAssinatura, *, billing: Any = None) -> dict:
    """Fold a provider status into the contract; forward-only (a stale event never regresses a `concluido`)."""
    order = {SignatureStatus.NONE.value: 0, SignatureStatus.PENDING.value: 1, SignatureStatus.PARTIAL.value: 2}
    terminal = (SignatureStatus.DONE.value, SignatureStatus.CANCELLED.value, SignatureStatus.EXPIRED.value)
    current = contract.get("signature_status") or SignatureStatus.NONE.value
    new = event.status
    if current in terminal or (new not in terminal and order.get(new, 0) <= order.get(current, 0)):
        return dict(contract)
    patch: dict[str, Any] = {"signature_status": new, "updated_at": now_iso()}
    if new == SignatureStatus.DONE.value:
        patch["signed_at"] = event.ocorrido_em.astimezone(timezone.utc).isoformat() if isinstance(event.ocorrido_em, datetime) else now_iso()
    s.tbl("contracts").update(patch).eq("org_id", s.org_id).eq("id", str(contract["id"])).execute()
    out = {**contract, **patch}
    if new == SignatureStatus.DONE.value and contract["status"] == ContractStatus.DRAFT.value and billing is not None:
        out = activate_contract(s, contract["id"], billing=billing)
    return out


async def sync_signature(s: Scope, adapter: Any, contract_id: Any, *, billing: Any = None) -> dict:
    adapter = require_adapter(adapter)
    c = get_contract(s, contract_id)
    if not c.get("signature_external_id"):
        raise conflict(ASSINATURA_NAO_CONFIGURADA, "Este contrato não foi enviado para assinatura.")
    return apply_signature_event(s, c, await adapter.consultar(c["signature_external_id"]), billing=billing)


async def cancel_signature(s: Scope, adapter: Any, contract_id: Any, reason: str) -> dict:
    adapter = require_adapter(adapter)
    c = get_contract(s, contract_id)
    if c.get("signature_status") not in _LIVE:
        raise conflict(ASSINATURA_NAO_CONFIGURADA, "Não há assinatura em andamento.")
    event = await adapter.cancelar(c["signature_external_id"], reason)
    return apply_signature_event(s, c, event)


def handle_signature_webhook(db: Any, cfg: Any, adapter: Any, body: bytes, headers: Mapping[str, str], *, billing: Any = None) -> Optional[dict]:
    """The host's webhook route body: verify (raises `WebhookInvalido` -> the host answers 401), find the contract
    by `(provider, external_id)` ACROSS orgs (the webhook carries no org), apply. Returns the contract, or None if unknown."""
    event = adapter.validar_webhook(body, headers)
    resp = (db.table(cfg.table("contracts")).select("*").eq("signature_provider", event.provedor)
            .eq("signature_external_id", event.external_id).limit(1).execute())
    rows = resp.data or []
    if not rows:
        logger.warning("contracts: signature webhook for unknown envelope %s", event.external_id)
        return None
    contract = dict(rows[0])
    return apply_signature_event(Scope(db, cfg, str(contract["org_id"])), contract, event, billing=billing)


__all__ = ["apply_signature_event", "cancel_signature", "handle_signature_webhook", "render_document", "require_adapter",
           "send_for_signature", "sync_signature"]

"""
Assinatura Service — Business logic for digital signatures.

Handles sending documents for signing, processing webhook events,
status tracking, audit trail management, and signature summaries.

Signing itself is delegated to the seed `signature` IO module
(`noctusai_lib.integrations.signature`) via `make_signature_adapter` —
see `projects/signature-integration-CONTRACT.md` §0/§5. This file used to
own its own provider dispatch (`app.services.signature_provider`), which
never uploaded a real document to ClickSign, made no API call at all for
DocuSign while claiming `dry_run: False`, and posted a URL to a D4Sign
endpoint whose real contract is a binary upload. That file is deleted;
this service now only owns erp's OWN signing domain (the `assinaturas`
table, its status lifecycle, the audit trail) and asks the seed adapter to
do the actual provider call.

🔴 No silent fallback. `make_signature_adapter(real=True, ...)` never
returns a Fake — an org with no D4Sign credentials gets
`ProvedorNaoConfigurado` (mapped to HTTP by the router), never a mock
envelope. v1 supports D4Sign only; any other `provedor` (including the
legacy `"interno"` mock option) is refused the same way, naming what is
unsupported.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.dependencies import first_or_none
from noctusai_lib.integrations.signature import (
    PROVEDORES_SUPORTADOS,
    DocumentoParaAssinar,
    EventoAssinatura,
    ProvedorNaoConfigurado,
    Signatario,
    SignatureAdapter,
    is_forward_transition,
    make_signature_adapter,
)

logger = logging.getLogger(__name__)

#: The Class-B DI test seam (`KB § PATTERNS/backend/di-test-seam.md`) —
#: tests inject a factory that returns `FakeSignatureAdapter()` (directly,
#: or by calling `make_signature_adapter(resolver=...)` with a fake
#: resolver) instead of patching this module's imports.
SignatureAdapterFactory = Callable[..., SignatureAdapter]


class AssinaturaService:
    """Service for digital signature business logic."""

    #: Seed `StatusAssinatura` (`pendente`/`parcial`/`concluido`/
    #: `cancelado`/`expirado` — `noctusai_lib.integrations.signature.
    #: types.StatusAssinatura`) -> erp's own `assinaturas.status` CHECK
    #: vocabulary (`pendente`/`enviado`/`assinado`/`recusado`/`expirado`/
    #: `cancelado`, `migrations/004_mvp_expansion.sql`).
    #:
    #: D4Sign's webhook has no distinct "signer declined" code
    #: (`real.py::_STATUS_POR_ID` maps every `type_post` onto one of the
    #: 5 seed statuses only) — a refusal in the D4Sign UI surfaces here as
    #: the envelope going `cancelado`, so `recusado` is never assigned via
    #: this path (it stays reachable only through erp's own future
    #: `AssinaturaUpdate.status` field, if that's ever wired to this
    #: table). `parcial`/`pendente` (envelope created / partially signed,
    #: not yet fully done) both land on `enviado` — erp's own vocabulary
    #: has no partial-signature state, and "sent, awaiting completion" is
    #: the accurate description of both (2026-09-20 wiring audit, task 3).
    D4SIGN_STATUS_MAP: Dict[str, str] = {
        "pendente": "enviado",
        "parcial": "enviado",
        "concluido": "assinado",
        "cancelado": "cancelado",
        "expirado": "expirado",
    }

    #: Once an assinatura reaches one of these, `is_forward_transition`
    #: refuses any webhook event that would move it to a DIFFERENT status
    #: (2026-09-20 wiring audit, task 4) — a D4Sign webhook body carries
    #: no nonce/timestamp, so a captured delivery replayed after the row
    #: already reached a later terminal state would otherwise regress it
    #: forever (e.g. a replayed `type_post=5` "cancelado" landing after
    #: `concluido` already flipped the row to `assinado`).
    TERMINAL_STATUSES = frozenset({"assinado", "recusado", "expirado", "cancelado"})

    def __init__(
        self,
        db_client,
        user_id: str,
        org_id: Optional[str] = None,
        adapter_factory: SignatureAdapterFactory = make_signature_adapter,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.db = db_client
        self.user_id = user_id
        self.org_id = org_id
        #: Defaults to the seed's real factory. Production code always
        #: calls it with `real=True` — the Fake only ever appears here
        #: when a test injects a different `adapter_factory`.
        self._adapter_factory = adapter_factory
        #: Optional injected `httpx.AsyncClient` for tests (mirrors
        #: `app.services.certidoes_service._fetch_certidao`'s seam) — None
        #: in production, where a short-lived client is opened per call.
        self._http_client = http_client

    async def _baixar_documento(self, documento_url: str) -> bytes:
        """Fetch the document's actual bytes from storage.

        The seed's `DocumentoParaAssinar.conteudo` is real bytes, never a
        URL (contract F1) — erp's request only carries a `documento_url`,
        so this is the mechanical step that bridges the two. Raises
        `httpx.HTTPError` on failure; the router maps that to a 502.
        """
        if self._http_client is not None:
            resp = await self._http_client.get(documento_url)
            resp.raise_for_status()
            return resp.content

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(documento_url)
            resp.raise_for_status()
            return resp.content

    async def preparar_envio(
        self,
        documento_nome: str,
        documento_url: Optional[str],
        signatarios: List[Dict[str, str]],
        provedor: str = "d4sign",
        contrato_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a signature request and send it to the configured provider.

        Args:
            documento_nome: Name of the document to sign
            documento_url: URL of the document file — its bytes are
                downloaded and uploaded to the provider
            signatarios: List of dicts with nome, email, papel
            provedor: Signing provider. v1 supports "d4sign" only.
            contrato_id: Optional linked contract ID

        Returns:
            Created assinatura record, or None if the insert returned
            nothing.

        Raises:
            ProvedorNaoConfigurado: `provedor` isn't `d4sign` (naming it as
                unsupported), or `d4sign` credentials are missing for this
                org (naming which ones).
            ValueError: `documento_url` is missing — there is no document
                to send.
            httpx.HTTPError: the document could not be downloaded.
            ProvedorIndisponivel / EnvelopeRecusado: the provider rejected
                or could not process the request.
        """
        if provedor not in PROVEDORES_SUPORTADOS:
            raise ProvedorNaoConfigurado(
                [
                    f"provedor '{provedor}' não é suportado nesta versão "
                    f"(suportado: {', '.join(PROVEDORES_SUPORTADOS)})"
                ],
                provedor=provedor,
            )

        if not documento_url:
            raise ValueError(
                "documento_url é obrigatório para enviar um documento para assinatura"
            )

        conteudo = await self._baixar_documento(documento_url)
        documento = DocumentoParaAssinar(nome=documento_nome, conteudo=conteudo)

        # NOC-REMEDIATE[erp-assinatura-cpf]: erp does not collect a signer
        # CPF today (its request schema has no such field) and D4Sign's
        # real wire calls (real.py's createlist) do not consume it either
        # — only `email` goes out. `cpf=""` is a safe placeholder until the
        # product needs certificate-based (ICP-Brasil) signing, at which
        # point erp's own request/DB schema needs the field, not just this
        # adapter call.
        seed_signatarios = [
            Signatario(
                nome=s.get("nome", ""),
                email=s.get("email", ""),
                cpf="",
                papel=s.get("papel", "testemunha"),
            )
            for s in signatarios
        ]

        adapter = self._adapter_factory(real=True, provedor=provedor, org_id=self.org_id)
        envelope = await adapter.criar_envelope(documento, seed_signatarios)

        now = datetime.now(timezone.utc).isoformat()

        # Prepare signatarios with pending status
        signatarios_com_status = []
        for s in signatarios:
            signatarios_com_status.append({
                **s,
                "status": "pendente",
                "assinado_em": None,
            })

        # Initial audit trail entry
        historico_inicial = [{
            "evento": "enviado",
            "descricao": f"Documento enviado para assinatura via {provedor}",
            "usuario_id": self.user_id,
            "data": now,
        }]

        data = {
            "documento_nome": documento_nome,
            "documento_url": documento_url,
            "contrato_id": contrato_id,
            "status": "enviado",
            "provedor": provedor,
            "link_assinatura": envelope.link_assinatura,
            "external_id": envelope.external_id,
            "signatarios": signatarios_com_status,
            "historico": historico_inicial,
            "data_envio": now,
        }

        result = self.db.table("assinaturas").insert(data).execute()
        row = first_or_none(result)
        return row

    async def processar_webhook(
        self,
        evento: EventoAssinatura,
    ) -> Optional[Dict[str, Any]]:
        """
        Process a verified D4Sign webhook event.

        `evento` is already HMAC-verified + parsed — see
        `app.routers.assinaturas.processar_webhook`, which delegates both
        to the seed adapter's `validar_webhook` (`noctusai_lib.
        integrations.signature.real.D4SignAdapter`) rather than
        re-implementing D4Sign's form-urlencoded wire shape here
        (2026-09-20 wiring audit, task 3).

        Looks the row up by `external_id` — migration 047's column,
        written at send time (`preparar_envio` above) and, until this
        fix, never read by anything — rather than erp's own `id` (D4Sign
        has no way to know that internal id).

        🔴 Monotonic once terminal (task 4). `is_forward_transition`
        refuses any event that would move a row OFF a `TERMINAL_STATUSES`
        member onto a DIFFERENT status — see that constant's docstring
        for why a captured webhook delivery can otherwise regress a
        finished contract forever.

        Note: this only updates erp's own record from the verified event;
        it does not call back into the seed adapter. Pulling the signed
        document via `adapter.baixar_assinado` and storing it is out of
        this slice's scope (`projects/signature-integration-CONTRACT.md`
        §5 — adapter swap, not a redesign of erp's signing domain).

        Args:
            evento: The verified webhook event.

        Returns:
            Updated assinatura record, the UNCHANGED record when the
            transition was refused (regressive) or the status was
            unrecognised, or None if no row matches `evento.external_id`.
        """
        result = self.db.table("assinaturas").select("*").eq(
            "external_id", evento.external_id
        ).single().execute()

        if not result.data:
            logger.warning(
                f"Webhook: assinatura com external_id={evento.external_id} nao encontrada"
            )
            return None

        assinatura = result.data
        now = datetime.now(timezone.utc).isoformat()

        novo_status = self.D4SIGN_STATUS_MAP.get(evento.status)
        if not novo_status:
            logger.warning(
                f"Webhook: status desconhecido '{evento.status}' para "
                f"external_id={evento.external_id}"
            )
            return assinatura

        status_atual = assinatura.get("status")
        if not is_forward_transition(
            status_atual, novo_status, terminais=self.TERMINAL_STATUSES
        ):
            logger.warning(
                "Webhook: transicao regressiva recusada para "
                f"external_id={evento.external_id} "
                f"(assinatura_id={assinatura.get('id')}): "
                f"atual={status_atual!r} novo={novo_status!r}"
            )
            return assinatura

        # Build audit trail entry
        historico = assinatura.get("historico", []) or []
        historico.append({
            "evento": evento.status,
            "descricao": f"Evento de webhook D4Sign: {evento.status}",
            "dados": None,
            "data": now,
        })

        # Build update payload
        update_data: Dict[str, Any] = {
            "status": novo_status,
            "historico": historico,
            "updated_at": now,
        }

        # Set data_assinatura if fully signed
        if novo_status == "assinado":
            update_data["data_assinatura"] = now

        updated = self.db.table("assinaturas").update(update_data).eq(
            "id", assinatura["id"]
        ).execute()
        row = first_or_none(updated)

        return row

    def get_resumo(self, assinaturas: List[Dict]) -> Dict[str, Any]:
        """
        Calculate signature summary counts by status.

        Args:
            assinaturas: List of assinatura records

        Returns:
            Dict with counts: pendentes, enviadas, assinadas, recusadas, expiradas, canceladas, total
        """
        pendentes = 0
        enviadas = 0
        assinadas = 0
        recusadas = 0
        expiradas = 0
        canceladas = 0

        for a in assinaturas:
            status = a.get("status", "")
            if status == "pendente":
                pendentes += 1
            elif status == "enviado":
                enviadas += 1
            elif status == "assinado":
                assinadas += 1
            elif status == "recusado":
                recusadas += 1
            elif status == "expirado":
                expiradas += 1
            elif status == "cancelado":
                canceladas += 1

        return {
            "pendentes": pendentes,
            "enviadas": enviadas,
            "assinadas": assinadas,
            "recusadas": recusadas,
            "expiradas": expiradas,
            "canceladas": canceladas,
            "total": len(assinaturas),
        }

    async def cancelar(self, assinatura_id: str) -> Optional[Dict[str, Any]]:
        """
        Cancel a signing request.

        Sets status to 'cancelado' and appends cancellation to the audit trail.
        Local-only, same as before the adapter swap — erp never called out
        to the provider to cancel (there was no such call in the original
        `signature_provider.py` either); it only ever updated its own row.

        Args:
            assinatura_id: ID of the assinatura to cancel

        Returns:
            Updated assinatura record or None if not found
        """
        # Fetch current record
        result = self.db.table("assinaturas").select("*").eq(
            "id", assinatura_id
        ).single().execute()

        if not result.data:
            return None

        assinatura = result.data
        now = datetime.now(timezone.utc).isoformat()

        # Cannot cancel an already completed signature
        current_status = assinatura.get("status", "")
        if current_status in ("assinado", "cancelado"):
            logger.warning(
                f"Tentativa de cancelar assinatura {assinatura_id} com status '{current_status}'"
            )
            return None

        # Append cancellation to audit trail
        historico = assinatura.get("historico", []) or []
        historico.append({
            "evento": "cancelado",
            "descricao": "Assinatura cancelada pelo usuario",
            "usuario_id": self.user_id,
            "data": now,
        })

        update_data = {
            "status": "cancelado",
            "historico": historico,
            "updated_at": now,
        }

        updated = self.db.table("assinaturas").update(update_data).eq(
            "id", assinatura_id
        ).execute()
        row = first_or_none(updated)

        return row

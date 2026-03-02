"""
Assinatura Service — Business logic for digital signatures.

Handles sending documents for signing, processing webhook events,
status tracking, audit trail management, and signature summaries.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class AssinaturaService:
    """Service for digital signature business logic."""

    # Map provider webhook events to internal status values
    EVENT_STATUS_MAP = {
        "assinado": "assinado",
        "signed": "assinado",
        "recusado": "recusado",
        "refused": "recusado",
        "declined": "recusado",
        "expirado": "expirado",
        "expired": "expirado",
        "cancelado": "cancelado",
        "canceled": "cancelado",
    }

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    async def preparar_envio(
        self,
        documento_nome: str,
        documento_url: Optional[str],
        signatarios: List[Dict[str, str]],
        provedor: str = "interno",
        contrato_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a signature request and send to the configured provider.

        When provider credentials are configured (org_settings or env),
        sends the document to ClickSign/DocuSign/D4Sign. Otherwise falls
        back to internal mock signing with placeholder links.

        Args:
            documento_nome: Name of the document to sign
            documento_url: URL of the document file
            signatarios: List of dicts with nome, email, papel
            provedor: Signing provider (interno, clicksign, docusign, d4sign)
            contrato_id: Optional linked contract ID

        Returns:
            Created assinatura record or None on failure
        """
        from app.services.signature_provider import (
            SignatureProviderConfig, enviar_para_assinatura,
        )

        now = datetime.now(timezone.utc).isoformat()

        # Send to external provider (or fall back to internal)
        provider_config = SignatureProviderConfig(self.db)
        provider_result = await enviar_para_assinatura(
            provedor, documento_nome, documento_url, signatarios, provider_config
        )

        link_assinatura = provider_result.get("link_assinatura", "")
        external_id = provider_result.get("external_id", "")

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
            "dry_run": provider_result.get("dry_run", False),
        }]

        data = {
            "documento_nome": documento_nome,
            "documento_url": documento_url,
            "contrato_id": contrato_id,
            "status": "enviado",
            "provedor": provedor,
            "link_assinatura": link_assinatura,
            "external_id": external_id,
            "signatarios": signatarios_com_status,
            "historico": historico_inicial,
            "data_envio": now,
        }

        result = self.db.table("assinaturas").insert(data).execute()
        row = first_or_none(result)
        return row

    async def processar_webhook(
        self,
        assinatura_id: str,
        evento: str,
        dados: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Process a signing provider webhook event.

        Maps the event to an internal status, updates the assinatura record,
        and appends the event to the audit trail.

        Args:
            assinatura_id: ID of the assinatura to update
            evento: Event type from the provider
            dados: Optional additional event data

        Returns:
            Updated assinatura record or None if not found
        """
        # Fetch current record
        result = self.db.table("assinaturas").select("*").eq(
            "id", assinatura_id
        ).single().execute()

        if not result.data:
            logger.warning(f"Webhook: assinatura {assinatura_id} nao encontrada")
            return None

        assinatura = result.data
        now = datetime.now(timezone.utc).isoformat()

        # Map event to status
        novo_status = self.EVENT_STATUS_MAP.get(evento.lower())
        if not novo_status:
            logger.warning(f"Webhook: evento desconhecido '{evento}' para assinatura {assinatura_id}")
            novo_status = assinatura.get("status", "enviado")

        # Build audit trail entry
        historico = assinatura.get("historico", []) or []
        historico.append({
            "evento": evento,
            "descricao": f"Evento de webhook: {evento}",
            "dados": dados,
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

            # Update individual signatario status if email provided in dados
            if dados and dados.get("email"):
                signatarios = assinatura.get("signatarios", []) or []
                for s in signatarios:
                    if s.get("email") == dados["email"]:
                        s["status"] = "assinado"
                        s["assinado_em"] = now
                update_data["signatarios"] = signatarios

        updated = self.db.table("assinaturas").update(update_data).eq(
            "id", assinatura_id
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

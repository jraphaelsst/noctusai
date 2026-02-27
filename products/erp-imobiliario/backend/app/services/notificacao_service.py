"""
Notification Service — creates and manages user notifications.

Provides helpers to create notifications from business events
(new lead, contract signed, payment overdue, etc.).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Points map for actions that trigger notifications
NOTIFICATION_TYPES = {
    "novo_lead": "Novo lead recebido",
    "proposta_recebida": "Nova proposta recebida",
    "proposta_aceita": "Proposta aceita",
    "contrato_assinado": "Contrato assinado",
    "pagamento_atrasado": "Pagamento em atraso",
    "vistoria_agendada": "Vistoria agendada",
    "comissao_aprovada": "Comissão aprovada",
    "meta_atingida": "Meta atingida",
    "documento_assinado": "Documento assinado",
    "chamado_aberto": "Novo chamado no portal",
    "whatsapp_recebido": "Nova mensagem WhatsApp",
    "lead_facebook": "Novo lead do Facebook",
}


async def criar_notificacao(
    supabase,
    org_id: str,
    user_id: str,
    tipo: str,
    titulo: str,
    mensagem: Optional[str] = None,
    link: Optional[str] = None,
) -> dict:
    """Create a notification for a user."""
    data = {
        "org_id": org_id,
        "user_id": user_id,
        "tipo": tipo,
        "titulo": titulo,
        "mensagem": mensagem,
        "link": link,
    }
    try:
        result = supabase.table("notificacoes").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        logger.warning(f"Failed to create notification: {e}")
        return data


async def notificar_equipe(
    supabase,
    org_id: str,
    user_ids: list[str],
    tipo: str,
    titulo: str,
    mensagem: Optional[str] = None,
    link: Optional[str] = None,
) -> int:
    """Create notifications for multiple users at once."""
    rows = [
        {
            "org_id": org_id,
            "user_id": uid,
            "tipo": tipo,
            "titulo": titulo,
            "mensagem": mensagem,
            "link": link,
        }
        for uid in user_ids
    ]
    try:
        result = supabase.table("notificacoes").insert(rows).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.warning(f"Failed to notify team: {e}")
        return 0

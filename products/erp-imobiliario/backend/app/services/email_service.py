"""
Email Service — Business logic for email sending, template rendering, and statistics.

Handles email record creation, template variable substitution, client history,
and aggregate statistics. SMTP sending is a placeholder that logs intent
without actually dispatching messages (ready for future integration).
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Regex for {{variable}} placeholders
VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class EmailService:
    """Service for CRM email operations."""

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        cliente_id: Optional[str] = None,
        corpo_html: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create an email record with status 'enviado'.

        SMTP sending is a placeholder — logs the intent but does not actually
        dispatch the message. Replace the logging call with a real SMTP/API
        integration when ready.

        Args:
            destinatario: Recipient email address
            assunto: Email subject
            corpo: Plain-text body
            cliente_id: Optional associated client ID
            corpo_html: Optional HTML body
            template_id: Optional template used to compose the email

        Returns:
            Created email record dict, or None on failure.
        """
        # Placeholder: log intent instead of sending via SMTP
        logger.info(
            f"[EMAIL DRY-RUN] Para: {destinatario} | Assunto: {assunto} | "
            f"Cliente: {cliente_id or 'N/A'}"
        )

        email_data: Dict[str, Any] = {
            "remetente": self.user_id,
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo": corpo,
            "direcao": "enviado",
            "status": "enviado",
        }

        if cliente_id:
            email_data["cliente_id"] = cliente_id
        if corpo_html:
            email_data["corpo_html"] = corpo_html
        if template_id:
            email_data["template_id"] = template_id

        result = self.db.table("emails").insert(email_data).select().single().execute()
        return result.data

    def aplicar_template(
        self,
        template_id: str,
        variaveis_dict: Dict[str, str],
    ) -> Optional[Dict[str, str]]:
        """
        Fetch a template and replace {{variavel}} placeholders with values.

        Args:
            template_id: ID of the email template
            variaveis_dict: Mapping of variable names to replacement values

        Returns:
            Dict with rendered 'assunto' and 'corpo', or None if template not found.
        """
        result = self.db.table("email_templates").select("*").eq(
            "id", template_id
        ).eq("ativo", True).single().execute()

        if not result.data:
            return None

        template = result.data

        def _replace(text: str) -> str:
            def replacer(match):
                var_name = match.group(1)
                if var_name in variaveis_dict:
                    return str(variaveis_dict[var_name])
                return match.group(0)
            return VARIABLE_PATTERN.sub(replacer, text)

        return {
            "assunto": _replace(template["assunto"]),
            "corpo": _replace(template["corpo"]),
        }

    def get_historico_cliente(self, cliente_id: str) -> List[Dict[str, Any]]:
        """
        Return all emails associated with a client, newest first.

        Args:
            cliente_id: Client UUID

        Returns:
            List of email records ordered by created_at descending.
        """
        result = self.db.table("emails").select("*").eq(
            "cliente_id", cliente_id
        ).order("created_at", desc=True).execute()

        return result.data or []

    def get_estatisticas(self) -> Dict[str, Any]:
        """
        Compute aggregate email statistics for the current organisation.

        Returns:
            Dict with total_enviados, total_abertos, taxa_abertura, and total_templates.
        """
        # Count emails
        emails_result = self.db.table("emails").select("status").execute()
        emails = emails_result.data or []

        total_enviados = len(emails)
        total_abertos = sum(1 for e in emails if e.get("status") == "aberto")
        taxa_abertura = round(
            (total_abertos / total_enviados * 100) if total_enviados > 0 else 0.0, 2
        )

        # Count active templates
        templates_result = self.db.table("email_templates").select(
            "id", count="exact"
        ).eq("ativo", True).execute()
        total_templates = (
            templates_result.count
            if templates_result.count is not None
            else len(templates_result.data or [])
        )

        return {
            "total_enviados": total_enviados,
            "total_abertos": total_abertos,
            "taxa_abertura": taxa_abertura,
            "total_templates": total_templates,
        }

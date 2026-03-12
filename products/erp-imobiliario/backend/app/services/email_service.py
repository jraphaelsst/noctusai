"""
Email Service — Business logic for email sending, template rendering, and statistics.

Handles email record creation, template variable substitution, client history,
and aggregate statistics. Uses Resend API for actual delivery when configured,
falls back to dry-run mode when API key is not set.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none
from app.services.credential_resolver import resolve_credential

logger = logging.getLogger(__name__)

# Regex for {{variable}} placeholders
VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _get_resend_config(org_id: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Resolve email provider config via the standard credential chain.
    Returns dict with api_key, from_email, from_name or None if unconfigured.
    """
    api_key = resolve_credential("resend_api_key", org_id)
    if not api_key:
        return None

    from_email = resolve_credential("email_from", org_id) or "noreply@noctus.app"
    from_name = resolve_credential("email_from_name", org_id) or "NoctusAI ERP"

    return {"api_key": api_key, "from_email": from_email, "from_name": from_name}


async def _send_via_resend(
    config: Dict[str, str],
    to: str,
    subject: str,
    text: str,
    html: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email via the Resend API. Returns the API response."""
    import httpx

    payload: Dict[str, Any] = {
        "from": f"{config['from_name']} <{config['from_email']}>",
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


class EmailService:
    """Service for CRM email operations."""

    def __init__(self, db_client, user_id: str, org_id: Optional[str] = None):
        self.db = db_client
        self.user_id = user_id
        self.org_id = org_id

    async def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        cliente_id: Optional[str] = None,
        corpo_html: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create an email record and send via Resend if configured.

        When no Resend API key is found (org_settings, platform_settings, or env),
        operates in dry-run mode — the email is recorded but not dispatched.

        Returns:
            Created email record dict, or None on failure.
        """
        config = _get_resend_config(self.org_id)
        dry_run = config is None
        status = "enviado"
        external_id = None

        if dry_run:
            logger.info(
                f"[EMAIL DRY-RUN] Para: {destinatario} | Assunto: {assunto} | "
                f"Cliente: {cliente_id or 'N/A'}"
            )
        else:
            try:
                result = await _send_via_resend(config, destinatario, assunto, corpo, corpo_html)
                external_id = result.get("id")
                logger.info(f"[EMAIL] Enviado via Resend: {external_id} -> {destinatario}")
            except Exception as e:
                logger.error(f"[EMAIL] Falha ao enviar via Resend: {e}")
                status = "falha"

        email_data: Dict[str, Any] = {
            "remetente": self.user_id,
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo": corpo,
            "direcao": "enviado",
            "status": status,
        }

        if cliente_id:
            email_data["cliente_id"] = cliente_id
        if corpo_html:
            email_data["corpo_html"] = corpo_html
        if template_id:
            email_data["template_id"] = template_id
        if external_id:
            email_data["external_id"] = external_id

        result = self.db.table("emails").insert(email_data).execute()
        row = first_or_none(result)
        return row

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

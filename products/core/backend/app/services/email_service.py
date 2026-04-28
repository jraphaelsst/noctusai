"""
Email notification service for the NoctusAI Core platform.

Supports Resend as the transactional email provider.
Set RESEND_API_KEY in .env to enable. If not configured, emails are
logged but not sent (graceful degradation for local development).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_resend = None


def _get_resend():
    """Lazy-init the Resend client. Returns None if not configured."""
    global _resend
    if _resend is not None:
        return _resend

    try:
        import resend as _resend_module
        from app.config import settings
        api_key = getattr(settings, "resend_api_key", None)
        if not api_key:
            logger.info("RESEND_API_KEY not set — emails will be logged only")
            _resend = False
            return None
        _resend_module.api_key = api_key
        _resend = _resend_module
        return _resend
    except ImportError:
        logger.warning("resend package not installed — emails disabled")
        _resend = False
        return None


FROM_EMAIL = "NoctusAI <noreply@noctusai.com>"


def send_invitation_email(
    to: str,
    org_name: str,
    invite_token: str,
    invited_by: str,
    base_url: str = "http://localhost:5173",
) -> bool:
    """Send a team invitation email."""
    invite_url = f"{base_url}/invite/{invite_token}"
    subject = f"Convite para {org_name} — NoctusAI"
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Você foi convidado!</h2>
        <p><strong>{invited_by}</strong> convidou você para fazer parte da organização
        <strong>{org_name}</strong> na plataforma NoctusAI.</p>
        <p>
            <a href="{invite_url}"
               style="display: inline-block; padding: 12px 24px; background: #2563eb;
                      color: white; text-decoration: none; border-radius: 6px;">
                Aceitar Convite
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Este convite expira em 7 dias. Se você não solicitou, ignore este e-mail.
        </p>
    </div>
    """
    return _send(to, subject, html)


def send_welcome_email(to: str, user_name: str, org_name: str) -> bool:
    """Send a welcome email after signup."""
    subject = f"Bem-vindo à NoctusAI, {user_name}!"
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Bem-vindo à NoctusAI!</h2>
        <p>Olá <strong>{user_name}</strong>,</p>
        <p>Sua organização <strong>{org_name}</strong> foi criada com sucesso.</p>
        <p>Próximos passos:</p>
        <ol>
            <li>Complete o onboarding da sua organização</li>
            <li>Escolha um plano</li>
            <li>Convide sua equipe</li>
            <li>Ative seus produtos</li>
        </ol>
        <p>Acesse a plataforma para começar.</p>
    </div>
    """
    return _send(to, subject, html)


def send_billing_alert(
    to: str,
    event_type: str,
    org_name: str,
    details: Optional[dict] = None,
) -> bool:
    """Send a billing alert email (payment failed, subscription changed, etc.)."""
    details = details or {}

    subjects = {
        "invoice.payment_failed": f"Falha no pagamento — {org_name}",
        "customer.subscription.deleted": f"Assinatura cancelada — {org_name}",
        "customer.subscription.updated": f"Assinatura atualizada — {org_name}",
    }
    subject = subjects.get(event_type, f"Alerta de cobrança — {org_name}")

    messages = {
        "invoice.payment_failed": (
            "Houve uma falha no processamento do seu pagamento. "
            "Por favor, verifique seus dados de pagamento no portal de cobrança."
        ),
        "customer.subscription.deleted": (
            "Sua assinatura foi cancelada. Você pode reativar a qualquer momento "
            "na página de planos."
        ),
        "customer.subscription.updated": (
            "Sua assinatura foi atualizada com sucesso."
        ),
    }
    message = messages.get(event_type, "Houve uma alteração na sua cobrança.")

    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Alerta de Cobrança</h2>
        <p>Olá,</p>
        <p>{message}</p>
        <p><strong>Organização:</strong> {org_name}</p>
        <p style="color: #666; font-size: 14px;">
            Caso tenha dúvidas, entre em contato com o suporte.
        </p>
    </div>
    """
    return _send(to, subject, html)


def _send(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend or log it if not configured."""
    client = _get_resend()
    if not client:
        logger.info("Email (not sent — no provider): to=%s subject=%s", to, subject)
        return False

    try:
        client.Emails.send({
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent: to=%s subject=%s", to, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return False

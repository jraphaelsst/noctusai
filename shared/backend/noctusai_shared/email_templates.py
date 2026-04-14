"""
Shared email templates for the NoctusAI platform.

Product-agnostic email sending with configurable branding.
Uses Resend as the transactional email provider (graceful fallback
when RESEND_API_KEY is not set).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_resend = None


def _get_resend():
    """Lazy-init the Resend client. Returns None if not configured."""
    global _resend
    if _resend is not None:
        return _resend if _resend else None

    try:
        import resend as _resend_module
        import os
        api_key = os.environ.get("RESEND_API_KEY")
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


def send_product_invitation_email(
    to: str,
    product_name: str,
    org_name: str,
    role_label: str,
    invite_token: str,
    invited_by: str,
    base_url: str,
    *,
    accept_path: str = "/accept-invite",
) -> bool:
    """Send a product-level team invitation email.

    Args:
        to: Invitee email.
        product_name: Human-readable product name (e.g. "ERP Imobiliario").
        org_name: Organization name.
        role_label: Portuguese role label (e.g. "Corretor", "Terapeuta").
        invite_token: The unique invitation token.
        invited_by: Name of the person who sent the invite.
        base_url: Product frontend base URL (e.g. "https://erp.noctusai.com").
        accept_path: URL path for acceptance (default "/accept-invite").

    Returns:
        True if email was sent, False otherwise.
    """
    invite_url = f"{base_url}{accept_path}/{invite_token}"
    subject = f"Convite para {org_name} — {product_name}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 32px;">
            <h1 style="font-size: 24px; font-weight: 700; color: #111; margin: 0;">
                {product_name}
            </h1>
            <p style="font-size: 14px; color: #666; margin: 4px 0 0 0;">
                by NoctusAI
            </p>
        </div>

        <div style="background: #f8f9fa; border-radius: 12px; padding: 32px; text-align: center;">
            <h2 style="font-size: 20px; color: #111; margin: 0 0 12px 0;">
                Voce foi convidado!
            </h2>
            <p style="font-size: 15px; color: #444; margin: 0 0 8px 0;">
                <strong>{invited_by}</strong> convidou voce para fazer parte de
                <strong>{org_name}</strong> como <strong>{role_label}</strong>.
            </p>
            <p style="font-size: 14px; color: #666; margin: 0 0 24px 0;">
                Clique no botao abaixo para aceitar o convite e configurar sua conta.
            </p>
            <a href="{invite_url}"
               style="display: inline-block; padding: 14px 32px; background: #2563eb;
                      color: white; text-decoration: none; border-radius: 8px;
                      font-size: 15px; font-weight: 600;">
                Aceitar Convite
            </a>
        </div>

        <div style="margin-top: 24px; text-align: center;">
            <p style="font-size: 13px; color: #999;">
                Este convite expira em 7 dias. Se voce nao solicitou, ignore este email.
            </p>
            <p style="font-size: 12px; color: #bbb; margin-top: 16px;">
                NoctusAI — AI-powered digital products
            </p>
        </div>
    </div>
    """
    return _send(to, subject, html)


def send_password_reset_email(
    to: str,
    product_name: str,
    reset_url: str,
) -> bool:
    """Send a password reset email with product branding."""
    subject = f"Redefinir senha — {product_name}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 32px;">
            <h1 style="font-size: 24px; font-weight: 700; color: #111; margin: 0;">
                {product_name}
            </h1>
        </div>

        <div style="background: #f8f9fa; border-radius: 12px; padding: 32px; text-align: center;">
            <h2 style="font-size: 20px; color: #111; margin: 0 0 12px 0;">
                Redefinir sua senha
            </h2>
            <p style="font-size: 15px; color: #444; margin: 0 0 24px 0;">
                Recebemos uma solicitacao para redefinir a senha da sua conta.
                Clique no botao abaixo para criar uma nova senha.
            </p>
            <a href="{reset_url}"
               style="display: inline-block; padding: 14px 32px; background: #2563eb;
                      color: white; text-decoration: none; border-radius: 8px;
                      font-size: 15px; font-weight: 600;">
                Redefinir Senha
            </a>
        </div>

        <div style="margin-top: 24px; text-align: center;">
            <p style="font-size: 13px; color: #999;">
                Se voce nao solicitou a redefinicao, ignore este email.
            </p>
        </div>
    </div>
    """
    return _send(to, subject, html)

"""
Email Service — notification emails via Resend API.

Graceful degradation: when resend_api_key is not set, logs a dry-run
message and returns True (never crashes). All templates in Portuguese.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend API. Returns True on success or dry-run."""
    if not settings.resend_api_key:
        logger.info("[EMAIL DRY-RUN] to=%s subject=%s", to, subject)
        return True

    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from": f"{settings.email_from_name} <{settings.email_from}>",
            "to": [to],
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent: to=%s subject=%s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email: to=%s error=%s", to, e)
        return False


async def send_registration_email(email: str, nome: str, role: str) -> bool:
    """Welcome email after registration."""
    role_label = {
        "therapist": "Terapeuta",
        "patient": "Paciente",
        "clinic_admin": "Administrador de Clínica",
    }.get(role, role)

    html = f"""
    <h2>Bem-vindo(a) à NoctusAI Therapy, {nome}!</h2>
    <p>Seu cadastro como <strong>{role_label}</strong> foi recebido com sucesso.</p>
    <p>Em breve você receberá uma confirmação de aprovação.</p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, "Bem-vindo(a) à NoctusAI Therapy", html)


async def send_approval_email(
    email: str, nome: str, approved: bool, reason: Optional[str] = None,
) -> bool:
    """Notify user about approval or rejection."""
    if approved:
        html = f"""
        <h2>Parabéns, {nome}!</h2>
        <p>Seu cadastro foi <strong>aprovado</strong>. Você já pode acessar a plataforma.</p>
        <p>Atenciosamente,<br>{settings.email_from_name}</p>
        """
        subject = "Cadastro aprovado — NoctusAI Therapy"
    else:
        reason_text = f"<p><strong>Motivo:</strong> {reason}</p>" if reason else ""
        html = f"""
        <h2>Olá, {nome}</h2>
        <p>Infelizmente seu cadastro não foi aprovado neste momento.</p>
        {reason_text}
        <p>Caso tenha dúvidas, entre em contato com nosso suporte.</p>
        <p>Atenciosamente,<br>{settings.email_from_name}</p>
        """
        subject = "Cadastro não aprovado — NoctusAI Therapy"
    return await send_email(email, subject, html)


async def send_booking_confirmation(
    patient_email: str,
    therapist_name: str,
    scheduled_start: str,
    meeting_link: str,
) -> bool:
    """Confirm a session booking to the patient."""
    html = f"""
    <h2>Sessão agendada!</h2>
    <p>Sua sessão com <strong>{therapist_name}</strong> está confirmada.</p>
    <p><strong>Data/hora:</strong> {scheduled_start}</p>
    <p><strong>Link da sessão:</strong> <a href="{meeting_link}">{meeting_link}</a></p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(patient_email, "Sessão agendada — NoctusAI Therapy", html)


async def send_session_reminder(
    email: str,
    nome: str,
    therapist_name: str,
    scheduled_start: str,
    meeting_link: str,
    hours_before: int,
) -> bool:
    """Remind about an upcoming session."""
    html = f"""
    <h2>Lembrete de sessão</h2>
    <p>Olá, {nome}!</p>
    <p>Sua sessão com <strong>{therapist_name}</strong> começa em <strong>{hours_before} hora(s)</strong>.</p>
    <p><strong>Data/hora:</strong> {scheduled_start}</p>
    <p><strong>Link:</strong> <a href="{meeting_link}">{meeting_link}</a></p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, f"Lembrete: sessão em {hours_before}h", html)


async def send_cancellation_email(
    email: str, nome: str, scheduled_start: str, charged: bool,
) -> bool:
    """Notify about session cancellation."""
    charge_notice = (
        "<p><strong>Atenção:</strong> Como o cancelamento ocorreu fora do prazo, "
        "a cobrança será mantida conforme política de cancelamento.</p>"
        if charged
        else "<p>Nenhuma cobrança será realizada.</p>"
    )
    html = f"""
    <h2>Sessão cancelada</h2>
    <p>Olá, {nome}.</p>
    <p>A sessão agendada para <strong>{scheduled_start}</strong> foi cancelada.</p>
    {charge_notice}
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, "Sessão cancelada — NoctusAI Therapy", html)


async def send_summary_available(
    email: str, nome: str, session_date: str,
) -> bool:
    """Notify patient that their session summary is ready."""
    html = f"""
    <h2>Resumo da sessão disponível</h2>
    <p>Olá, {nome}!</p>
    <p>O resumo da sua sessão de <strong>{session_date}</strong> está disponível na plataforma.</p>
    <p>Acesse para conferir.</p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, "Resumo de sessão disponível", html)


async def send_refund_notification(
    email: str, nome: str, amount: str, approved: bool, reason: Optional[str] = None,
) -> bool:
    """Notify about refund decision."""
    if approved:
        html = f"""
        <h2>Reembolso aprovado</h2>
        <p>Olá, {nome}!</p>
        <p>Seu pedido de reembolso no valor de <strong>R$ {amount}</strong> foi aprovado.</p>
        <p>O valor será creditado em até 5 dias úteis.</p>
        <p>Atenciosamente,<br>{settings.email_from_name}</p>
        """
        subject = "Reembolso aprovado — NoctusAI Therapy"
    else:
        reason_text = f"<p><strong>Motivo:</strong> {reason}</p>" if reason else ""
        html = f"""
        <h2>Reembolso não aprovado</h2>
        <p>Olá, {nome}.</p>
        <p>Seu pedido de reembolso no valor de <strong>R$ {amount}</strong> não foi aprovado.</p>
        {reason_text}
        <p>Atenciosamente,<br>{settings.email_from_name}</p>
        """
        subject = "Reembolso não aprovado — NoctusAI Therapy"
    return await send_email(email, subject, html)


async def send_payout_notification(
    email: str, nome: str, amount: str, status: str,
) -> bool:
    """Notify therapist about payout status."""
    status_label = {
        "completed": "concluído",
        "pending": "pendente",
        "failed": "falhou",
    }.get(status, status)

    html = f"""
    <h2>Atualização de repasse</h2>
    <p>Olá, {nome}!</p>
    <p>Seu repasse no valor de <strong>R$ {amount}</strong> está com status: <strong>{status_label}</strong>.</p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, f"Repasse {status_label} — NoctusAI Therapy", html)


async def send_unread_message_notification(
    email: str, sender_name: str, preview: str,
) -> bool:
    """Notify about unread messages."""
    truncated = preview[:100] + "..." if len(preview) > 100 else preview
    html = f"""
    <h2>Nova mensagem</h2>
    <p>Você tem uma mensagem não lida de <strong>{sender_name}</strong>:</p>
    <blockquote>{truncated}</blockquote>
    <p>Acesse a plataforma para responder.</p>
    <p>Atenciosamente,<br>{settings.email_from_name}</p>
    """
    return await send_email(email, f"Mensagem de {sender_name} — NoctusAI Therapy", html)

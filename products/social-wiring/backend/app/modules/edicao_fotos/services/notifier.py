"""Batch-ready fan-out — the engine's `BatchReadyNotifier` port.

Three channels, one recipient set. Recipients: the batch's CREATOR
(always) plus every agency admin (`AGENCY_ADMIN_ROLES`) who opted in
(migration 131, `services/notificacoes_preferencias.py`) — resolves
NOC-REMEDIATE[edicao-fotos-notify-channels] (plan §1 "Notifications").

Both switches the owner defined are honoured here, before anything is
resolved or sent: the platform-wide `notificacoes_globais_ativas` and the
org's `notificacoes_ativas`. A switched-off notice is logged, not dropped
silently.

`InAppBatchReadyNotifier` (below, UNCHANGED — single creator row, in-app
only) is kept as the minimal building block + its existing test coverage;
`MultiChannelBatchReadyNotifier` is the real product wiring
(`services/ports.py`) and is a superset: every resolved recipient gets an
in-app row PLUS email (when they have one — always true, `noctus_users.
email` is `NOT NULL`) PLUS WhatsApp (only when they registered a number,
`services/notificacoes_preferencias.py` — `noctus_users` carries no phone
column at all).

Failure semantics differ ON PURPOSE between the two:
  - in-app RAISES on failure (unchanged) — the engine's `fotos.lote_pronto`
    handler is at-least-once and retries a notice that did not land, so a
    write failure here must abort the handler.
  - email/WhatsApp NEVER raise per-recipient — logged only, same contract
    as `app.services.notification_service.NotificationService` (a down
    WAHA session or a bounced email must not gate the batch's `pronto`
    transition, nor tank a sibling recipient's delivery).

Reuses, never reimplements: the seed email integration
(`noctusai_lib.integrations.email.send_to_one` — Resend/SMTP, 3-tier
credential chain, dry-run when unconfigured) and social-wiring's existing
WAHA sender (`noctusai_lib.integrations.whatsapp.get_whatsapp_client` +
`chat_id_for_phone` — the SAME factory `app.services.notification_service`
and `app.services.whatsapp_outbound` already use)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.photo_editing import BatchReadyNotice, PhotoEditingRepository
from noctusai_lib.integrations.whatsapp import chat_id_for_phone, get_whatsapp_client

from app.modules.edicao_fotos.services.notificacoes_preferencias import (
    NotificationPreferencesRepository,
)

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "system"
FEATURE = "edicao_fotos.lote_pronto"

#: `(to, subject, html, text, org_id) -> sent?` — DI seam for tests
#: (`senders are faked`); default wraps the seed email integration.
EmailSenderFn = Callable[..., Awaitable[bool]]


def batch_ready_message(notice: BatchReadyNotice) -> tuple[str, str]:
    """pt-BR title + body for a ready batch."""
    title = f"Lote pronto para revisão: {notice.nome}"
    body = f"{notice.aguardando_decisao} de {notice.total_fotos} foto(s) aguardam sua decisão."
    if notice.falhou:
        body += f" {notice.falhou} foto(s) falharam e podem ser retentadas."
    return title, body


class InAppBatchReadyNotifier:
    """Writes the creator's in-app notification through a `public`-scoped
    service-role client (the table lives in Core's schema)."""

    def __init__(
        self,
        *,
        core_client: Callable[[], Any],
        repo: PhotoEditingRepository,
    ) -> None:
        self._core_client = core_client
        self._repo = repo

    async def batch_ready(self, notice: BatchReadyNotice) -> None:
        platform = await self._repo.get_platform_settings()
        if not platform.notificacoes_globais_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada na plataforma",
                notice.lote_id,
            )
            return
        org = await self._repo.get_org_settings(notice.org_id)
        if org is not None and not org.notificacoes_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada pela organização %s",
                notice.lote_id,
                notice.org_id,
            )
            return
        title, body = batch_ready_message(notice)
        row = {
            "user_id": notice.criado_por,
            "org_id": notice.org_id,
            "type": NOTIFICATION_TYPE,
            "title": title,
            "message": body,
            "metadata": {
                "feature_key": FEATURE,
                "lote_id": notice.lote_id,
                "link": f"/edicao-fotos/lotes/{notice.lote_id}/revisao",
            },
        }
        client = self._core_client()
        # Raises on failure: the engine's `fotos.lote_pronto` handler is
        # at-least-once and retries a notice that did not land.
        await asyncio.to_thread(lambda: client.table("notifications").insert(row).execute())


async def _default_send_email(
    *, to: str, subject: str, html: str, text: str, org_id: Optional[str]
) -> bool:
    """Default `EmailSenderFn` — the seed's generic single-recipient send
    (`noctusai_lib.integrations.email`), never reimplemented here. Resolves
    Resend/SMTP through the 3-tier credential chain; dry-runs (logs, `sent=
    False`) when neither is configured for this org — never raises."""
    from noctusai_lib.integrations.email import Digest, send_to_one

    result = await send_to_one(
        Digest(subject=subject, text=text, html=html),
        recipient=to,
        org_id=org_id,
        log_prefix="EDICAO_FOTOS",
    )
    return bool(result.get("sent"))


def _email_body(notice: BatchReadyNotice, title: str, body: str) -> tuple[str, str, str]:
    """`(subject, html, text)` for the batch-ready email."""
    subject = f"[Edição de Fotos] {title}"
    link = f"/edicao-fotos/lotes/{notice.lote_id}/revisao"
    html = (
        "<div style='font-family:sans-serif;max-width:560px'>"
        f"<h2 style='margin:0 0 8px'>📸 {title}</h2>"
        f"<p style='margin:0 0 16px'>{body}</p>"
        f"<p style='margin:0 0 16px'><a href='{link}' "
        "style='display:inline-block;padding:10px 16px;background:#2563eb;"
        "color:#fff;text-decoration:none;border-radius:6px'>Revisar fotos</a></p>"
        "<p style='color:#888;font-size:12px;margin:24px 0 0'>Enviado pelo "
        "Social Wiring — Edição de Fotos.</p></div>"
    )
    return subject, html, body


class _Recipient:
    __slots__ = ("user_id", "email", "whatsapp_number")

    def __init__(
        self, user_id: str, email: Optional[str], whatsapp_number: Optional[str]
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.whatsapp_number = whatsapp_number


class MultiChannelBatchReadyNotifier:
    """In-app + email + WhatsApp fan-out to the creator + every opted-in
    agency admin (contract §1 / plan §1). The real `services/ports.py`
    wiring; see the module docstring for the failure-semantics split."""

    def __init__(
        self,
        *,
        core_client: Callable[[], Any],
        repo: PhotoEditingRepository,
        preferences: NotificationPreferencesRepository,
        waha_base_url: str = "",
        waha_api_key: str = "",
        waha_session: str = "default",
        whatsapp_client_factory: Optional[Callable[..., Any]] = None,
        send_email: Optional[EmailSenderFn] = None,
    ) -> None:
        self._core_client = core_client
        self._repo = repo
        self._preferences = preferences
        self._waha_base_url = waha_base_url
        self._waha_api_key = waha_api_key
        self._waha_session = waha_session
        # DI seam for WAHA — resolved lazily (not captured eagerly) so a
        # test's explicit factory or the module-level `get_whatsapp_client`
        # patch both stay live, same rationale as
        # `NotificationService._build_whatsapp_client`.
        self._whatsapp_client_factory = whatsapp_client_factory
        self._send_email: EmailSenderFn = send_email or _default_send_email

    async def batch_ready(self, notice: BatchReadyNotice) -> None:
        platform = await self._repo.get_platform_settings()
        if not platform.notificacoes_globais_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada na plataforma",
                notice.lote_id,
            )
            return
        org = await self._repo.get_org_settings(notice.org_id)
        if org is not None and not org.notificacoes_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada pela organização %s",
                notice.lote_id,
                notice.org_id,
            )
            return

        title, body = batch_ready_message(notice)
        recipients = await self._resolve_recipients(notice)
        if not recipients:
            return

        # in-app first, and RAISES on failure — see module docstring.
        await self._write_in_app(notice, title, body, recipients)

        subject, html, text = _email_body(notice, title, body)
        whatsapp_text = f"{title}\n\n{body}"
        whatsapp_client = (
            self._build_whatsapp_client()
            if any(r.whatsapp_number for r in recipients)
            else None
        )
        tasks: list[Awaitable[bool]] = []
        for recipient in recipients:
            if recipient.email:
                tasks.append(
                    self._send_email_logged(
                        to=recipient.email, subject=subject, html=html, text=text,
                        org_id=notice.org_id,
                    )
                )
            if recipient.whatsapp_number and whatsapp_client is not None:
                tasks.append(
                    self._send_whatsapp_logged(whatsapp_client, recipient.whatsapp_number, whatsapp_text)
                )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # --- recipients ---------------------------------------------------
    async def _resolve_recipients(self, notice: BatchReadyNotice) -> list[_Recipient]:
        creator_email = await self._fetch_email(notice.criado_por)
        creator_pref = await self._preferences.get(org_id=notice.org_id, user_id=notice.criado_por)
        recipients = [_Recipient(notice.criado_por, creator_email, creator_pref.whatsapp_number)]
        admins = await self._preferences.list_opted_in_admins(
            org_id=notice.org_id, exclude_user_id=notice.criado_por
        )
        recipients.extend(_Recipient(a.user_id, a.email, a.whatsapp_number) for a in admins)
        return recipients

    async def _fetch_email(self, user_id: str) -> Optional[str]:
        def _query() -> list[dict]:
            return (
                self._core_client()
                .table("noctus_users")
                .select("email")
                .eq("id", user_id)
                .limit(1)
                .execute()
                .data
                or []
            )

        rows = await asyncio.to_thread(_query)
        return rows[0].get("email") if rows else None

    # --- in-app ---------------------------------------------------------
    async def _write_in_app(
        self, notice: BatchReadyNotice, title: str, body: str, recipients: list[_Recipient]
    ) -> None:
        metadata = {
            "feature_key": FEATURE,
            "lote_id": notice.lote_id,
            "link": f"/edicao-fotos/lotes/{notice.lote_id}/revisao",
        }
        client = self._core_client()

        def _insert() -> None:
            rows = [
                {
                    "user_id": r.user_id,
                    "org_id": notice.org_id,
                    "type": NOTIFICATION_TYPE,
                    "title": title,
                    "message": body,
                    "metadata": metadata,
                }
                for r in recipients
            ]
            client.table("notifications").insert(rows).execute()

        # Raises on failure: see module docstring (at-least-once retry).
        await asyncio.to_thread(_insert)

    # --- email / whatsapp (never raise; always log) ---------------------
    async def _send_email_logged(
        self, *, to: str, subject: str, html: str, text: str, org_id: str
    ) -> bool:
        try:
            return await self._send_email(to=to, subject=subject, html=html, text=text, org_id=org_id)
        except Exception:  # noqa: BLE001 — per-recipient failure, never fatal
            logger.exception("edicao_fotos: falha ao enviar email de lote pronto para %s", to)
            return False

    def _build_whatsapp_client(self) -> Any:
        factory = self._whatsapp_client_factory or get_whatsapp_client
        return factory(
            base_url=self._waha_base_url,
            api_key=self._waha_api_key,
            session=self._waha_session,
        )

    async def _send_whatsapp_logged(self, client: Any, phone: str, text: str) -> bool:
        try:
            await client.send_text(chat_id_for_phone(phone), text)
        except Exception:  # noqa: BLE001 — per-recipient failure, never fatal
            logger.exception("edicao_fotos: falha ao enviar WhatsApp de lote pronto para %s", phone)
            return False
        return True


__all__ = [
    "InAppBatchReadyNotifier",
    "MultiChannelBatchReadyNotifier",
    "batch_ready_message",
]

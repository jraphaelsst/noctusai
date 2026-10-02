"""Delivery — the email with the download link, and the buyer-facing download.

Email (seed `make_email_sender`, transactional — `send` RAISES on failure):
a failed send is RECORDED on the pedido (`email_erro`) and logged at error
level, never swallowed; the webhook then still answers 200 (the payment IS
confirmed — the owner re-sends from the admin, and the thank-you page offers
the download regardless).

Idempotency: `claim_email` is an atomic `email_enviado_em IS NULL` update, so
a replayed webhook, a PAYMENT_CONFIRMED + PAYMENT_RECEIVED pair, or two racing
workers produce exactly one email.

Download terms: 30 days from `pago_em`, at most 20 downloads, only while the
pedido is `pago` (a refund stops it at once).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Callable, Optional

from noctusai_lib.integrations.email import OutgoingEmail
from noctusai_lib.integrations.email.types import EmailSender

from app.services.assets import AssetService

logger = logging.getLogger(__name__)

DOWNLOAD_WINDOW_DAYS = 30
MAX_DOWNLOADS = 20
SIGNED_URL_TTL_SECONDS = 300

_ERROR_MAX_CHARS = 300


class DeliveryFailed(Exception):
    """The delivery email could not be sent (recorded on the pedido)."""


class DownloadRefused(Exception):
    """The buyer's download is not available (HTTP `status_code`)."""

    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def mask_email(email: str) -> str:
    """`joao@gmail.com` -> `j***@gmail.com`."""
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def download_state(pedido: dict[str, Any], *, now: datetime) -> str:
    """`ok` | `not_paid` | `refunded` | `expired` | `exhausted`."""
    status = pedido.get("status")
    if status == "reembolsado":
        return "refunded"
    if status != "pago":
        return "not_paid"
    paid_at = _parse_ts(pedido.get("pago_em"))
    if paid_at is None or now > paid_at + timedelta(days=DOWNLOAD_WINDOW_DAYS):
        return "expired"
    if int(pedido.get("downloads") or 0) >= MAX_DOWNLOADS:
        return "exhausted"
    return "ok"


def build_delivery_email(pedido: dict[str, Any], *, public_url: str) -> OutgoingEmail:
    produto = str(pedido["produto"])
    link = f"{public_url.rstrip('/')}/api/public/download/{pedido['token']}"
    nome = str(pedido.get("nome") or "").strip().split(" ")[0] or "olá"
    terms = (
        f"O link vale por {DOWNLOAD_WINDOW_DAYS} dias e permite até {MAX_DOWNLOADS} downloads."
    )
    text = (
        f"Olá, {nome}!\n\n"
        f"Seu pagamento foi confirmado. Baixe o seu {produto} neste link:\n\n{link}\n\n"
        f"{terms}\n\n"
        "Se você não fez esta compra, ignore esta mensagem.\n"
    )
    html = (
        f"<p>Olá, {escape(nome)}!</p>"
        f"<p>Seu pagamento foi confirmado. Baixe o seu <strong>{escape(produto)}</strong> neste link:</p>"
        f'<p><a href="{escape(link, quote=True)}">{escape(link)}</a></p>'
        f"<p>{escape(terms)}</p>"
        "<p>Se você não fez esta compra, ignore esta mensagem.</p>"
    )
    return OutgoingEmail(
        to=[str(pedido["email"])],
        subject=f"Seu {produto} chegou",
        text=text,
        html=html,
    )


class DeliveryService:
    def __init__(
        self,
        *,
        pedidos: Any,
        email_sender: EmailSender,
        assets: AssetService,
        public_url: str,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._pedidos = pedidos
        self._sender = email_sender
        self._assets = assets
        self._public_url = public_url
        self._now = now_fn

    # ── email ────────────────────────────────────────────────────────────
    async def send_once(self, pedido: dict[str, Any]) -> bool:
        """Send the delivery email iff it was never sent. True when this call sent it.

        Raises `DeliveryFailed` after recording the failure (the claim is
        released so a later retry / admin re-send can succeed)."""
        pedido_id = str(pedido["id"])
        if not self._pedidos.claim_email(pedido_id, at_iso=self._now().isoformat()):
            return False
        try:
            await self._sender.send(build_delivery_email(pedido, public_url=self._public_url))
        except Exception as exc:  # noqa: BLE001 - recorded, then surfaced as DeliveryFailed
            self._record_failure(pedido_id, exc)
            raise DeliveryFailed(str(exc)) from exc
        return True

    async def resend(self, pedido: dict[str, Any]) -> None:
        """Admin re-send: sends regardless of `email_enviado_em`."""
        pedido_id = str(pedido["id"])
        try:
            await self._sender.send(build_delivery_email(pedido, public_url=self._public_url))
        except Exception as exc:  # noqa: BLE001
            self._record_failure(pedido_id, exc, clear_sent=False)
            raise DeliveryFailed(str(exc)) from exc
        self._pedidos.update(pedido_id, {"email_enviado_em": self._now().isoformat(), "email_erro": None})

    def _record_failure(self, pedido_id: str, exc: Exception, *, clear_sent: bool = True) -> None:
        message = f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]
        logger.error("delivery: email send failed pedido=%s error=%s", pedido_id, type(exc).__name__)
        if clear_sent:
            self._pedidos.release_email(pedido_id, error=message)
        else:
            self._pedidos.update(pedido_id, {"email_erro": message})

    # ── buyer-facing status + download ───────────────────────────────────
    def status_view(self, pedido: dict[str, Any]) -> dict[str, Any]:
        downloadable = download_state(pedido, now=self._now()) == "ok"
        return {
            "status": pedido["status"],
            "produto": pedido["produto"],
            "email_mascarado": mask_email(str(pedido.get("email") or "")),
            "download_url": f"/api/public/download/{pedido['token']}" if downloadable else None,
        }

    async def take_download(self, pedido: Optional[dict[str, Any]]) -> str:
        """Count one download and return a 5-minute signed URL of the kit."""
        if pedido is None:
            raise DownloadRefused("Pedido não encontrado.", status_code=404)
        state = download_state(pedido, now=self._now())
        if state == "not_paid":
            raise DownloadRefused("Pedido não encontrado.", status_code=404)
        if state == "refunded":
            raise DownloadRefused("Este pedido foi reembolsado; o download não está mais disponível.", status_code=410)
        if state == "expired":
            raise DownloadRefused(
                f"O prazo de {DOWNLOAD_WINDOW_DAYS} dias para download terminou.", status_code=410
            )
        if state == "exhausted":
            raise DownloadRefused(f"O limite de {MAX_DOWNLOADS} downloads foi atingido.", status_code=410)
        # The file must exist BEFORE a download is consumed.
        if not await self._assets.kit_exists():
            logger.error("download: kit file missing in storage")
            raise DownloadRefused("Arquivo temporariamente indisponível. Tente novamente em instantes.", status_code=503)
        if not self._pedidos.take_download(str(pedido["token"]), max_downloads=MAX_DOWNLOADS):
            raise DownloadRefused(f"O limite de {MAX_DOWNLOADS} downloads foi atingido.", status_code=410)
        return await self._assets.kit_signed_url(expires_in_seconds=SIGNED_URL_TTL_SECONDS)


__all__ = [
    "DOWNLOAD_WINDOW_DAYS",
    "DeliveryFailed",
    "DeliveryService",
    "DownloadRefused",
    "MAX_DOWNLOADS",
    "build_delivery_email",
    "download_state",
    "mask_email",
]

"""Public checkout — create a `pedido` and a hosted one-off Asaas charge.

Contract §3 `POST /api/public/checkout`. The price is ALWAYS read from the
settings ledger server-side — the request carries no amount. The gateway is
the seed's `HostedCheckout` (`make_hosted_checkout`); this module never
speaks to Asaas directly.

Order matters: validate -> checkout enabled (409) -> gateway available (503)
-> insert the pedido -> create the charge. A gateway failure marks the
pedido `falhou` (the row stays — an attempt that cost the buyer a click is
still an order-shaped fact the owner may want to see).

PII: nome/email/cpf are NEVER logged.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Callable, Optional

from email_validator import EmailNotValidError, validate_email

from noctusai_lib.integrations.documents.cpf import is_valid as cpf_is_valid
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.integrations.payments.checkout import CheckoutRequest, HostedCheckout
from noctusai_lib.integrations.payments.types import Money

from app.services.settings_service import SettingsService
from app.stores.protocols import PedidoStore

logger = logging.getLogger(__name__)

GATEWAY = "asaas"


class CheckoutError(Exception):
    """A checkout refusal carrying its HTTP status + a pt-BR message."""

    def __init__(self, detail: str, *, status_code: int, code: str, field: Optional[str] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code
        self.field = field


def _invalid(field: str, message: str) -> CheckoutError:
    return CheckoutError(message, status_code=422, code="invalid", field=field)


class CheckoutService:
    def __init__(
        self,
        *,
        settings_service: SettingsService,
        pedidos: PedidoStore,
        checkout_factory: Callable[[], HostedCheckout],
        public_url: str,
        token_fn: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        self._settings = settings_service
        self._pedidos = pedidos
        self._checkout_factory = checkout_factory
        self._public_url = public_url.rstrip("/")
        self._token_fn = token_fn

    @staticmethod
    def validate_buyer(nome: str, email: str, cpf: str) -> tuple[str, str, str]:
        nome = (nome or "").strip()
        if not 2 <= len(nome) <= 120:
            raise _invalid("nome", "Informe seu nome completo.")
        try:
            email_norm = validate_email(email or "", check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise _invalid("email", "Informe um e-mail válido.") from None
        digits = only_digits(cpf or "")
        if len(digits) != 11 or not cpf_is_valid(digits):
            raise _invalid("cpf", "Informe um CPF válido.")
        return nome, email_norm, digits

    def create(self, *, nome: str, email: str, cpf: str) -> dict[str, str]:
        nome, email, cpf_digits = self.validate_buyer(nome, email, cpf)

        _version, data = self._settings.current()
        if not data.get("checkout_enabled", True):
            raise CheckoutError(
                "As vendas estão pausadas no momento.", status_code=409, code="checkout_disabled"
            )

        # Resolved BEFORE any write: an unconfigured gateway (503) must not
        # leave an orphan pedido behind.
        hosted = self._checkout_factory()

        token = self._token_fn()
        valor_cents = int(data["price_cents"])
        produto = str(data["product_name"])
        pedido = self._pedidos.create(
            {
                "token": token,
                "nome": nome,
                "email": email,
                "cpf": cpf_digits,
                "valor_cents": valor_cents,
                "produto": produto,
                "status": "pendente",
                "gateway": GATEWAY,
            }
        )
        pedido_id = str(pedido["id"])

        try:
            session = hosted.create_checkout(
                CheckoutRequest(
                    external_reference=pedido_id,
                    email=email,
                    name=nome,
                    price=Money(valor_cents, "BRL"),
                    billing_cycle=None,
                    billing_method="undefined",
                    tax_id=cpf_digits,
                    description=produto,
                    success_url=f"{self._public_url}/obrigado?pedido={token}",
                    cancel_url=f"{self._public_url}/",
                    metadata={"pedido_id": pedido_id},
                )
            )
        except PaymentGatewayError as exc:
            logger.error("checkout: gateway refused pedido=%s status=%s retryable=%s", pedido_id, exc.status, exc.retryable)
            self._pedidos.update(pedido_id, {"status": "falhou"})
            raise CheckoutError(
                "Não foi possível iniciar o pagamento agora. Tente novamente em instantes.",
                status_code=502,
                code="gateway_error",
            ) from exc

        self._pedidos.update(
            pedido_id,
            {"gateway_charge_id": session.id_at_gateway, "checkout_url": session.checkout_url},
        )
        return {"checkout_url": session.checkout_url, "pedido_token": token}


__all__ = ["CheckoutError", "CheckoutService", "GATEWAY"]

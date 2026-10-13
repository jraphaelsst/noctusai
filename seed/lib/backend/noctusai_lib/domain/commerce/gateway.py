"""`CheckoutGateway` -- the per-org payment-gateway seam (Protocol + Fake + Real + factory).

Everything the commerce organ needs from "the payment gateway" that is NOT the
charge call itself (that is the seed's `HostedCheckout`):

* which `HostedCheckout` to use for THIS org (each client has its OWN Asaas
  account -- D5/D27; the key is resolved per org, never a platform-wide key);
* noc's platform wallet id for the fee split (PLATFORM tier credential);
* the per-org webhook token the delivery is verified against;
* the gateway's customer record (name/doc/e-mail/phone/address) for the
  payment-is-the-source-of-truth enrichment (D26).

Real = Asaas, composing `make_hosted_checkout` / `make_payment_gateway` and the
seed credential resolver (`resolve_api_key`: the product's encrypted per-org store
first, then the platform chain). Fake = in-memory, scriptable, test-only.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

import httpx

from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout, HostedCheckout, make_hosted_checkout
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.factory import make_payment_gateway
from noctusai_lib.security.api_keys import resolve_api_key

from ._common import digits
from .config import CommerceConfig
from .errors import GatewayNotConfigured

logger = logging.getLogger(__name__)

GATEWAY_NAME = "asaas"


@runtime_checkable
class CheckoutGateway(Protocol):
    name: str

    def hosted_checkout(self, org_id: Any) -> HostedCheckout:
        """The org's hosted-checkout client. Raises `GatewayNotConfigured` when the
        org has no usable credentials (checkout answers 503 BEFORE any write)."""
        ...

    def platform_wallet_id(self) -> Optional[str]:
        """noc's wallet id for the platform-fee split, or None (=> no split)."""
        ...

    def webhook_token(self, org_id: Any) -> Optional[str]:
        """The org's webhook shared secret, resolved at request time."""
        ...

    def customer_data(self, org_id: Any, customer_id_at_gateway: str) -> Optional[dict]:
        """The gateway's customer record normalised to `{name, doc, email, phone,
        address}` (absent keys omitted), or None when it cannot be read."""
        ...


class FakeCheckoutGateway:
    """In-memory `CheckoutGateway` for dev + tests. Scriptable:

    * `configured=False` => `hosted_checkout` raises `GatewayNotConfigured`;
    * `wallet_id` => the platform wallet (None => no split);
    * `webhook_secret` => the per-org token (None => the webhook 401s, fail-closed);
    * `customers` => `{customer_id_at_gateway: {name, doc, ...}}` for enrichment.
    """

    name = GATEWAY_NAME

    def __init__(
        self,
        *,
        configured: bool = True,
        wallet_id: Optional[str] = None,
        webhook_secret: Optional[str] = "fake-webhook-token",
        customers: Optional[dict[str, dict]] = None,
        checkout: Optional[FakeHostedCheckout] = None,
        customer_error: Optional[BaseException] = None,
    ) -> None:
        self.configured = configured
        self.wallet_id = wallet_id
        self.webhook_secret = webhook_secret
        self.customers = dict(customers or {})
        self.checkout = checkout or FakeHostedCheckout()
        self.customer_error = customer_error

    def hosted_checkout(self, org_id: Any) -> HostedCheckout:
        if not self.configured:
            raise GatewayNotConfigured(f"no payment gateway credentials for org {org_id}")
        return self.checkout

    def platform_wallet_id(self) -> Optional[str]:
        return self.wallet_id

    def webhook_token(self, org_id: Any) -> Optional[str]:
        return self.webhook_secret

    def customer_data(self, org_id: Any, customer_id_at_gateway: str) -> Optional[dict]:
        if self.customer_error is not None:
            raise self.customer_error
        return self.customers.get(customer_id_at_gateway)


def _asaas_customer_fields(raw: Mapping[str, Any]) -> dict:
    out: dict[str, Any] = {}
    if raw.get("name"):
        out["name"] = raw["name"]
    if raw.get("cpfCnpj"):
        out["doc"] = digits(str(raw["cpfCnpj"]))
    if raw.get("email"):
        out["email"] = raw["email"]
    phone = raw.get("mobilePhone") or raw.get("phone")
    if phone:
        out["phone"] = digits(str(phone))
    address = {
        key: raw[src]
        for key, src in (
            ("street", "address"),
            ("number", "addressNumber"),
            ("complement", "complement"),
            ("district", "province"),
            ("zip", "postalCode"),
        )
        if raw.get(src)
    }
    if address:
        out["address"] = address
    return out


class AsaasCheckoutGateway:
    """Real Asaas `CheckoutGateway`.

    `store_factory` builds the product's Fernet credential store (the per-org
    keys live there); without it only the platform chain answers, which is the
    correct degradation for a product that has no per-org key UI yet.
    """

    name = GATEWAY_NAME

    def __init__(
        self,
        cfg: CommerceConfig,
        *,
        store_factory: Optional[Callable[[], Any]] = None,
        resolver: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._cfg = cfg
        self._store_factory = store_factory
        self._resolver = resolver
        self._transport = transport

    def _resolve(self, name: str, org_id: Optional[Any]) -> Optional[str]:
        kwargs: dict[str, Any] = {"store_factory": self._store_factory}
        if self._resolver is not None:
            kwargs["resolver"] = self._resolver
        return resolve_api_key(name, str(org_id) if org_id else None, **kwargs)

    def _api_key(self, org_id: Any) -> str:
        key = self._resolve(self._cfg.asaas_api_key_name, org_id)
        if not key:
            raise GatewayNotConfigured(f"no Asaas API key for org {org_id}")
        return key

    def hosted_checkout(self, org_id: Any) -> HostedCheckout:
        return make_hosted_checkout(provider="asaas", asaas_api_key=self._api_key(org_id), asaas_transport=self._transport)

    def platform_wallet_id(self) -> Optional[str]:
        # PLATFORM tier on purpose (org_id=None): the wallet is noc's, never a client's.
        return self._resolve(self._cfg.platform_wallet_credential, None)

    def webhook_token(self, org_id: Any) -> Optional[str]:
        return self._resolve(self._cfg.asaas_webhook_token_name, org_id)

    def customer_data(self, org_id: Any, customer_id_at_gateway: str) -> Optional[dict]:
        try:
            gateway = make_payment_gateway(
                provider="asaas", asaas_api_key=self._api_key(org_id), asaas_transport=self._transport
            )
            raw = gateway.get_customer(customer_id_at_gateway)
        except (GatewayNotConfigured, PaymentGatewayError) as exc:
            logger.warning("commerce: could not read the gateway customer: %s", exc)
            return None
        return _asaas_customer_fields(raw)


def make_checkout_gateway(
    cfg: CommerceConfig,
    *,
    use_fake: bool = False,
    store_factory: Optional[Callable[[], Any]] = None,
    resolver: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
    **fake_kwargs: Any,
) -> CheckoutGateway:
    """Fake when `use_fake`, else the Asaas gateway (the only Real in P3)."""
    if use_fake:
        return FakeCheckoutGateway(**fake_kwargs)
    return AsaasCheckoutGateway(cfg, store_factory=store_factory, resolver=resolver, transport=transport)


__all__ = [
    "AsaasCheckoutGateway",
    "CheckoutGateway",
    "FakeCheckoutGateway",
    "GATEWAY_NAME",
    "make_checkout_gateway",
]

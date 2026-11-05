"""``GrantDelivery`` — the control-plane side of a platform grant.

The agents app mints a credential for a product, then calls
``PUT {product}/api/platform/grants/{issuer}`` with a one-shot delivery token
(scope ``platform:grant-receive``) as the bearer. The product's receiver
(``noctusai_seed.platform_grants_router``) stores the credential. Revoke is a
best-effort ``DELETE`` on the same path.

Protocol + Fake + Real + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``). The factory REFUSES the
Fake in a deploy context: a Fake "delivery" would report success and deliver
nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol

import httpx

from noctusai_lib.config.product_urls import resolve_product_url

logger = logging.getLogger(__name__)

__all__ = [
    "DeliveredCall",
    "FakeGrantDelivery",
    "GrantDelivery",
    "GrantDeliveryError",
    "GrantPayload",
    "HttpGrantDelivery",
    "make_grant_delivery",
]

_TIMEOUT_SECONDS = 10.0


class GrantDeliveryError(RuntimeError):
    """A grant could not be delivered (transport failure or non-2xx)."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GrantPayload:
    """Body of ``PUT /api/platform/grants/{issuer}``. The org is NOT here — the
    receiver takes it from the delivery token."""

    credential: str
    agent_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "credential": self.credential,
            "agent_id": self.agent_id,
            "metadata": dict(self.metadata),
        }


class GrantDelivery(Protocol):
    def deliver(
        self, product_slug: str, issuer: str, payload: GrantPayload, *, delivery_token: str,
    ) -> None:
        """PUT the grant. Raises :class:`GrantDeliveryError` on any failure."""
        ...

    def revoke(self, product_slug: str, issuer: str, *, delivery_token: str) -> bool:
        """Best-effort DELETE. ``True`` when the product acknowledged (2xx);
        never raises (the product sees 401 once its token is revoked anyway)."""
        ...


@dataclass(frozen=True)
class DeliveredCall:
    """One recorded call on the Fake."""

    method: str  # "PUT" | "DELETE"
    product_slug: str
    issuer: str
    delivery_token: str
    payload: Optional[GrantPayload] = None


class FakeGrantDelivery:
    """Records calls; ``fail_deliver`` / ``fail_revoke`` simulate a refusal."""

    def __init__(self) -> None:
        self.calls: list[DeliveredCall] = []
        self.fail_deliver = False
        self.fail_revoke = False

    def deliver(
        self, product_slug: str, issuer: str, payload: GrantPayload, *, delivery_token: str,
    ) -> None:
        if self.fail_deliver:
            raise GrantDeliveryError("fake delivery failure", status_code=502)
        self.calls.append(DeliveredCall("PUT", product_slug, issuer, delivery_token, payload))

    def revoke(self, product_slug: str, issuer: str, *, delivery_token: str) -> bool:
        if self.fail_revoke:
            return False
        self.calls.append(DeliveredCall("DELETE", product_slug, issuer, delivery_token))
        return True


class HttpGrantDelivery:
    """Real sender: HTTP to the product's resolved URL, bearer = delivery token."""

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        db_url_bases: Optional[Mapping[str, str]] = None,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        """``db_url_bases`` maps slug -> ``public.products.url_base`` (the
        ``resolve_product_url`` fallback when no env override is set)."""
        self._client = client or httpx.Client(timeout=timeout)
        self._bases = dict(db_url_bases or {})

    def _url(self, product_slug: str, issuer: str) -> str:
        base = resolve_product_url(product_slug, db_url_base=self._bases.get(product_slug))
        return f"{base}/api/platform/grants/{issuer}"

    def deliver(
        self, product_slug: str, issuer: str, payload: GrantPayload, *, delivery_token: str,
    ) -> None:
        url = self._url(product_slug, issuer)
        try:
            resp = self._client.put(
                url, json=payload.to_json(), headers={"Authorization": f"Bearer {delivery_token}"},
            )
        except httpx.HTTPError as exc:
            raise GrantDeliveryError(
                f"grant delivery to {product_slug} failed: {type(exc).__name__}"
            ) from exc
        if resp.status_code // 100 != 2:
            raise GrantDeliveryError(
                f"grant delivery to {product_slug} refused: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

    def revoke(self, product_slug: str, issuer: str, *, delivery_token: str) -> bool:
        try:
            resp = self._client.delete(
                self._url(product_slug, issuer),
                headers={"Authorization": f"Bearer {delivery_token}"},
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "grant_revoke_failed product=%s issuer=%s err=%s",
                product_slug, issuer, type(exc).__name__,
            )
            return False
        return resp.status_code // 100 == 2


def make_grant_delivery(
    *,
    client: Optional[httpx.Client] = None,
    db_url_bases: Optional[Mapping[str, str]] = None,
    real: Optional[bool] = None,
    deploy_context: Optional[bool] = None,
) -> GrantDelivery:
    """Real HTTP sender, or the Fake outside a deploy context.

    ``real=True`` (or an injected ``client``) -> :class:`HttpGrantDelivery`.
    Otherwise the Fake — which raises ``RuntimeError`` in a deploy context.
    ``deploy_context=None`` asks ``is_deploy_context()``.
    """
    if real or client is not None:
        return HttpGrantDelivery(client=client, db_url_bases=db_url_bases)
    if deploy_context is None:
        from noctusai_lib.config.deploy_config import is_deploy_context

        deploy_context = is_deploy_context()
    if deploy_context:
        raise RuntimeError(
            "make_grant_delivery: refusing FakeGrantDelivery in a deploy context "
            "— call make_grant_delivery(real=True)."
        )
    return FakeGrantDelivery()

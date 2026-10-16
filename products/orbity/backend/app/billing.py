"""Orbity's billing wiring on the SEED organs: configs, the gateway, the CNPJ lookup.

* Finance (`fin_*`) and contracts (`ctr_*`) live in this product's schema (migrations 019 / 021, generator output
  verbatim; pinned by ``tests/test_billing_wiring.py``).
* Orbity mounts NO parties/items organ: a contract's ``party_id`` IS ``orbity.clients.id`` (a plain UUID by
  ``ContractsConfig.with_parties=False``), verified in the org and snapshotted (legal name + CPF/CNPJ) through the
  organ's ``party_resolver`` seam -- the editor's party picker sends only the id.
* The gateway is Asaas, resolved PER ORG (key / environment / webhook token are org credentials, org settings ->
  platform settings -> env). No credential => ``GatewayNotConfigured`` => the charge stays a plain receivable; the
  Fake is reachable ONLY through ``PAYMENTS_ALLOW_FAKE`` (never a silent default).
* Conexa (the upstream agency's other gateway) has no seed adapter:
  NOC-REMEDIATE[orbity-conexa-adapter] -- add a ``conexa`` HostedCheckout/ChargeOperations adapter to
  ``noctusai_lib.integrations.payments`` first, then a ``billing_type`` branch in ``services/billing_charges.py``. -- 2026-10-16
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.domain.commerce import CommerceConfig
from noctusai_lib.domain.commerce.errors import GatewayNotConfigured
from noctusai_lib.domain.commerce.gateway import AsaasCheckoutGateway, CheckoutGateway, FakeCheckoutGateway
from noctusai_lib.domain.contracts import ContractsConfig
from noctusai_lib.domain.finance import FinanceConfig
from noctusai_lib.integrations.cnpj_registry import make_cnpj_registry_lookup
from noctusai_lib.integrations.cnpj_registry.types import CnpjRegistryLookup

from app.config import settings

logger = logging.getLogger(__name__)

SCHEMA = "orbity"

def client_party_resolver(db: Any, org_id: str, party_id: str) -> Optional[dict]:
    """The contracts organ's ``party_resolver`` seam: the contract's customer IS an ``orbity.clients`` row of the SAME org.

    Snapshots the Razão Social (what the gateway charges) and the CPF/CNPJ; ``None`` => the id is not this org's client."""
    rows = db.table("clients").select("legal_name,name,document").eq("org_id", str(org_id)).eq("id", str(party_id)).limit(1).execute().data or []
    if not rows:
        return None
    row = rows[0]
    return {"party_name": row.get("legal_name") or row.get("name"), "party_doc": row.get("document")}


FINANCE_CFG = FinanceConfig(schema=SCHEMA)
CONTRACTS_CFG = ContractsConfig(schema=SCHEMA, party_resolver=client_party_resolver)

#: Only the credential NAMES / default environment of the commerce gateway config are used (asaas_api_key,
#: asaas_environment, asaas_webhook_token, sandbox default) -- Orbity runs no storefront.
_GATEWAY_CFG = CommerceConfig(schema=SCHEMA)

GATEWAY_NAME = "asaas"


class OrbityAsaasGateway(AsaasCheckoutGateway):
    """The seed Asaas gateway + a cheap "is this org configured?" probe (no HTTP client is built to answer it)."""

    def is_configured(self, org_id: Any) -> bool:
        try:
            self._api_key(org_id)
        except GatewayNotConfigured:
            return False
        return True


def platform_resolve(name: str, org_id: Optional[str]) -> Optional[str]:
    return resolve_credential(name, org_id)


_gateway: Optional[CheckoutGateway] = None


def get_gateway() -> CheckoutGateway:
    """The per-org gateway. One instance per process (it holds no connection; clients are built per call)."""
    global _gateway
    if _gateway is None:
        if settings.payments_allow_fake:
            _gateway = FakeCheckoutGateway()
        else:
            _gateway = OrbityAsaasGateway(_GATEWAY_CFG, resolver=platform_resolve)
    return _gateway


def gateway_is_configured(org_id: Any, gateway: Optional[CheckoutGateway] = None) -> bool:
    gw = gateway or get_gateway()
    probe = getattr(gw, "is_configured", None)
    if probe is not None:
        return bool(probe(org_id))
    try:  # Fake gateways: configured iff they hand out a checkout
        gw.hosted_checkout(org_id)
    except GatewayNotConfigured:
        return False
    return True


def get_cnpj_lookup() -> CnpjRegistryLookup:
    """Public keyless registries (BrasilAPI / ReceitaWS): Real unless the harness opted into fakes."""
    return make_cnpj_registry_lookup(real=not settings.payments_allow_fake)


__all__ = [
    "CONTRACTS_CFG", "client_party_resolver", "FINANCE_CFG", "GATEWAY_NAME", "OrbityAsaasGateway", "SCHEMA", "gateway_is_configured",
    "get_cnpj_lookup", "get_gateway",
]

"""{{PRODUCT_NAME}} -- the ERP organs mounted on this product (one-call seed mounts, house auth).

Order is irrelevant here (routers only); the MIGRATION order is by each organ's `OrganSpec.requires`
(`tests/test_erp_wiring.py` pins it). Tables are rendered by `noctus.dev.render_organ_migration`, never hand-edited.

Seams left at the seed defaults on purpose -- a market ERP fills them:
* quotes: no `get_link_secret` => the signed public accept page is not mounted and `send` answers 503;
* contracts: no `get_signature` => the signature routes answer 409 `assinatura_nao_configurada`;
* finance gateway sync: stays 503-not-configured until a product supplies `get_charge_operations`.
"""
from __future__ import annotations

from noctusai_lib.domain.finance import FinanceConfig
from noctusai_seed.organs import (
    mount_contracts,
    mount_finance,
    mount_inventory,
    mount_items,
    mount_parties,
    mount_purchasing,
    mount_quotes,
)

from app.dependencies import _db, get_admin_client, get_current_user_org

SCHEMA = "{{SCHEMA_NAME}}"
FINANCE_CFG = FinanceConfig(schema=SCHEMA)


def _core():
    return _db.get_core_client()


_common = dict(schema=SCHEMA, auth_dependency=get_current_user_org, get_admin_client=get_admin_client, get_core_client=_core)

ERP_ORGANS = [
    mount_finance(cfg=FINANCE_CFG, **_common),
    mount_parties(**_common),
    mount_items(**_common),
    mount_inventory(**_common),
    mount_purchasing(**_common),
    mount_contracts(**_common),
    mount_quotes(**_common),
]

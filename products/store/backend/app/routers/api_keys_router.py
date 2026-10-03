"""`/api/settings/api-keys*` — the owner's managed keys, admin-only.

A thin mount of the seed `create_api_keys_router` (same as community /
social-wiring) over this product's specs. No local route logic: values are
never returned (masked `hint` + `source` only); `ENCRYPTION_KEY` missing => the
seed's 503 config-gap on writes. The router's org dependency is the store's
admin gate + the single-tenant `STORE_ORG_ID`, so every route 401/403s for
anyone but the owner.
"""
from noctusai_seed.api_keys_router import create_api_keys_router

from app.api_keys import API_KEY_SPECS, key_provider
from app.config import settings
from app.key_testers import checkout_probe
from app.dependencies import get_store_admin_org

router = create_api_keys_router(
    deps=None,
    settings=settings,
    specs=API_KEY_SPECS,
    store_factory=key_provider.build_store,
    get_current_user_org=get_store_admin_org,
    resolver=key_provider.platform_resolve,
    testers={"asaas_api_key": checkout_probe.test_asaas_api_key},
)

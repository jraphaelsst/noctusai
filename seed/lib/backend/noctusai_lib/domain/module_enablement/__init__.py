"""Per-org module enablement -- ALL modules ON by default, switched per org by NoctusAI admins.

* `keys` -- canonical module-group keys (mirror of the FE `MODULE_GROUP_ORDER`) + page-status vocabulary.
* `store` -- `ModuleEnablementStore` Protocol + Fake + Supabase (`public.org_modules`) + factory; `ModuleEnablement`
  resolver (`enabled_modules(org_id)`; absent row = ON; store error = 503, never "all on").
* `sql` -- `module_enablement_migration()` (service-only, tier platform); registered as organ `module_enablement`.
* `admin_router` -- the platform-admin write API the core admin dashboard consumes.

The product-side binding (`ModuleSpec`, the route guard, `GET /api/modules`) is `noctusai_seed.modules`.
KB § PATTERNS/architect/vertical-seed.md § Mounting a module.
"""
from .admin_router import OrgModuleItem, OrgModulesOut, OrgModuleUpdate, create_org_modules_admin_router
from .guards import module_enablement_guard_probes
from .keys import (
    MODULE_GROUP_KEYS,
    MODULE_PERMISSION_LEVELS,
    PAGE_STATUS_DEFAULT,
    PAGE_STATUSES,
    is_valid_enablement_key,
    is_valid_page_key,
)
from .sql import MODULE_ENABLEMENT_MIGRATION_HEADER, module_enablement_migration
from .store import (
    MODULE_DISABLED_CODE,
    ORG_MODULES_TABLE,
    FakeModuleEnablementStore,
    ModuleEnablement,
    ModuleEnablementStore,
    ModuleEnablementUnavailable,
    SupabaseModuleEnablementStore,
    make_module_enablement,
    make_module_enablement_store,
)

__all__ = [
    "FakeModuleEnablementStore",
    "MODULE_DISABLED_CODE",
    "MODULE_ENABLEMENT_MIGRATION_HEADER",
    "MODULE_GROUP_KEYS",
    "MODULE_PERMISSION_LEVELS",
    "ModuleEnablement",
    "ModuleEnablementStore",
    "ModuleEnablementUnavailable",
    "ORG_MODULES_TABLE",
    "OrgModuleItem",
    "OrgModuleUpdate",
    "OrgModulesOut",
    "PAGE_STATUSES",
    "PAGE_STATUS_DEFAULT",
    "SupabaseModuleEnablementStore",
    "create_org_modules_admin_router",
    "is_valid_enablement_key",
    "is_valid_page_key",
    "make_module_enablement",
    "make_module_enablement_store",
    "module_enablement_guard_probes",
    "module_enablement_migration",
]

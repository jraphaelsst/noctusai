"""Modules: the declared bundle a market product mounts (`create_product_app(modules=[...])`).

    from noctusai_seed.modules import ModuleSpec, PageSpec
    crm = ModuleSpec(key="crm", organs=[leads, funnel], pages=[PageSpec("leads", "/crm/leads", "Leads")],
                     permissions={"crm.write": "admin"})
    app = create_product_app(..., modules=[crm], module_auth_dependency=get_current_user_org)

KB § PATTERNS/architect/vertical-seed.md § Mounting a module.
"""
from .mount import ModuleMount, module_disabled, mount_modules
from .spec import MANIFEST_VERSION, ModuleSpec, PageSpec, module_manifest, validate_modules

__all__ = [
    "MANIFEST_VERSION",
    "ModuleMount",
    "ModuleSpec",
    "PageSpec",
    "module_disabled",
    "module_manifest",
    "mount_modules",
    "validate_modules",
]

"""The n8n module must be REGISTERED in `app.main.MODULES`, not merely exist.

Why this test exists
--------------------
`app/modules/n8n/__init__.py` exports `register()` and says in its own
docstring that wiring it in is "a single MODULES [entry] ... the tech-lead
registers this module when merging both". The backend module and the page UI
lived on separate branches, so that last step fell to whoever merged them —
and on 2026-07-31 that merge shipped to production without it.

It was the worst shape of failure, because everything LOOKED shipped: the
module directory was present, its 33 unit tests passed, the page rendered,
the nav item appeared, and the empty state ("select a client") was correct —
the empty state needs no API. The moment a client was selected, every call
404'd, because `/api/n8n/*` had no routes at all. Verified after the fact:
0 mounted routes without the MODULES entry, 9 with it.

Router unit tests cannot catch this — they import the router object directly
and never consult the assembled app. Only membership in the assembly list can.

A NOTE ON WHAT THIS DOES *NOT* ASSERT, and why
----------------------------------------------
The obvious test — "assert /api/n8n/workflows is in app.routes" — was tried
first and is USELESS here: it passed even with the MODULES entry deleted,
because the product's conftest imports `app.main` during collection, so
`sys.modules` already holds an app assembled before the edit. A route
assertion that cannot fail is decoration. Membership in `MODULES` is checked
instead because it is the actual contract and it demonstrably fails when
broken.
"""
from __future__ import annotations


def test_n8n_register_is_in_the_modules_assembly_list():
    from app.main import MODULES
    from app.modules.n8n import register

    assert register in MODULES, (
        "app.modules.n8n.register is missing from app.main.MODULES. The module "
        "exists and its unit tests pass, but NO /api/n8n route is mounted and "
        "every request from the page 404s."
    )


def test_register_yields_the_four_surfaces_the_page_calls():
    """The FE hits workflows, folders, settings and tags. A partial module is
    as broken as an unmounted one, so assert the router set itself — this is
    independent of whether the app object was cached at collection time."""
    from app.modules.n8n import register

    paths = {
        route.path
        for router in register().routers
        for route in router.routes
        if hasattr(route, "path")
    }
    for required in (
        "/api/n8n/workflows",
        "/api/n8n/folders",
        "/api/n8n/settings",
        "/api/n8n/tags",
    ):
        assert required in paths, f"{required} is not declared by app.modules.n8n.register()"

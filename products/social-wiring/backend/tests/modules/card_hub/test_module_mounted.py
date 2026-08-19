"""`card_hub` must be REGISTERED in `app.main.MODULES`, not merely exist —
see `tests/modules/n8n/test_module_mounted.py`'s docstring for the
production incident this shape of test guards against (a module whose
directory, unit tests, and even UI empty-state all look shipped, while
zero routes are actually mounted)."""
from __future__ import annotations


def test_card_hub_register_is_in_the_modules_assembly_list():
    from app.main import MODULES
    from app.modules.card_hub import register

    assert register in MODULES, (
        "app.modules.card_hub.register is missing from app.main.MODULES. The "
        "module exists and its unit tests pass, but no /api/clientes/{id}/card "
        "route is mounted and every request from the card dialog 404s."
    )


def test_card_hub_registered_before_media_wiring():
    """See `app/main.py`'s MODULES comment: `_card_hub` MUST precede
    `_register_media_wiring` or `GET/POST /api/clientes/tags` structurally
    collides with `clientes_router.py`'s bare `/{cliente_id}` and every
    `/tags` request 422s instead of matching this module's route."""
    from app.main import MODULES
    from app.modules.card_hub import register as card_hub_register

    names = [getattr(m, "__name__", str(m)) for m in MODULES]
    media_wiring_index = next(
        i for i, m in enumerate(MODULES) if getattr(m, "__name__", "") == "_register_media_wiring"
    )
    card_hub_index = MODULES.index(card_hub_register)
    assert card_hub_index < media_wiring_index, (
        f"card_hub must be registered BEFORE _register_media_wiring in MODULES "
        f"(got order {names}) or /api/clientes/tags loses the route-match race "
        "to clientes_router's bare /{cliente_id}."
    )


def test_register_yields_the_expected_surfaces():
    from app.modules.card_hub import register

    paths = {
        route.path
        for router in register().routers
        for route in router.routes
        if hasattr(route, "path")
    }
    for required in (
        "/api/clientes/tags",
        "/api/clientes/documentos/tipos",
        "/api/clientes/{cliente_id}/timeline",
        "/api/clientes/{cliente_id}/notas",
        "/api/clientes/{cliente_id}/tags",
        "/api/clientes/{cliente_id}/membros",
        # `/datas` retired 2026-08-19 — see the note above.
        "/api/clientes/{cliente_id}/agendamentos",
        "/api/clientes/{cliente_id}/checklists",
        "/api/clientes/{cliente_id}/documentos",
        "/api/clientes/{cliente_id}/documentos/{documento_id}/url",
        "/api/clientes/{cliente_id}/documentos/{documento_id}/acessos",
        "/api/clientes/{cliente_id}/card",
    ):
        assert required in paths, f"{required} is not declared by app.modules.card_hub.register()"


def test_router_is_mounted_on_the_live_app():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/clientes/tags" in paths
    assert "/api/clientes/{cliente_id}/card" in paths

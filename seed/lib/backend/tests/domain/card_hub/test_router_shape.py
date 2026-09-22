"""The factory's HTTP surface: inventory, ordering, naming, auth.

These pin what a product ADOPTING the factory must be able to rely on to
keep its API contract byte-identical — route paths + methods + order, the
path-parameter name, OpenAPI operation ids and body-schema names, status
codes — and that every route is behind the product's auth dependency."""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.testing.schema_errors import MockSchemaError
from tests.domain.card_hub.conftest import AUTH, ORG_ID, build_hub

#: Social-wiring's generic card-hub routes, in its declaration order
#: (`app/modules/card_hub/router.py` at the lift), path relative to the prefix.
SW_GENERIC_ROUTES = [
    ("/tags", "GET"),
    ("/tags", "POST"),
    ("/tags/{tag_id}", "PATCH"),
    ("/tags/{tag_id}", "DELETE"),
    ("/documentos/tipos", "GET"),
    ("/{cliente_id}/timeline", "GET"),
    ("/{cliente_id}/notas", "POST"),
    ("/{cliente_id}/notas/{nota_id}", "PATCH"),
    ("/{cliente_id}/notas/{nota_id}", "DELETE"),
    ("/{cliente_id}/tags", "PUT"),
    ("/{cliente_id}/membros", "GET"),
    ("/{cliente_id}/membros", "PUT"),
    ("/{cliente_id}/checklist-extras", "GET"),
    ("/{cliente_id}/checklist-extras", "POST"),
    ("/{cliente_id}/checklist-extras/{extra_id}", "PATCH"),
    ("/{cliente_id}/checklist-extras/{extra_id}", "DELETE"),
    ("/{cliente_id}/checklist-extras/{extra_id}/documento", "POST"),
    ("/{cliente_id}/checklist-extras/{extra_id}/documento", "DELETE"),
    ("/{cliente_id}/checklists", "GET"),
    ("/{cliente_id}/checklists", "POST"),
    ("/{cliente_id}/checklists/{checklist_id}", "PATCH"),
    ("/{cliente_id}/checklists/{checklist_id}", "DELETE"),
    ("/{cliente_id}/checklists/{checklist_id}/itens", "POST"),
    ("/{cliente_id}/checklists/{checklist_id}/itens/{item_id}", "PATCH"),
    ("/{cliente_id}/checklists/{checklist_id}/itens/{item_id}", "DELETE"),
    ("/{cliente_id}/documentos", "GET"),
    ("/{cliente_id}/documentos", "POST"),
    ("/{cliente_id}/documentos/{documento_id}/url", "GET"),
    ("/{cliente_id}/documentos/{documento_id}", "DELETE"),
    ("/{cliente_id}/documentos/{documento_id}/acessos", "GET"),
    ("/{cliente_id}/card", "GET"),
]

_STATUS_201 = {("/tags", "POST"), ("/{cliente_id}/notas", "POST"), ("/{cliente_id}/checklist-extras", "POST"),
               ("/{cliente_id}/checklists", "POST"), ("/{cliente_id}/checklists/{checklist_id}/itens", "POST"),
               ("/{cliente_id}/documentos", "POST")}


def _inventory(hub) -> list[tuple[str, str]]:
    out = []
    for route in hub.app.routes:
        path = getattr(route, "path", "")
        if path.startswith(hub.prefix):
            for method in sorted(route.methods):
                out.append((path[len(hub.prefix):], method))
    return out


@pytest.fixture
def sw_hub(lead_schema_cache):
    return build_hub("sw")


class TestInventory:
    def test_sw_config_reproduces_social_wirings_route_inventory_in_order(self, sw_hub):
        assert _inventory(sw_hub) == SW_GENERIC_ROUTES

    def test_the_path_parameter_is_the_configured_name(self, hub):
        entity_paths = {p for p, _ in _inventory(hub) if p.startswith("/{")}
        assert entity_paths and all(p.startswith(f"/{{{hub.cfg.id_param}}}") for p in entity_paths)

    def test_literal_routes_live_on_the_collection_router_only(self, hub):
        """Two routers so the product can mount the literal `/tags` BEFORE its
        own bare `/{id}` route (Starlette matches by path shape)."""
        from noctusai_lib.domain.card_hub import card_hub_routers

        collection, entity = card_hub_routers(
            hub.cfg, auth_dependency=lambda: None, resolve_context=lambda a, d: None,
            get_db=lambda: None, get_storage=lambda: None, prefix=hub.prefix,
        )
        assert {r.path for r in collection.routes} == {
            f"{hub.prefix}/tags", f"{hub.prefix}/tags/{{tag_id}}", f"{hub.prefix}/documentos/tipos",
        }
        assert all(r.path.startswith(f"{hub.prefix}/{{{hub.cfg.id_param}}}") for r in entity.routes)

    def test_status_codes(self, sw_hub):
        for route in sw_hub.app.routes:
            if not getattr(route, "path", "").startswith(sw_hub.prefix):
                continue
            path = route.path[len(sw_hub.prefix):]
            for method in getattr(route, "methods", ()):
                if method == "DELETE":
                    assert route.status_code == 204, (path, method)
                elif (path, method) in _STATUS_201:
                    assert route.status_code == 201, (path, method)
                else:
                    assert route.status_code is None, (path, method)


class TestOpenApi:
    def test_operation_ids_are_social_wirings(self, sw_hub):
        ops = sw_hub.app.openapi()["paths"]
        assert ops["/api/clientes/{cliente_id}/tags"]["put"]["operationId"] == (
            "set_cliente_tags_route_api_clientes__cliente_id__tags_put"
        )
        assert ops["/api/clientes/{cliente_id}/timeline"]["get"]["operationId"] == (
            "get_timeline_route_api_clientes__cliente_id__timeline_get"
        )

    def test_entity_path_param_is_listed_first(self, sw_hub):
        params = sw_hub.app.openapi()["paths"]["/api/clientes/{cliente_id}/checklists/{checklist_id}/itens/{item_id}"][
            "patch"
        ]["parameters"]
        assert [p["name"] for p in params if p["in"] == "path"] == ["cliente_id", "checklist_id", "item_id"]
        assert params[0]["schema"] == {"type": "string", "format": "uuid", "title": "Cliente Id"}

    def test_body_schema_names(self, sw_hub):
        schemas = sw_hub.app.openapi()["components"]["schemas"]
        assert "ClienteTagsSetBody" in schemas
        assert list(schemas["MembrosSetBody"]["properties"]) == ["lead_corretor_ids"]

    def test_timeline_query_contract(self, sw_hub):
        params = {p["name"]: p for p in sw_hub.app.openapi()["paths"]["/api/clientes/{cliente_id}/timeline"]["get"]["parameters"]}
        assert params["limit"]["schema"]["maximum"] == 200
        assert params["limit"]["schema"]["minimum"] == 1
        assert params["limit"]["schema"]["default"] == 50
        assert set(params) >= {"cursor", "limit", "kinds"}


class TestAuthBoundary:
    def test_every_route_requires_auth(self, hub):
        """Strict `== 401`: a permissive tuple passes when the route is absent
        or validation runs first (`KB § PATTERNS/compliance/auth-boundary-false-green.md`)."""
        ids = {"{tag_id}": str(uuid4()), "{nota_id}": str(uuid4()), "{extra_id}": str(uuid4()),
               "{checklist_id}": str(uuid4()), "{item_id}": str(uuid4()), "{documento_id}": str(uuid4()),
               f"{{{hub.cfg.id_param}}}": str(uuid4())}
        checked = 0
        for path, method in _inventory(hub):
            url = hub.prefix + path
            for placeholder, value in ids.items():
                url = url.replace(placeholder, value)
            resp = hub.anon.request(method, url)
            assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"
            checked += 1
        assert checked == len(SW_GENERIC_ROUTES)


class TestHarnessIsLive:
    def test_the_sw_mock_validates_against_social_wirings_real_migrations(self, sw_hub):
        """The SW-shaped run only proves schema fit if the mock actually
        refuses an unknown column. Pin that it does."""
        with pytest.raises(MockSchemaError):
            sw_hub.db.table("cliente_notas").insert({"id": str(uuid4()), "org_id": ORG_ID, "nao_existe": 1}).execute()

    def test_the_lead_mock_validates_against_the_generated_template(self, lead_schema_cache):
        hub = build_hub("lead")
        with pytest.raises(MockSchemaError):
            hub.db.table("lead_notas").insert({"id": str(uuid4()), "org_id": ORG_ID, "cliente_id": "x"}).execute()

    def test_a_request_with_auth_reaches_the_handler(self, hub):
        eid = hub.new_entity()
        assert hub.client.get(hub.url(eid, "/card"), headers=AUTH).status_code == 200

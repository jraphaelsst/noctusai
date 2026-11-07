"""website_catalog_service — status derivation, filter, TTL cache, projection leak guard,
router invalidation wiring, and migration 100 structure."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.services import website_catalog_service as svc

BACKEND = Path(__file__).resolve().parents[2]

ROWS = [
    {"slug": "a", "nome": "A", "descricao": "d", "icone": "i", "ativo": True, "deploy_scope": "live",
     "exibir_no_site": True, "url_base": "https://a", "port": 8001},
    {"slug": "b", "nome": "B", "descricao": None, "icone": None, "ativo": True, "deploy_scope": "dev",
     "exibir_no_site": True, "url_base": "https://b", "port": 8002},
    {"slug": "c", "nome": "C", "descricao": "x", "icone": "y", "ativo": False, "deploy_scope": "dev",
     "exibir_no_site": True, "url_base": "https://c", "port": 8003},
    {"slug": "hidden", "nome": "H", "descricao": None, "icone": None, "ativo": True,
     "deploy_scope": "live", "exibir_no_site": False, "url_base": "https://h", "port": 8004},
]


class _Query:
    """Minimal PostgREST stand-in: honours .eq() filters, ignores select/order, counts executes."""

    def __init__(self, client):
        self._c = client
        self._eq: dict = {}

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def execute(self):
        self._c.calls += 1
        rows = [r for r in self._c.rows if all(r.get(k) == v for k, v in self._eq.items())]

        class _R:
            data = rows

        return _R()


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def table(self, name):
        assert name == "products"
        return _Query(self)


@pytest.fixture(autouse=True)
def _clean():
    svc.invalidate_cache()
    yield
    svc.invalidate_cache()


@pytest.mark.parametrize(
    "ativo,scope,expected",
    [
        (True, "live", "disponivel"),
        (True, "dev", "lista_de_espera"),
        (False, "dev", "em_breve"),
        (False, "live", "em_breve"),  # forbidden by the DB CHECK, but never advertised as available
    ],
)
def test_derive_status(ativo, scope, expected):
    assert svc.derive_status(ativo, scope) == expected


def test_list_public_filters_and_derives():
    out = svc.list_public(client=_Client(ROWS), now=0.0)
    assert [(p.slug, p.status) for p in out] == [
        ("a", "disponivel"), ("b", "lista_de_espera"), ("c", "em_breve"),
    ]


def test_projection_keyset_and_no_internal_leak():
    out = svc.list_public(client=_Client(ROWS), now=0.0)
    for p in out:
        assert set(p.model_dump()) == {"slug", "nome", "descricao", "icone", "status"}
    blob = repr([p.model_dump() for p in out])
    for leaked in ("ativo", "deploy_scope", "url_base", "port", "https://", "8001"):
        assert leaked not in blob
    assert set(svc.CatalogProduct.model_fields) == {"slug", "nome", "descricao", "icone", "status"}


def test_projection_schema_rejects_extra_fields():
    with pytest.raises(Exception):
        svc.CatalogProduct(slug="a", nome="A", status="em_breve", url_base="https://x")


def test_cache_ttl_and_invalidation():
    client = _Client(ROWS)
    svc.list_public(client=client, now=1000.0)
    svc.list_public(client=client, now=1001.0)
    assert client.calls == 1  # served from cache
    svc.list_public(client=client, now=1059.0)
    assert client.calls == 1
    svc.list_public(client=client, now=1061.0)  # past 60s
    assert client.calls == 2
    svc.invalidate_cache()
    svc.list_public(client=client, now=1062.0)
    assert client.calls == 3


def test_products_router_invalidates_on_every_write_path():
    src = (BACKEND / "app" / "routers" / "products.py").read_text()
    # create, patch, activation, deploy-scope, delete
    assert src.count("website_catalog_service.invalidate_cache()") == 5


def test_product_update_accepts_exibir_no_site():
    from app.schemas.products import ProductUpdate

    assert ProductUpdate(exibir_no_site=False).model_dump(exclude_none=True) == {"exibir_no_site": False}


def test_migration_100_structure():
    sql = migration_sql(BACKEND / "migrations", "products_exibir_no_site")
    assert "exibir_no_site boolean NOT NULL DEFAULT true" in sql
    assert "'dev-team', 'knowledge-extractor'" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "UPDATE OF ativo, deploy_scope, exibir_no_site, nome, descricao, icone" in sql
    # 5 top-level client_payload keys (<= GitHub's 10); the projection is nested.
    for key in ("'active'", "'live'", "'site_catalog'", "'op'", "'at'"):
        assert key in sql

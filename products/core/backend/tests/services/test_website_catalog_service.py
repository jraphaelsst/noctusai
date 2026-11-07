"""website_catalog_service — status derivation, filter, TTL cache, projection leak guard,
router invalidation wiring, and migration 100 structure."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.services import website_catalog_service as svc

KEYS = {"slug", "nome", "descricao_publica", "icone", "destaque_no_site", "status"}
BACKEND = Path(__file__).resolve().parents[2]

# `descricao` is the INTERNAL description: present on the DB rows, must never reach the public payload.
ROWS = [
    {"slug": "a", "nome": "A", "descricao": "SEGREDO-INTERNO", "descricao_publica": "pub a", "icone": "i",
     "ativo": True, "deploy_scope": "live",
     "exibir_no_site": True, "destaque_no_site": 1, "url_base": "https://a", "port": 8001},
    {"slug": "b", "nome": "B", "descricao": "SEGREDO-B", "descricao_publica": None, "icone": None, "ativo": True, "deploy_scope": "dev",
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
        self._neq: dict = {}

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def neq(self, col, val):
        self._neq[col] = val
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def execute(self):
        self._c.calls += 1
        rows = [r for r in self._c.rows if all(r.get(k) == v for k, v in self._eq.items())
                and all(r.get(k) != v for k, v in self._neq.items())]

        class _R:
            data = rows

        return _R()


class _Client:
    def __init__(self, rows):
        self.rows = [{**r, "id": r.get("id", r["slug"])} for r in rows]
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
        (True, "dev", "em_breve"),
        (False, "dev", "lista_de_espera"),
        (False, "live", "lista_de_espera"),  # forbidden by the DB CHECK, but never advertised as available
    ],
)
def test_derive_status(ativo, scope, expected):
    assert svc.derive_status(ativo, scope) == expected


def test_list_public_filters_and_derives():
    out = svc.list_public(client=_Client(ROWS), now=0.0)
    assert [(p.slug, p.status) for p in out] == [
        ("a", "disponivel"), ("b", "em_breve"), ("c", "lista_de_espera"),
    ]


def test_projection_keyset_and_no_internal_leak():
    out = svc.list_public(client=_Client(ROWS), now=0.0)
    for p in out:
        assert set(p.model_dump()) == KEYS
    blob = repr([p.model_dump() for p in out])
    for leaked in ("ativo", "deploy_scope", "url_base", "port", "https://", "8001"):
        assert leaked not in blob
    assert set(svc.CatalogProduct.model_fields) == KEYS


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
    hidden = sql.split("UPDATE public.products SET exibir_no_site = false", 1)[1].split("AND exibir_no_site;", 1)[0]
    assert "'seed', 'monica', 'dev-team', 'knowledge-extractor'" in hidden
    assert "academia-de-reciclagem" not in hidden and "p-studio" not in hidden  # Q20: stay visible
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "UPDATE OF ativo, deploy_scope, exibir_no_site, destaque_no_site, nome, descricao, descricao_publica, icone" in sql
    # 5 top-level client_payload keys (<= GitHub's 10); the projection is nested.
    for key in ("'active'", "'live'", "'site_catalog'", "'op'", "'at'"):
        assert key in sql


# --- featured products (destaque_no_site) -----------------------------------------------------

def _featured_rows(positions: dict, hidden=()):
    return [
        {"slug": s, "id": s, "nome": s.upper(), "exibir_no_site": s not in hidden,
         "destaque_no_site": positions.get(s)}
        for s in ("a", "b", "c", "d", "e", "f", "g", "h")
    ]


def test_list_public_exposes_destaque_no_site():
    out = {p.slug: p.destaque_no_site for p in svc.list_public(client=_Client(ROWS), now=0.0)}
    assert out == {"a": 1, "b": None, "c": None}


def test_destaque_ok_free_position_and_unfeature():
    db = _Client(_featured_rows({"a": 1}))
    svc.check_destaque_write(db, "b", {"destaque_no_site": 2})  # free slot: allowed
    svc.check_destaque_write(db, "a", {"destaque_no_site": None})  # un-feature: allowed
    svc.check_destaque_write(db, "a", {"destaque_no_site": 1})  # re-saving own slot: allowed


def test_destaque_rejects_duplicate_position_without_swapping():
    db = _Client(_featured_rows({"a": 1}))
    with pytest.raises(svc.DestaqueRefused) as exc:
        svc.check_destaque_write(db, "b", {"destaque_no_site": 1})
    assert exc.value.status_code == 409
    assert "posição 1 já está ocupada por 'A'" in exc.value.detail
    assert [r["destaque_no_site"] for r in db.rows if r["slug"] == "a"] == [1]  # untouched


@pytest.mark.parametrize("pos", [7, 0, -1])
def test_destaque_rejects_position_beyond_six(pos):
    db = _Client(_featured_rows({}))
    with pytest.raises(svc.DestaqueRefused) as exc:
        svc.check_destaque_write(db, "a", {"destaque_no_site": pos})
    assert exc.value.status_code == 422
    assert "1 a 6" in exc.value.detail


def test_destaque_rejects_seventh_entry_when_six_are_featured():
    # Six are featured elsewhere; "g" has no slot: position 7 is out of range and any
    # reused position 1..6 is a duplicate. Nothing is swapped.
    db = _Client(_featured_rows({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6}))
    with pytest.raises(svc.DestaqueRefused) as seventh:
        svc.check_destaque_write(db, "g", {"destaque_no_site": 7})
    assert "1 a 6" in seventh.value.detail
    with pytest.raises(svc.DestaqueRefused) as dup:
        svc.check_destaque_write(db, "g", {"destaque_no_site": 6})
    assert "já está ocupada" in dup.value.detail


def test_destaque_rejects_hidden_product():
    db = _Client(_featured_rows({}, hidden=("a",)))
    with pytest.raises(svc.DestaqueRefused) as exc:
        svc.check_destaque_write(db, "a", {"destaque_no_site": 1})
    assert "oculto do site" in exc.value.detail
    # same refusal when one PATCH hides and features together
    db2 = _Client(_featured_rows({}))
    with pytest.raises(svc.DestaqueRefused):
        svc.check_destaque_write(db2, "a", {"exibir_no_site": False, "destaque_no_site": 1})


def test_hiding_a_featured_product_is_refused():
    db = _Client(_featured_rows({"a": 1}))
    with pytest.raises(svc.DestaqueRefused) as exc:
        svc.check_destaque_write(db, "a", {"exibir_no_site": False})
    assert "Remova o destaque" in exc.value.detail
    # explicit un-feature + hide in one PATCH is fine
    svc.check_destaque_write(db, "a", {"exibir_no_site": False, "destaque_no_site": None})


def test_unrelated_patch_does_no_lookup():
    db = _Client(_featured_rows({"a": 1}))
    svc.check_destaque_write(db, "a", {"nome": "x"})
    assert db.calls == 0


def test_router_maps_refusal_and_allows_explicit_null():
    src = (BACKEND / "app" / "routers" / "products.py").read_text()
    assert "check_destaque_write" in src and "DestaqueRefused" in src
    assert '"destaque_no_site" in body.model_fields_set' in src  # explicit null survives exclude_none


def test_migration_100_destaque_constraints():
    sql = migration_sql(BACKEND / "migrations", "products_exibir_no_site")
    assert "destaque_no_site smallint" in sql
    assert "destaque_no_site BETWEEN 1 AND 6" in sql
    assert "CHECK (destaque_no_site IS NULL OR exibir_no_site)" in sql
    assert "UNIQUE INDEX" in sql
    assert "ON public.products (destaque_no_site) WHERE destaque_no_site IS NOT NULL" in sql
    for pos, slug in enumerate(("agents", "social-wiring", "erp-imobiliario", "commerce",
                                "therapy-platform", "igig"), start=1):
        assert f"('{slug}', {pos})" in sql
    assert "NOT EXISTS (SELECT 1 FROM public.products WHERE destaque_no_site IS NOT NULL)" in sql


# --- public description (descricao_publica) ---------------------------------------------------

def test_internal_descricao_never_in_public_payload():
    out = svc.list_public(client=_Client(ROWS), now=0.0)
    for p in out:
        assert "descricao" not in p.model_dump()  # only descricao_publica
    assert "SEGREDO" not in repr([p.model_dump() for p in out])
    assert "descricao" not in svc.CatalogProduct.model_fields
    assert {p.slug: p.descricao_publica for p in out} == {"a": "pub a", "b": None, "c": None}


def test_empty_public_description_is_returned_as_null():
    rows = [{**ROWS[0], "slug": "e", "descricao_publica": ""}]
    assert svc.list_public(client=_Client(rows), now=0.0)[0].descricao_publica is None


def _site_rows(exibir: bool, publica):
    return [{"slug": "x", "id": "x", "nome": "X", "exibir_no_site": exibir, "descricao_publica": publica}]


@pytest.mark.parametrize("publica", [None, "", "   "])
def test_turning_exibir_on_requires_public_description(publica):
    with pytest.raises(svc.DestaqueRefused) as exc:
        svc.check_exibir_write(_Client(_site_rows(False, publica)), "x", {"exibir_no_site": True})
    assert exc.value.detail == "Escreva a descrição pública antes de mostrar o produto no site."


def test_turning_exibir_on_ok_when_described_or_described_in_same_patch():
    svc.check_exibir_write(_Client(_site_rows(False, "texto")), "x", {"exibir_no_site": True})
    svc.check_exibir_write(
        _Client(_site_rows(False, None)), "x", {"exibir_no_site": True, "descricao_publica": "novo"}
    )
    with pytest.raises(svc.DestaqueRefused):  # blanking it in the same patch does not slip through
        svc.check_exibir_write(
            _Client(_site_rows(False, "texto")), "x", {"exibir_no_site": True, "descricao_publica": " "}
        )


def test_already_visible_rows_with_empty_description_are_not_blocked_retroactively():
    db = _Client(_site_rows(True, None))
    svc.check_exibir_write(db, "x", {"exibir_no_site": True})  # not a transition
    svc.check_exibir_write(db, "x", {"nome": "Y"})
    svc.check_exibir_write(db, "x", {"exibir_no_site": False})


def test_router_runs_exibir_check_and_schema_accepts_descricao_publica():
    from app.schemas.products import ProductUpdate

    src = (BACKEND / "app" / "routers" / "products.py").read_text()
    assert "check_exibir_write" in src
    assert ProductUpdate(descricao_publica="t").model_dump(exclude_none=True) == {"descricao_publica": "t"}


def test_migration_100_public_description_seed_and_name_fix():
    sql = migration_sql(BACKEND / "migrations", "products_exibir_no_site")
    assert "descricao_publica text" in sql
    assert "'descricao_publica', descricao_publica" in sql  # site_catalog payload ships the public one
    assert "'descricao', descricao," not in sql  # ...and never the internal one
    seeded = {
        "agents", "social-wiring", "academia-de-reciclagem", "adconnect", "commerce", "community",
        "daily-life", "erp-imobiliario", "personal-finance", "igig", "p-studio", "pilates",
        "therapy-platform", "store",
    }
    for slug in seeded:
        assert f"('{slug}', '" in sql
    assert "('orbity'," not in sql  # honest empty
    assert "AND p.descricao_publica IS NULL" in sql  # never overwrites the owner's edits on re-run
    assert "SET nome = 'Finanças Pessoais'" in sql

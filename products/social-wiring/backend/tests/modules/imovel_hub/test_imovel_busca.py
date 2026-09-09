"""`GET /api/imoveis/busca` — the picker can reach a SOLD imóvel.

🔴 THE LOAD-BEARING CLASS IS `TestRegistryOnlyIsFindable`.

Every FK an operator's work lands on — `imovel_dados` (076), `visitas` (082),
`atendimento_negociacao` (077) — points at `imovel_registry`. The only search
the UI had pointed at `imoveis`, the Vista mirror, which on prod holds 2008 of
the registry's 3017 rows. So 35% of everything the schema would accept was
untypeable, and it was the wrong 35%: an imóvel leaves the Vista catalog when
it is SOLD, i.e. exactly when its matrícula and its contract are being handled.

These tests fail against a mirror-only search by construction — every one of
them seeds an imóvel that is in the registry and NOT in the mirror.

The other thing worth reading is `TestMirrorPreferredWithSnapFallback`: the
union is not "registry instead of mirror". An ACTIVE imóvel has no `snap_*`
at all (063 writes the snapshot only at delist time), so the registry alone
could not answer a search for a live listing's título either. Neither source
is sufficient; that is why there are two.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import ORG_ID, auth


def mirror_row(codigo: str, **over) -> dict:
    """A row of the Vista mirror.

    🔴 `codigo_norm` is UPPERCASE here, unlike this module's shared
    `conftest.imovel_row` builder, which lowercases it deliberately to prove
    `dados_service` never reads the mirror. This suite is the one place in
    `imovel_hub` that DOES read it, so it needs the production shape: 076
    verified on prod that `imoveis.codigo` and
    `imovel_registry.codigo_canonical` are both already uppercase everywhere.
    """
    row = {
        "org_id": ORG_ID,
        "codigo": codigo,
        "codigo_norm": codigo,
        "titulo": "Apartamento amplo",
        "empreendimento": "Edifício Aurora",
        "logradouro": "Rua das Palmeiras",
        "numero": "320",
        "complemento": "apto 91",
        "bairro": "Pinheiros",
        "cidade": "São Paulo",
        "uf": "SP",
        "cep": "05422-000",
        "foto_destaque": "https://cdn.example/one.jpg",
        "corretores": [{"nome": "Ana Prado"}],
    }
    row.update(over)
    return row


def registry_row(codigo: str, *, ativo=True, **snap) -> dict:
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo_canonical": codigo,
        "codigo_display": codigo,
        "ativo_no_vista": ativo,
        "origem_descoberta": "vista_sync",
        "snap_titulo": snap.get("titulo"),
        "snap_bairro": snap.get("bairro"),
        "snap_cidade": snap.get("cidade"),
        "snap_uf": snap.get("uf"),
        "snap_foto_destaque": snap.get("foto"),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    return row


def seed_busca(scoped, *, registry, mirror, dados=None) -> None:
    scoped.set_table_data("imovel_registry", registry)
    scoped.set_table_data("imoveis", mirror)
    scoped.set_table_data("imovel_dados", dados or [])


def buscar(client, termo: str, **params) -> dict:
    resp = client.get(
        "/api/imoveis/busca",
        params={"q": termo, **params},
        headers=auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def codigos(payload: dict) -> list[str]:
    return [i["codigo"] for i in payload["items"]]


class TestRegistryOnlyIsFindable:
    """🔴 The sold imóvel — the reason this endpoint exists at all."""

    def test_an_imovel_absent_from_the_mirror_is_still_found_by_codigo(
        self, client, scoped
    ):
        # ONE4770 sold in 2024 and left the Vista catalog. It is in the
        # registry, it is what every FK accepts, and `GET /api/imoveis?search=`
        # cannot see it.
        seed_busca(
            scoped,
            registry=[registry_row("ONE4770", ativo=False, titulo="Casa vendida")],
            mirror=[],
        )
        assert codigos(buscar(client, "ONE4770")) == ["ONE4770"]

    def test_it_is_found_by_its_snapshot_titulo_too(self, client, scoped):
        seed_busca(
            scoped,
            registry=[
                registry_row("CA5180", ativo=False, titulo="Sobrado no Butantã")
            ],
            mirror=[],
        )
        assert codigos(buscar(client, "Butantã")) == ["CA5180"]

    def test_the_result_says_it_left_the_catalog_rather_than_hiding_it(
        self, client, scoped
    ):
        """A delisted imóvel is a first-class answer, LABELLED — not filtered
        out, and not silently presented as if it were still listed."""
        seed_busca(
            scoped,
            registry=[registry_row("ONE4770", ativo=False, titulo="Casa vendida")],
            mirror=[],
        )
        item = buscar(client, "ONE4770")["items"][0]
        assert item["ativo_no_vista"] is False
        assert item["fonte"] == "registry"

    def test_the_mirror_only_search_would_have_returned_nothing(
        self, client, scoped
    ):
        """The counter-check, in one assertion: the same seed through the
        catalog browser is empty. If this ever starts returning the row, the
        two endpoints have been collapsed and this suite is no longer proving
        anything."""
        seed_busca(
            scoped,
            registry=[registry_row("ONE4770", ativo=False, titulo="Casa vendida")],
            mirror=[],
        )
        resp = client.get("/api/imoveis", params={"search": "ONE4770"}, headers=auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []


class TestMirrorPreferredWithSnapFallback:
    """Neither source alone answers — see the module docstring."""

    def test_a_listed_imovel_renders_from_the_mirror(self, client, scoped):
        seed_busca(
            scoped,
            registry=[registry_row("ONE9001")],
            mirror=[mirror_row("ONE9001")],
        )
        item = buscar(client, "ONE9001")["items"][0]
        assert item["fonte"] == "imoveis"
        assert item["titulo"] == "Apartamento amplo"
        # Fields the registry snapshot does not carry at all.
        assert item["logradouro"] == "Rua das Palmeiras"
        assert item["ativo_no_vista"] is True

    def test_a_live_listing_is_findable_by_titulo_which_the_registry_lacks(
        self, client, scoped
    ):
        """063 writes `snap_*` only at DELIST time, so an active row's
        registry entry has no título. A registry-only search would miss this."""
        registry = registry_row("ONE9001")
        assert registry["snap_titulo"] is None
        seed_busca(scoped, registry=[registry], mirror=[mirror_row("ONE9001")])
        assert codigos(buscar(client, "Aurora")) == []  # empreendimento is not searched
        assert codigos(buscar(client, "Apartamento amplo")) == ["ONE9001"]

    def test_both_sources_are_unioned_not_chosen_between(self, client, scoped):
        seed_busca(
            scoped,
            registry=[
                registry_row("ONE9001"),
                registry_row("ONE9002", ativo=False, titulo="Sobrado ONE9002"),
            ],
            mirror=[mirror_row("ONE9001")],
        )
        assert codigos(buscar(client, "ONE9")) == ["ONE9001", "ONE9002"]


class TestRanking:
    def test_an_exact_codigo_match_comes_first(self, client, scoped):
        seed_busca(
            scoped,
            registry=[registry_row(c) for c in ("ONE9", "ONE90", "ONE900")],
            mirror=[mirror_row(c) for c in ("ONE9", "ONE90", "ONE900")],
        )
        assert codigos(buscar(client, "ONE9"))[0] == "ONE9"

    def test_a_listed_imovel_outranks_a_delisted_one(self, client, scoped):
        seed_busca(
            scoped,
            registry=[
                registry_row("ONE9002", ativo=False, titulo="x"),
                registry_row("ONE9001", ativo=True),
            ],
            mirror=[mirror_row("ONE9001")],
        )
        assert codigos(buscar(client, "ONE9")) == ["ONE9001", "ONE9002"]

    def test_a_lowercase_term_matches_and_the_codigo_comes_back_canonical(
        self, client, scoped
    ):
        seed_busca(scoped, registry=[registry_row("ONE9001")], mirror=[])
        assert codigos(buscar(client, "one9001")) == ["ONE9001"]


class TestLimits:
    def test_limit_caps_the_list(self, client, scoped):
        seed_busca(
            scoped,
            registry=[registry_row(f"ONE900{i}") for i in range(9)],
            mirror=[],
        )
        payload = buscar(client, "ONE900", limit=3)
        assert len(payload["items"]) == 3
        # `total` describes what came back, never a catalog count — promising
        # a page that does not exist is the failure this pins.
        assert payload["total"] == 3

    def test_a_one_character_term_is_refused_rather_than_answered_empty(
        self, client, scoped
    ):
        """An empty list would be indistinguishable from "no such imóvel"."""
        seed_busca(scoped, registry=[registry_row("ONE9001")], mirror=[])
        resp = client.get("/api/imoveis/busca", params={"q": "O"}, headers=auth())
        assert resp.status_code == 422, resp.text

    def test_no_match_is_an_empty_list_not_an_error(self, client, scoped):
        seed_busca(scoped, registry=[registry_row("ONE9001")], mirror=[])
        assert buscar(client, "ZZZZ") == {"items": [], "total": 0}


class TestAuthBoundary:
    """Strict `== 401`, never `in (401, 404|422)` — a permissive tuple passes
    when the route is absent and when validation runs before auth.
    → `KB § PATTERNS/compliance/auth-boundary-false-green.md`"""

    def test_unauthenticated_busca_is_strictly_401(self, anon_client):
        resp = anon_client.get("/api/imoveis/busca", params={"q": "ONE9001"})
        assert resp.status_code == 401, resp.text

    def test_it_is_401_and_not_422_even_with_an_invalid_query(self, anon_client):
        """`q=O` is below the minimum length. Auth must still fire FIRST —
        a 422 here would mean an anonymous caller reaches validation."""
        resp = anon_client.get("/api/imoveis/busca", params={"q": "O"})
        assert resp.status_code == 401, resp.text

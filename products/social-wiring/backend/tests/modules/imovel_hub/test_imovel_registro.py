"""`GET /{codigo}/registro` — is this código known at all?

WHAT THIS PINS
--------------
- `GET /api/imoveis/{codigo}` (`app.routers.imoveis_router`) reads ONLY the
  Vista-synced mirror and 404s a manually registered código, which has no
  listing to display and never will — this route is the property page's
  "can this even open" check that survives that gap;
- a código present in the mirror answers `origem: "vista"`, read off the
  REGISTRY row's `origem_descoberta`, not off whether the mirror still has
  it today — a synced property that later sold and left `imoveis` must
  keep reporting "vista", never flip to "manual";
- a código the registry knows through any OTHER path (manual, lead, intake,
  venda, desconhecida) answers `origem: "manual"`;
- a completely unknown código is a 404, not a 200 with `registrado: false`.

Auth is not re-tested here — `test_imovel_auth_boundary.py` enumerates every
mounted route and asserts a strict 401 on each.
"""
from __future__ import annotations

from tests.modules.imovel_hub.conftest import CODIGO, auth, imovel_row, registry_row, seed


class TestRegistroStatus:
    def test_a_manually_registered_codigo_answers_manual(self, client, scoped):
        seed(
            scoped,
            registry=[registry_row(origem_descoberta="manual")],
            imoveis=[],
        )
        r = client.get(f"/api/imoveis/{CODIGO}/registro", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["codigo"] == CODIGO.upper()
        assert body["registrado"] is True
        assert body["origem"] == "manual"
        assert body["criado_em"] == "2026-01-01T00:00:00+00:00"

    def test_a_vista_synced_codigo_answers_vista(self, client, scoped):
        seed(
            scoped,
            registry=[registry_row(origem_descoberta="vista_sync")],
            imoveis=[imovel_row()],
        )
        r = client.get(f"/api/imoveis/{CODIGO}/registro", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["registrado"] is True
        assert body["origem"] == "vista"

    def test_a_sold_property_still_answers_vista_once_delisted(self, client, scoped):
        """The mirror row is gone (sold, left the Vista catalog) but the
        registry — append-only — still remembers how it was discovered."""
        seed(
            scoped,
            registry=[registry_row(origem_descoberta="vista_sync", ativo_no_vista=False)],
            imoveis=[],
        )
        r = client.get(f"/api/imoveis/{CODIGO}/registro", headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["origem"] == "vista"

    def test_a_lead_discovered_codigo_also_answers_manual(self, client, scoped):
        """Every non-Vista discovery path collapses to the same two-value
        `origem` this route promises."""
        seed(
            scoped,
            registry=[registry_row(origem_descoberta="lead")],
            imoveis=[],
        )
        r = client.get(f"/api/imoveis/{CODIGO}/registro", headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["origem"] == "manual"

    def test_an_unknown_codigo_is_404(self, client, scoped):
        seed(scoped, registry=[], imoveis=[])
        r = client.get("/api/imoveis/NUNCA-VISTO/registro", headers=auth())
        assert r.status_code == 404, r.text

    def test_the_codigo_is_matched_case_insensitively(self, client, scoped):
        seed(scoped, registry=[registry_row(codigo=CODIGO.upper())], imoveis=[])
        r = client.get(f"/api/imoveis/{CODIGO.lower()}/registro", headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["codigo"] == CODIGO.upper()

    def test_org_scoped_a_registry_row_from_another_org_is_invisible(self, client, scoped):
        row = registry_row()
        row["org_id"] = "00000000-0000-4000-8000-000000000099"
        seed(scoped, registry=[row], imoveis=[])
        r = client.get(f"/api/imoveis/{CODIGO}/registro", headers=auth())
        assert r.status_code == 404, r.text

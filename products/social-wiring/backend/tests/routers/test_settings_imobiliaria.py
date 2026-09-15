"""`/api/settings/imobiliaria` — the agency's cadastral data, plus the
office's operational answers added by migration 117 (contract F6):
`plataforma_assinatura_nome` / `plataforma_assinatura_url` (HTTPS-only),
`posse_multa_diaria` (>= 0), `prazo_pendencias_padrao_dias` (> 0, default
10).

Same DI-test-seam shape `test_settings_testemunhas.py` uses (and explains at
length in its own module docstring): `Depends(get_social_wiring_client)`
resolved via `app.dependency_overrides`, never a `unittest.mock.patch` of
our own code.

🔴 NO ROUND-TRIP (PUT-then-GET) ASSERTIONS HERE — A REAL, PRE-EXISTING MOCK
GAP, NOT SOMETHING THIS SLICE INTRODUCED
--------------------------------------------------------------------------------
`update_dados_imobiliaria` writes via `.upsert(linha, on_conflict="org_id")`.
`noctusai_lib.testing.mocks.MockRequestBuilder.upsert` is a documented no-op
today — "Upsert propagation is deferred to a follow-up project (needs
conflict-target tracking via `on_conflict`)" — so a PUT's own response (which
re-reads through `get_dados_imobiliaria` right after the upsert) can never
observe the value it just wrote, for ANY field on this table, not only the
four this migration adds. There was no pre-existing round-trip test for this
endpoint to break; writing one now would be a false-green — it would pass
even if persistence were completely broken. What IS honestly testable
against this mock is everything that happens BEFORE the DB call: the
Pydantic validation boundary.

NOC-REMEDIATE[seed]: `MockRequestBuilder.upsert` needs real conflict-target-
aware propagation (same shape `insert`/`update` already have via
`inserted_payloads`/`updated_payloads`) before a genuine round-trip test can
exist for this endpoint — 2026-09-15.
"""
from __future__ import annotations

import pytest

from app.dependencies import coerce_org_uuid, get_social_wiring_client

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


@pytest.fixture
def imobiliaria_scoped(client):
    from app.main import app

    scoped = client.mock_supabase.schema("social_wiring")
    prev = app.dependency_overrides.get(get_social_wiring_client)
    app.dependency_overrides[get_social_wiring_client] = lambda: scoped
    yield scoped
    if prev is None:
        app.dependency_overrides.pop(get_social_wiring_client, None)
    else:
        app.dependency_overrides[get_social_wiring_client] = prev


class TestGetFreshOrg:
    def test_a_fresh_org_has_no_row_and_never_404s(self, client, imobiliaria_scoped):
        r = client.get("/api/settings/imobiliaria")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["plataforma_assinatura_nome"] is None
        assert body["plataforma_assinatura_url"] is None
        assert body["posse_multa_diaria"] is None
        assert body["prazo_pendencias_padrao_dias"] is None


class TestPutValidation:
    """The Pydantic boundary — everything that happens BEFORE the (mocked,
    non-propagating) DB write, so it is genuinely observable through a 422
    vs. 200 status code regardless of the upsert gap noted in the module
    docstring."""

    def test_a_fully_valid_payload_is_accepted(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={
                "plataforma_assinatura_nome": "ClickSign",
                "plataforma_assinatura_url": "https://app.clicksign.com",
                "posse_multa_diaria": 150.0,
                "prazo_pendencias_padrao_dias": 15,
            },
        )
        assert r.status_code == 200, r.text

    def test_an_http_url_is_refused(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"plataforma_assinatura_url": "http://app.clicksign.com"},
        )
        assert r.status_code == 422, r.text

    def test_an_https_url_is_accepted(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"plataforma_assinatura_url": "https://app.clicksign.com"},
        )
        assert r.status_code == 200, r.text

    def test_a_negative_posse_multa_diaria_is_refused(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria", json={"posse_multa_diaria": -10}
        )
        assert r.status_code == 422, r.text

    def test_zero_posse_multa_diaria_is_accepted(self, client, imobiliaria_scoped):
        """`ge=0` — zero is a valid fine (none), not a data-entry error."""
        r = client.put(
            "/api/settings/imobiliaria", json={"posse_multa_diaria": 0}
        )
        assert r.status_code == 200, r.text

    def test_a_zero_prazo_pendencias_is_refused(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"prazo_pendencias_padrao_dias": 0},
        )
        assert r.status_code == 422, r.text

    def test_a_negative_prazo_pendencias_is_refused(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"prazo_pendencias_padrao_dias": -5},
        )
        assert r.status_code == 422, r.text

    def test_a_positive_prazo_pendencias_is_accepted(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"prazo_pendencias_padrao_dias": 20},
        )
        assert r.status_code == 200, r.text

    def test_extra_field_rejected(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={"plataforma_assinatura_nome": "X", "org_id": "should-not-be-settable"},
        )
        assert r.status_code == 422, r.text

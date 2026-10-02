"""`/api/settings/imobiliaria` — the agency's cadastral data, plus the
office's operational answers added by migration 117 (contract F6):
`plataforma_assinatura_nome` / `plataforma_assinatura_url` (HTTPS-only),
`posse_multa_diaria` (>= 0), `prazo_pendencias_padrao_dias` (> 0, default
10).

Same DI-test-seam shape `test_settings_testemunhas.py` uses (and explains at
length in its own module docstring): `Depends(get_social_wiring_client)`
resolved via `app.dependency_overrides`, never a `unittest.mock.patch` of
our own code.

Round trips (PUT-then-GET) are genuine here: the seed's
`MockRequestBuilder.upsert` now merges on the `on_conflict` key, which
closed the 2026-09-15 `NOC-REMEDIATE[seed]` gap this file used to carry —
see `TestSuporteContato` (migration 189).
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


class TestSuporteContato:
    """Migration 189 — the office's SUPPORT contact, separate from the
    notification recipients (owner decision 2026-10-02). The mock's `upsert`
    now propagates on the conflict key, so this is a genuine round trip."""

    def test_whatsapp_is_canonicalized_to_e164_and_round_trips(self, client, imobiliaria_scoped):
        r = client.put(
            "/api/settings/imobiliaria",
            json={
                "suporte_nome": "Suporte",
                "suporte_whatsapp": "(11) 99457-3387",
                "suporte_email": "suporte@exemplo.com.br",
            },
        )
        assert r.status_code == 200, r.text
        body = client.get("/api/settings/imobiliaria").json()
        assert body["suporte_nome"] == "Suporte"
        assert body["suporte_whatsapp"] == "+5511994573387"
        assert body["suporte_email"] == "suporte@exemplo.com.br"

    def test_an_unresolvable_whatsapp_is_refused(self, client, imobiliaria_scoped):
        r = client.put("/api/settings/imobiliaria", json={"suporte_whatsapp": "1199457"})
        assert r.status_code == 422, r.text

    def test_an_invalid_email_is_refused(self, client, imobiliaria_scoped):
        r = client.put("/api/settings/imobiliaria", json={"suporte_email": "sem-arroba"})
        assert r.status_code == 422, r.text

    def test_blank_clears_to_null(self, client, imobiliaria_scoped):
        r = client.put("/api/settings/imobiliaria", json={"suporte_whatsapp": "  "})
        assert r.status_code == 200, r.text
        assert client.get("/api/settings/imobiliaria").json()["suporte_whatsapp"] is None

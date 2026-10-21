"""`GET /api/card-hub/cep/{cep}` — the card address form's CEP lookup.

Adapter is the seed's Fake via the `get_cep_lookup_adapter` DI seam (never the network).
Auth (strict 401) is asserted here too, separately from the happy path.
"""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.cep import CepEndereco, FakeCepLookupAdapter

from app.main import app
from app.modules.card_hub.deps import get_cep_lookup_adapter
from tests.modules.card_hub.test_negociacao_estruturada import _auth


@pytest.fixture
def fake_cep():
    fake = FakeCepLookupAdapter({
        "01310-100": CepEndereco(
            cep="01310100", cidade="São Paulo", uf="SP",
            logradouro="Avenida Paulista", bairro="Bela Vista",
        )
    })
    app.dependency_overrides[get_cep_lookup_adapter] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_cep_lookup_adapter, None)


def test_resolves_a_masked_cep(client, fake_cep):
    r = client.get("/api/card-hub/cep/01310-100", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json() == {
        "cep": "01310100", "logradouro": "Avenida Paulista", "bairro": "Bela Vista",
        "cidade": "São Paulo", "uf": "SP",
    }
    assert fake_cep.lookups == ["01310100"]


def test_unknown_cep_is_404(client, fake_cep):
    assert client.get("/api/card-hub/cep/99999999", headers=_auth()).status_code == 404


def test_malformed_cep_is_400_and_never_reaches_the_adapter(client, fake_cep):
    assert client.get("/api/card-hub/cep/123", headers=_auth()).status_code == 400
    assert fake_cep.lookups == []


def test_requires_auth(anon_client):
    assert anon_client.get("/api/card-hub/cep/01310100").status_code == 401

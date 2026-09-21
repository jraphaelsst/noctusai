"""`GET/PUT /imoveis/{codigo}/endereco-registro` (migration 139 writer,
migration 147) — the confirmed short address the posse clauses print.

WHAT THESE PIN
--------------
- there is NEVER a `sugestao` key on the read (unlike título aquisitivo /
  ônus credor) — migration 139's whole point is that this value is NEVER a
  recomputed guess, only an operator's typed confirmation;
- confirming lands on `imovel_dados.endereco_registro_texto` (visible via
  `GET /api/imoveis/{codigo}/dados`), and `texto: null` clears it;
- the body key is required (unlike a PATCH, this is a PUT — an empty body is
  a 422, not a no-op).

Auth is not re-tested here — `test_matriculas_auth_boundary.py` covers it.
"""
from __future__ import annotations

from tests.modules.matriculas.conftest import CODIGO, registry_row, seed

TEXTO_CONFIRMADO = "Rua dos Exemplos, nº 7"


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestEnderecoRegistro:
    def test_unconfirmed_reads_as_null_with_no_suggestion_key(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        data = _data(client.get(f"/api/matriculas/imoveis/{CODIGO}/endereco-registro"))
        assert data["confirmado"] is None
        assert "sugestao" not in data

    def test_confirming_lands_on_imovel_dados_and_null_clears(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        url = f"/api/matriculas/imoveis/{CODIGO}/endereco-registro"

        data = _data(client.put(url, json={"texto": TEXTO_CONFIRMADO}))
        assert data["confirmado"]["texto"] == TEXTO_CONFIRMADO
        assert data["confirmado"]["confirmado_por"]

        dados = client.get(f"/api/imoveis/{CODIGO}/dados").json()
        assert dados["endereco_registro_texto"] == TEXTO_CONFIRMADO

        limpo = _data(client.put(url, json={"texto": None}))
        assert limpo["confirmado"] is None
        assert client.get(f"/api/imoveis/{CODIGO}/dados").json()["endereco_registro_texto"] is None

    def test_the_body_key_is_required(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.put(f"/api/matriculas/imoveis/{CODIGO}/endereco-registro", json={})
        assert resp.status_code == 422

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.get("/api/matriculas/imoveis/NOPE9/endereco-registro")
        assert resp.status_code == 404

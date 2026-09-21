"""Manual address override for the 4 fields `contrato_gerador.derivacao`
gates on (migration 149) — `PUT /{codigo}/endereco-manual`.

WHAT THESE PIN
--------------
- the override wins over the CRM/Vista mirror per-field, once set;
- every changed field appends an `imovel_endereco_historico` row recording
  the value in effect BEFORE the change (the mirror's, the first time) and
  who/when;
- a second override on an already-overridden field logs the PREVIOUS
  override, not the mirror again;
- `None` clears the override (falls back to the mirror) and is itself a
  logged change;
- a field left absent from the body is untouched (no history row, no
  clobber) — same absence-means-leave-alone contract `ImovelDadosPatchBody`
  already has.

Auth is not re-tested here — `test_imovel_auth_boundary.py` covers it.
"""
from __future__ import annotations

from tests.modules.imovel_hub.conftest import CODIGO, auth, imovel_row, seed


def _mirror(**extra):
    return imovel_row(
        # `busca_service.enriquecer` matches on `codigo_norm` against the
        # CANONICAL (upper-cased) código — `imovel_row()`'s own default
        # lower-cases it, which is fine for tests that never call
        # `enriquecer`, but this one does.
        codigo_norm=CODIGO.upper(),
        logradouro="Rua Antiga",
        numero="10",
        cidade="São Paulo",
        uf="SP",
        **extra,
    )


class TestOverrideWinsOverMirror:
    def test_setting_one_field_overrides_only_that_field(self, client, scoped):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        r = client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Nova, 100"},
            headers=auth(),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["endereco_manual_logradouro"] == "Rua Nova, 100"
        assert body["endereco_manual_numero"] is None
        assert body["endereco_manual_confirmado_por"] is not None
        assert body["endereco_manual_confirmado_em"] is not None

    def test_history_logs_the_mirror_value_the_first_time(self, client, scoped):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Nova, 100"},
            headers=auth(),
        )

        historico = client.get(
            f"/api/imoveis/{CODIGO}/endereco-manual/historico", headers=auth()
        ).json()["items"]
        assert len(historico) == 1
        assert historico[0]["campo"] == "logradouro"
        assert historico[0]["valor_anterior"] == "Rua Antiga"
        assert historico[0]["valor_novo"] == "Rua Nova, 100"
        assert historico[0]["alterado_por"] is not None

    def test_a_second_override_logs_the_previous_override_not_the_mirror(
        self, client, scoped
    ):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Nova, 100"},
            headers=auth(),
        )
        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Mais Nova, 200"},
            headers=auth(),
        )

        historico = client.get(
            f"/api/imoveis/{CODIGO}/endereco-manual/historico", headers=auth()
        ).json()["items"]
        assert len(historico) == 2
        # 🔴 `MockRequestBuilder.order()` is a documented no-op (validates the
        # column, never actually sorts) — see `noctusai_lib/testing/mocks.py`
        # — so "newest first" (real over Postgres) cannot be asserted
        # positionally against the mock. Sort here instead of relying on
        # fetch order.
        por_alterado_em = sorted(historico, key=lambda h: h["alterado_em"], reverse=True)
        assert por_alterado_em[0]["valor_anterior"] == "Rua Nova, 100"
        assert por_alterado_em[0]["valor_novo"] == "Rua Mais Nova, 200"
        assert por_alterado_em[1]["valor_anterior"] == "Rua Antiga"

    def test_unchanged_value_logs_nothing(self, client, scoped):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Antiga"},
            headers=auth(),
        )

        historico = client.get(
            f"/api/imoveis/{CODIGO}/endereco-manual/historico", headers=auth()
        ).json()["items"]
        assert historico == []

    def test_null_clears_the_override_and_falls_back_to_mirror(self, client, scoped):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Nova, 100"},
            headers=auth(),
        )
        r = client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": None},
            headers=auth(),
        )
        assert r.status_code == 200
        assert r.json()["endereco_manual_logradouro"] is None

        historico = client.get(
            f"/api/imoveis/{CODIGO}/endereco-manual/historico", headers=auth()
        ).json()["items"]
        # See the no-op-`.order()` note above.
        mais_recente = sorted(historico, key=lambda h: h["alterado_em"], reverse=True)[0]
        assert mais_recente["valor_anterior"] == "Rua Nova, 100"
        assert mais_recente["valor_novo"] is None

    def test_an_absent_field_is_left_alone(self, client, scoped):
        seed(scoped, imoveis=[_mirror()])
        scoped.set_table_data("imovel_endereco_historico", [])

        client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"logradouro": "Rua Nova, 100"},
            headers=auth(),
        )
        r = client.put(
            f"/api/imoveis/{CODIGO}/endereco-manual",
            json={"cidade": "Campinas"},
            headers=auth(),
        )
        body = r.json()
        assert body["endereco_manual_logradouro"] == "Rua Nova, 100"
        assert body["endereco_manual_cidade"] == "Campinas"


class TestRegistrarImovel:
    def test_registering_a_new_codigo_gives_it_an_identity(self, client, scoped):
        seed(scoped, registry=[], imoveis=[])
        r = client.post("/api/imoveis/OFFMKT01/registrar", headers=auth())
        assert r.status_code == 200
        assert r.json()["codigo"] == "OFFMKT01"

        # Now authorable — ensure_imovel no longer 404s it.
        d = client.get("/api/imoveis/OFFMKT01/dados", headers=auth())
        assert d.status_code == 200

    def test_registering_is_idempotent(self, client, scoped):
        seed(scoped, registry=[], imoveis=[])
        first = client.post("/api/imoveis/OFFMKT01/registrar", headers=auth())
        second = client.post("/api/imoveis/OFFMKT01/registrar", headers=auth())
        assert first.json() == second.json()

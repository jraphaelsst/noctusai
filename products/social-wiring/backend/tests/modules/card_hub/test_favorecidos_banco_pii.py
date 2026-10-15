"""A legacy `banco` carrying agência/conta as free text must not leak in the
masked list / viewer detail, is refused on write, and blocks readiness."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as fp
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_pagamentos import _avaliar
from tests.modules.card_hub.test_favorecidos_registro import CPF_OK, _auth, _criar, _papel

_BANCO_LEGADO = "Itaú (341) Ag. 1234 CC 56789-0"


def _linha_legada() -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "nome": "Legado", "tipo_pessoa": "PF",
        "cpf_cnpj": CPF_OK, "banco": _BANCO_LEGADO, "agencia": None, "conta": None,
        "pix": None, "pix_tipo": None, "ativo": True,
    }


class TestBancoComDadosDeContaNaoVaza:
    def test_list_exposes_only_the_bank_name_and_flags_review(self, client, scoped):
        scoped.set_table_data("favorecidos", [_linha_legada()])
        _papel(client, "member")
        item = client.get("/api/card-hub/favorecidos", headers=_auth()).json()["items"][0]
        assert item["banco"] == "Itaú (341)"
        assert item["banco_requer_revisao"] is True
        assert "Ag. 1234" not in str(item) and "56789-0" not in str(item)

    def test_clean_banco_is_not_flagged(self, client, scoped):
        row = {**_linha_legada(), "banco": "Itaú (341)"}
        scoped.set_table_data("favorecidos", [row])
        _papel(client, "member")
        item = client.get("/api/card-hub/favorecidos", headers=_auth()).json()["items"][0]
        assert item["banco"] == "Itaú (341)" and item["banco_requer_revisao"] is False

    def test_viewer_detail_is_sanitised_too(self, client, scoped):
        row = _linha_legada()
        scoped.set_table_data("favorecidos", [row])
        _papel(client, "viewer")
        det = client.get(f"/api/card-hub/favorecidos/{row['id']}", headers=_auth()).json()
        assert det["banco"] == "Itaú (341)" and det["banco_requer_revisao"] is True
        assert "Ag. 1234" not in str(det) and "56789-0" not in str(det)

    def test_create_moves_agencia_and_conta_out_of_banco(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        r = _criar(client, banco=_BANCO_LEGADO, agencia=None, conta=None)
        assert r.status_code == 201, r.text
        linha = r.json()
        assert (linha["banco"], linha["agencia"], linha["conta"]) == (
            "Itaú (341)", "1234", "56789-0",
        )

    def test_create_and_patch_refuse_conta_data_that_does_not_split(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        r = _criar(client, banco="Itaú CC 56789-0", agencia=None, conta=None)
        assert r.status_code == 400 and "Agência e Conta" in r.text
        fid = _criar(client).json()["id"]
        r = client.patch(
            f"/api/card-hub/favorecidos/{fid}", json={"banco": "Bradesco CC 1234"},
            headers=_auth(),
        )
        assert r.status_code == 400 and "Agência e Conta" in r.text


class TestReadinessBancoComDadosDeConta:
    def test_banco_with_account_digits_and_no_conta_is_not_ready(self):
        d = fp.sinal_em_partes()
        assert _avaliar(d, 1).pronto
        favs = [
            replace(f, banco=_BANCO_LEGADO, agencia=None, conta=None, pix="a@b.com")
            if f.id == "fav-v" else f
            for f in d.favorecidos
        ]
        av = _avaliar(replace(d, favorecidos=favs), 1)
        assert not av.pronto
        assert "estão no campo Banco" in str(av.faltando)


class TestSepararBanco:
    def test_splits_the_full_triple(self):
        from app.modules.card_hub.banco_texto import separar_banco

        assert separar_banco(_BANCO_LEGADO) == ("Itaú (341)", "1234", "56789-0")
        assert separar_banco("Bradesco, Agência: 0123-4, Conta Corrente 98765-X") == (
            "Bradesco", "0123-4", "98765-X",
        )

    def test_any_other_shape_is_left_alone(self):
        from app.modules.card_hub.banco_texto import separar_banco

        for texto in ("Itaú (341)", "Itaú CC 56789-0", "Itaú Ag. 1234", "Ag. 1234 CC 5 obs", None):
            assert separar_banco(texto) is None

    def test_filled_fields_are_never_overwritten(self):
        from app.modules.card_hub.banco_texto import com_banco_separado

        v = {"banco": _BANCO_LEGADO, "agencia": "9", "conta": None}
        assert com_banco_separado(v) is v

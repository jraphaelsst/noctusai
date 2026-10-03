"""Migration 192 — the parcela API for the payment shapes the generator now
prints: a parcela split among several favorecidos (`favorecidos_divisao`),
the FGTS portion of the financing parcela (`valor_fgts`), and the
'vendedores_boleto' ônus quitação.

Wrong is refused (400/404), missing is saved — same posture as the rest of
`negociacao_estruturada_service` (module header). Synthetic data only.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_negociacao_termos import (
    _criar_parcela,
    _estruturada,
    _mensagem_400,
    _patch_parcela,
    _put_termos,
    _seed,
)


def _fav(aid: str, nome: str) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "nome": nome,
        "cpf_cnpj": None, "banco": "Banco Exemplo", "agencia": "0001", "conta": "1-1",
        "pix": None, "created_at": "2026-01-01T00:00:00+00:00",
    }


def _seed_favs(scoped):
    cid, aid = _seed(scoped)
    f1, f2 = _fav(aid, "Fulano Exemplo"), _fav(aid, "Beltrana Exemplo")
    scoped.set_table_data("atendimento_favorecidos", [f1, f2])
    scoped.set_table_data("atendimento_parcela_favorecidos", [])
    return cid, aid, f1, f2


class TestFavorecidosDivisao:
    def test_create_round_trips_the_split(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        r = _criar_parcela(
            client, cid, tipo="sinal", valor="50000.00",
            favorecidos_divisao=[
                {"favorecido_id": f1["id"], "valor": "30000.00"},
                {"favorecido_id": f2["id"], "valor": "20000.00"},
            ],
        )
        assert r.status_code == 201, r.text
        parcela = r.json()["parcelas"][0]
        assert parcela["favorecido_id"] is None
        assert [(s["favorecido_id"], s["valor"], s["percentual"]) for s in parcela["favorecidos_divisao"]] == [
            (f1["id"], "30000.00", None), (f2["id"], "20000.00", None),
        ]

    def test_patch_replaces_and_empty_list_removes(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        pid = _criar_parcela(
            client, cid, tipo="sinal", valor="50000.00",
            favorecidos_divisao=[
                {"favorecido_id": f1["id"], "percentual": "50"},
                {"favorecido_id": f2["id"], "percentual": "50"},
            ],
        ).json()["parcelas"][0]["id"]
        r = _patch_parcela(
            client, cid, pid,
            favorecidos_divisao=[
                {"favorecido_id": f2["id"], "percentual": "60"},
                {"favorecido_id": f1["id"], "percentual": "40"},
            ],
        )
        assert r.status_code == 200, r.text
        assert [s["percentual"] for s in r.json()["parcelas"][0]["favorecidos_divisao"]] == ["60", "40"]
        # Swap the split for a single favorecido in ONE patch.
        r = _patch_parcela(client, cid, pid, favorecidos_divisao=[], favorecido_id=f1["id"])
        assert r.status_code == 200, r.text
        p = r.json()["parcelas"][0]
        assert p["favorecidos_divisao"] == [] and p["favorecido_id"] == f1["id"]

    def test_a_single_favorecido_and_a_split_together_are_refused(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="sinal", valor="1.00", favorecido_id=f1["id"],
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f2["id"]}],
        ))
        assert "favorecido único" in msg

    def test_setting_a_favorecido_on_a_split_parcela_is_refused(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        pid = _criar_parcela(
            client, cid, tipo="sinal", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f2["id"]}],
        ).json()["parcelas"][0]["id"]
        msg = _mensagem_400(_patch_parcela(client, cid, pid, favorecido_id=f1["id"]))
        assert "dividida" in msg

    def test_one_share_is_refused(self, client, scoped):
        cid, _aid, f1, _f2 = _seed_favs(scoped)
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="sinal", valor="1.00", favorecidos_divisao=[{"favorecido_id": f1["id"]}],
        ))
        assert "pelo menos dois" in msg

    def test_mixing_valor_and_percentual_is_refused(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="sinal", valor="2.00",
            favorecidos_divisao=[
                {"favorecido_id": f1["id"], "valor": "1.00"},
                {"favorecido_id": f2["id"], "percentual": "50"},
            ],
        ))
        assert "mistura" in msg

    def test_valor_and_percentual_on_one_share_is_rejected_at_the_boundary(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        r = _criar_parcela(
            client, cid, tipo="sinal", valor="2.00",
            favorecidos_divisao=[
                {"favorecido_id": f1["id"], "valor": "1.00", "percentual": "50"},
                {"favorecido_id": f2["id"]},
            ],
        )
        assert r.status_code == 422, r.text

    def test_the_same_favorecido_twice_is_refused(self, client, scoped):
        cid, _aid, f1, _f2 = _seed_favs(scoped)
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="sinal", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f1["id"]}],
        ))
        assert "duas vezes" in msg

    def test_a_split_on_a_financing_parcela_is_refused(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="financiamento", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f2["id"]}],
        ))
        assert "divididas" in msg

    def test_a_favorecido_of_another_deal_is_a_404(self, client, scoped):
        cid, _aid, f1, _f2 = _seed_favs(scoped)
        estranho = str(uuid4())
        r = _criar_parcela(
            client, cid, tipo="sinal", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": estranho}],
        )
        assert r.status_code == 404, r.text
        assert scoped.table("atendimento_negociacao_parcelas").select("*").execute().data == []

    def test_changing_tipo_away_from_a_paid_tipo_needs_the_split_removed(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        pid = _criar_parcela(
            client, cid, tipo="sinal", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f2["id"]}],
        ).json()["parcelas"][0]["id"]
        msg = _mensagem_400(_patch_parcela(client, cid, pid, tipo="financiamento"))
        assert "divisão" in msg

    def test_removing_the_parcela_removes_its_split(self, client, scoped):
        cid, _aid, f1, f2 = _seed_favs(scoped)
        pid = _criar_parcela(
            client, cid, tipo="sinal", valor="1.00",
            favorecidos_divisao=[{"favorecido_id": f1["id"]}, {"favorecido_id": f2["id"]}],
        ).json()["parcelas"][0]["id"]
        r = client.delete(f"/api/clientes/{cid}/negociacao/parcelas/{pid}", headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 204, r.text
        assert scoped.table("atendimento_parcela_favorecidos").select("*").execute().data == []


class TestValorFgts:
    def test_round_trips_on_the_financing_parcela(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_parcela(client, cid, tipo="financiamento", valor="400000.00", valor_fgts="100000.00")
        assert r.status_code == 201, r.text
        assert r.json()["parcelas"][0]["valor_fgts"] == "100000.00"

    def test_patch_sets_and_clears(self, client, scoped):
        cid, _aid = _seed(scoped)
        pid = _criar_parcela(client, cid, tipo="financiamento", valor="400000.00").json()["parcelas"][0]["id"]
        assert _patch_parcela(client, cid, pid, valor_fgts="50000.00").json()["parcelas"][0]["valor_fgts"] == "50000.00"
        assert _patch_parcela(client, cid, pid, valor_fgts=None).json()["parcelas"][0]["valor_fgts"] is None

    def test_only_on_a_financing_parcela(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_criar_parcela(client, cid, tipo="sinal", valor="1000.00", valor_fgts="10.00"))
        assert "financiamento" in msg

    def test_not_the_whole_parcela(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_criar_parcela(client, cid, tipo="financiamento", valor="100.00", valor_fgts="100.00"))
        assert "menor" in msg

    def test_lowering_the_parcela_below_its_fgts_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        pid = _criar_parcela(
            client, cid, tipo="financiamento", valor="400000.00", valor_fgts="100000.00",
        ).json()["parcelas"][0]["id"]
        msg = _mensagem_400(_patch_parcela(client, cid, pid, valor="90000.00"))
        assert "menor" in msg

    def test_changing_tipo_with_fgts_set_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        pid = _criar_parcela(
            client, cid, tipo="financiamento", valor="400000.00", valor_fgts="100000.00",
        ).json()["parcelas"][0]["id"]
        msg = _mensagem_400(_patch_parcela(client, cid, pid, tipo="direta"))
        assert "financiamento" in msg


class TestOnusQuitacaoBoleto:
    def test_vendedores_boleto_round_trips(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, onus_quitacao="vendedores_boleto", onus_prazo_dias=30)
        assert r.status_code == 200, r.text
        termos = _estruturada(client, cid)["termos"]
        assert termos["onus_quitacao"] == "vendedores_boleto"
        assert termos["onus_prazo_dias"] == 30

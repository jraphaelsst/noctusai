"""Termos do negócio (migration 114) — the clauses the contract generator
prints: posse, itens integrantes / ad corpus, ônus, confissão de dívida,
corretagem, permuta-as-payment, PF/PJ qualification of intermediários.

THE CLAIMS WORTH DEFENDING
--------------------------
1. **Wrong is refused, missing is reported.** A negative prazo, juros outside
   0–100% a.m., an invalid CPF/CNPJ, a marco 'parcela' that names no parcela
   → 400 VALIDATION_ERROR with a pt-BR message. A permuta parcela with no
   imóvel yet, a deal with no posse clause → saved, listed in `completude`.
2. **Everything a clause points at belongs to THIS deal and THIS org.** A
   parcela of another atendimento, an ativo of another org (RLS-shaped: the
   fake holds the row, the service must not see it) → 404 naming the id.
3. **A permuta parcela is paid with permuta CURRENCY only** —
   `natureza='permuta_imovel'`, never a catalog listing, never linked to two
   parcelas of the same deal.
4. **A parcela a clause cites cannot vanish from under it** — 409 until the
   marco changes.

All personal data below is synthetic: checksum-valid test documents, never a
real person's.

Auth is not re-tested here — `test_auth_boundary_negociacao_estruturada.py`
asserts a strict 401 on every route this surface mounts, PUT /termos included.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.modules.card_hub.negociacao_estruturada_service import TERMOS_CAMPOS
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

OUTRA_ORG = str(uuid4())

#: Synthetic, checksum-valid documents.
CPF = "111.444.777-35"
CPF_NU = "11144477735"
CPF_REPRESENTANTE = "529.982.247-25"
CNPJ = "11.222.333/0001-81"
CNPJ_NU = "11222333000181"
CNPJ_ALFANUMERICO = "12.ABC.345/01DE-35"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str) -> dict:
    return {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }


def _negociacao_row(aid: str) -> dict:
    return {
        "atendimento_id": aid,
        "org_id": ORG_ID,
        "imovel_codigo": None,
        "valor_negociado": "500000.00",
        "pct_comissao": "6",
        "tem_parceria": False,
        "pct_parceria": "50",
        "pct_agencia": "50",
        "pct_agentes": "45",
        "pct_captador": "5",
        "formas_pagamento": None,
        "parcelas": None,
        "financiamento": False,
        "fgts": False,
        "observacoes": None,
        "posse_data": None,
        "posse_condicoes": None,
        "permuta_ativo_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }


def _ativo(*, natureza: str = "permuta_imovel", org_id: str = ORG_ID) -> dict:
    return {"id": str(uuid4()), "org_id": org_id, "natureza": natureza}


def _seed(scoped, *, ativos=None, parcelas=None, favorecidos=None):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("cliente_membros", [])
    scoped.set_table_data("lead_corretores", [])
    scoped.set_table_data("atendimento_negociacao", [_negociacao_row(aid)])
    scoped.set_table_data("negociacao_defaults", [])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("atendimento_negociacao_parcelas", parcelas or [])
    scoped.set_table_data("atendimento_favorecidos", favorecidos or [])
    scoped.set_table_data("atendimento_intermediarios", [])
    scoped.set_table_data("atendimento_negociacao_termos", [])
    scoped.set_table_data("atendimento_parcela_permuta_ativos", [])
    scoped.set_table_data("permuta_ativos", ativos or [])
    return cid, aid


def _estruturada(client, cid) -> dict:
    r = client.get(f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth())
    assert r.status_code == 200, r.text
    return r.json()


def _put_termos(client, cid, **campos):
    return client.put(
        f"/api/clientes/{cid}/negociacao/termos", json=campos, headers=_auth()
    )


def _criar_parcela(client, cid, **body):
    return client.post(
        f"/api/clientes/{cid}/negociacao/parcelas", json=body, headers=_auth()
    )


def _patch_parcela(client, cid, parcela_id, **body):
    return client.patch(
        f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}",
        json=body, headers=_auth(),
    )


def _criar_intermediario(client, cid, **body):
    return client.post(
        f"/api/clientes/{cid}/negociacao/intermediarios",
        json={"nome": "Parceira Imóveis", **body}, headers=_auth(),
    )


def _mensagem_400(r) -> str:
    assert r.status_code == 400, r.text
    erro = r.json()["error"]
    assert erro["code"] == "VALIDATION_ERROR"
    return erro["message"]


def _parcela_de_outro_atendimento() -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": str(uuid4()),
        "tipo": "financiamento", "valor": "100.00", "vencimento": None,
        "evento": None, "forma_pagamento": None, "favorecido_id": None,
        "confissao_divida": False, "dispara_corretagem": False, "ordem": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ─── termos: storage + contract ───────────────────────────────────────────


class TestTermosRoundTrip:
    def test_a_deal_with_no_termos_reads_every_clause_as_null(self, client, scoped):
        cid, _aid = _seed(scoped)
        body = _estruturada(client, cid)
        assert set(body["termos"]) == set(TERMOS_CAMPOS)
        assert all(v is None for v in body["termos"].values())
        assert "posse" in body["completude"]["faltando"]

    def test_put_round_trips_every_clause(self, client, scoped):
        cid, _aid = _seed(scoped)
        parcela_id = _criar_parcela(
            client, cid, tipo="financiamento", valor="300000.00"
        ).json()["parcelas"][0]["id"]

        r = _put_termos(
            client, cid,
            posse_prazo_dias=30, posse_marco="parcela",
            posse_marco_parcela_id=parcela_id,
            permuta_posse_prazo_dias=0, permuta_posse_marco="assinatura",
            permuta_obrigacoes_entrega="Entregar livre de pessoas e coisas",
            itens_integrantes="Armários planejados da cozinha",
            ad_corpus=True,
            obrigacoes_vendedor="Quitar condomínio até a posse",
            onus_quitacao="interveniente_quitante", onus_prazo_dias=60,
            confissao_juros_am="1.5", confissao_garantia="Nota promissória",
            corretagem_contratantes="vendedores", corretagem_num_parcelas=2,
        )
        assert r.status_code == 200, r.text
        termos = r.json()["termos"]
        assert termos["posse_prazo_dias"] == 30
        assert termos["posse_marco"] == "parcela"
        assert termos["posse_marco_parcela_id"] == parcela_id
        assert termos["permuta_posse_prazo_dias"] == 0
        assert termos["permuta_posse_marco"] == "assinatura"
        assert termos["permuta_posse_marco_parcela_id"] is None
        assert termos["itens_integrantes"] == "Armários planejados da cozinha"
        assert termos["ad_corpus"] is True
        assert termos["onus_quitacao"] == "interveniente_quitante"
        assert termos["onus_prazo_dias"] == 60
        assert Decimal(termos["confissao_juros_am"]) == Decimal("1.5")
        assert termos["corretagem_contratantes"] == "vendedores"
        assert termos["corretagem_num_parcelas"] == 2
        # And the read path returns the same thing.
        assert _estruturada(client, cid)["termos"] == termos

    def test_put_is_a_whole_replacement_absent_keys_become_null(self, client, scoped):
        cid, _aid = _seed(scoped)
        _put_termos(client, cid, itens_integrantes="Ar-condicionado", ad_corpus=False)
        r = _put_termos(client, cid, obrigacoes_vendedor="Entregar as chaves")
        assert r.status_code == 200, r.text
        termos = r.json()["termos"]
        assert termos["obrigacoes_vendedor"] == "Entregar as chaves"
        assert termos["itens_integrantes"] is None
        assert termos["ad_corpus"] is None
        # One row per deal — the second PUT updated, it did not insert.
        assert len(scoped.table("atendimento_negociacao_termos").select("*").execute().data) == 1

    def test_an_absent_itens_ausente_flag_is_stored_false_never_null(self, client, scoped):
        """🔴 Migration 163's column is NOT NULL — a PUT that omits it (every
        client before the explicit control) must store `False`, not the null
        a whole-replacement PUT writes for every other absent key."""
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, obrigacoes_vendedor="Entregar as chaves")
        assert r.status_code == 200, r.text
        assert r.json()["termos"]["itens_integrantes_ausente_confirmado"] is False
        linha = scoped.table("atendimento_negociacao_termos").select("*").execute().data[0]
        assert linha["itens_integrantes_ausente_confirmado"] is False

    def test_confirming_no_itens_integrantes_round_trips(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, itens_integrantes_ausente_confirmado=True, ad_corpus=False)
        assert r.status_code == 200, r.text
        termos = r.json()["termos"]
        assert termos["itens_integrantes_ausente_confirmado"] is True
        assert termos["itens_integrantes"] is None
        assert termos["ad_corpus"] is False

    def test_listing_items_and_confirming_none_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(
            client, cid, itens_integrantes="Armários", itens_integrantes_ausente_confirmado=True,
        )
        assert r.status_code == 400, r.text
        assert scoped.table("atendimento_negociacao_termos").select("*").execute().data == []

    def test_blank_text_is_stored_as_null_not_as_an_empty_clause(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, itens_integrantes="   ")
        assert r.json()["termos"]["itens_integrantes"] is None

    def test_a_posse_clause_satisfies_completude(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, posse_marco="assinatura", posse_prazo_dias=15)
        assert "posse" not in r.json()["completude"]["faltando"]

    def test_a_marco_without_its_prazo_is_still_incomplete_not_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, posse_marco="protocolo_registro")
        assert r.status_code == 200, r.text
        assert "posse" in r.json()["completude"]["faltando"]


class TestTermosValidation:
    def test_marco_parcela_without_the_parcela_is_refused_by_name(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_put_termos(client, cid, posse_marco="parcela", posse_prazo_dias=10))
        assert "informe a parcela" in msg

    def test_a_parcela_id_without_marco_parcela_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        parcela_id = _criar_parcela(client, cid, tipo="sinal", valor="1.00").json()["parcelas"][0]["id"]
        msg = _mensagem_400(_put_termos(
            client, cid, posse_marco="assinatura", posse_marco_parcela_id=parcela_id
        ))
        assert "só se aplica" in msg

    def test_the_permuta_marco_follows_the_same_rule(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_put_termos(client, cid, permuta_posse_marco="parcela"))
        assert "imóvel da permuta" in msg

    def test_a_marco_parcela_from_another_deal_is_a_404_not_a_500(self, client, scoped):
        estranha = _parcela_de_outro_atendimento()
        cid, _aid = _seed(scoped, parcelas=[estranha])
        r = _put_termos(
            client, cid, posse_marco="parcela", posse_marco_parcela_id=estranha["id"]
        )
        assert r.status_code == 404, r.text
        assert estranha["id"] in r.text

    def test_a_negative_prazo_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_put_termos(client, cid, onus_prazo_dias=-1))
        assert "não pode ser negativo" in msg

    def test_zero_corretagem_parcelas_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_put_termos(client, cid, corretagem_num_parcelas=0))
        assert "maior que zero" in msg

    def test_juros_outside_0_to_100_are_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_put_termos(client, cid, confissao_juros_am="150"))
        assert "entre 0 e 100" in msg
        _mensagem_400(_put_termos(client, cid, confissao_juros_am="-0.5"))

    def test_an_unknown_vocabulary_value_is_rejected_at_the_boundary(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, posse_marco="entrega_chaves")
        assert r.status_code == 422

    def test_an_unknown_key_is_rejected_not_silently_dropped(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _put_termos(client, cid, posse_data="2026-06-01")
        assert r.status_code == 422

    def test_a_refused_put_writes_nothing(self, client, scoped):
        cid, _aid = _seed(scoped)
        _put_termos(client, cid, itens_integrantes="x", onus_prazo_dias=-5)
        assert scoped.table("atendimento_negociacao_termos").select("*").execute().data == []


class TestParcelaCitedByAClause:
    def test_the_posse_marco_parcela_cannot_be_removed_until_the_marco_changes(
        self, client, scoped
    ):
        cid, _aid = _seed(scoped)
        parcela_id = _criar_parcela(
            client, cid, tipo="financiamento", valor="300000.00"
        ).json()["parcelas"][0]["id"]
        _put_termos(
            client, cid, posse_marco="parcela", posse_marco_parcela_id=parcela_id,
            posse_prazo_dias=5,
        )

        r = client.delete(
            f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}", headers=_auth()
        )
        assert r.status_code == 409, r.text
        assert "marco da posse" in r.json()["error"]["message"]

        _put_termos(client, cid, posse_marco="assinatura", posse_prazo_dias=5)
        r = client.delete(
            f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}", headers=_auth()
        )
        assert r.status_code == 204


# ─── permuta as payment ───────────────────────────────────────────────────


class TestPermutaParcela:
    def test_one_parcela_paid_with_two_matriculas(self, client, scoped):
        a1, a2 = _ativo(), _ativo()
        cid, _aid = _seed(scoped, ativos=[a1, a2])
        r = _criar_parcela(
            client, cid, tipo="permuta", valor="200000.00",
            permuta_ativo_ids=[a1["id"], a2["id"]],
        )
        assert r.status_code == 201, r.text
        body = r.json()
        parcela = body["parcelas"][0]
        assert parcela["tipo"] == "permuta"
        assert parcela["permuta_ativo_ids"] == [a1["id"], a2["id"]]
        # The swap is part of the price — it counts against the saldo.
        assert body["saldo_nao_alocado"] == "300000.00"
        assert "parcela_permuta_sem_imoveis" not in body["completude"]["faltando"]

    def test_a_duplicated_id_in_the_request_links_once(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        r = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00",
            permuta_ativo_ids=[a1["id"], a1["id"]],
        )
        assert r.json()["parcelas"][0]["permuta_ativo_ids"] == [a1["id"]]

    def test_an_ativo_of_another_org_is_a_404_naming_it(self, client, scoped):
        estranho = _ativo(org_id=OUTRA_ORG)
        cid, _aid = _seed(scoped, ativos=[estranho])
        r = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[estranho["id"]]
        )
        assert r.status_code == 404, r.text
        assert estranho["id"] in r.text
        # Refused before anything was written.
        assert scoped.table("atendimento_negociacao_parcelas").select("*").execute().data == []

    def test_a_catalog_listing_is_not_payment_currency(self, client, scoped):
        listing = _ativo(natureza="imovel")
        cid, _aid = _seed(scoped, ativos=[listing])
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[listing["id"]]
        ))
        assert "não é um imóvel de permuta" in msg

    def test_ativos_on_a_non_permuta_parcela_are_refused(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="sinal", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ))
        assert "tipo permuta" in msg

    def test_one_ativo_cannot_pay_two_parcelas_of_the_same_deal(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        _criar_parcela(client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]])
        msg = _mensagem_400(_criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ))
        assert "já está vinculado" in msg

    def test_a_permuta_parcela_with_no_imovel_yet_is_saved_and_reported(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_parcela(client, cid, tipo="permuta", valor="200000.00")
        assert r.status_code == 201, r.text
        assert "parcela_permuta_sem_imoveis" in r.json()["completude"]["faltando"]

    def test_patch_replaces_the_linked_set(self, client, scoped):
        a1, a2 = _ativo(), _ativo()
        cid, _aid = _seed(scoped, ativos=[a1, a2])
        parcela_id = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ).json()["parcelas"][0]["id"]
        r = _patch_parcela(client, cid, parcela_id, permuta_ativo_ids=[a2["id"]])
        assert r.status_code == 200, r.text
        assert r.json()["parcelas"][0]["permuta_ativo_ids"] == [a2["id"]]

    def test_relinking_the_same_ativo_to_its_own_parcela_is_not_a_conflict(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        parcela_id = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ).json()["parcelas"][0]["id"]
        r = _patch_parcela(client, cid, parcela_id, permuta_ativo_ids=[a1["id"]])
        assert r.status_code == 200, r.text

    def test_changing_the_tipo_of_a_linked_parcela_is_refused(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        parcela_id = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ).json()["parcelas"][0]["id"]
        msg = _mensagem_400(_patch_parcela(client, cid, parcela_id, tipo="saldo"))
        assert "remova os imóveis" in msg

    def test_changing_the_tipo_and_clearing_the_links_together_is_accepted(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        parcela_id = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ).json()["parcelas"][0]["id"]
        r = _patch_parcela(client, cid, parcela_id, tipo="saldo", permuta_ativo_ids=[])
        assert r.status_code == 200, r.text
        parcela = r.json()["parcelas"][0]
        assert parcela["tipo"] == "saldo"
        assert parcela["permuta_ativo_ids"] == []

    def test_removing_a_permuta_parcela_removes_its_links(self, client, scoped):
        a1 = _ativo()
        cid, _aid = _seed(scoped, ativos=[a1])
        parcela_id = _criar_parcela(
            client, cid, tipo="permuta", valor="1.00", permuta_ativo_ids=[a1["id"]]
        ).json()["parcelas"][0]["id"]
        r = client.delete(
            f"/api/clientes/{cid}/negociacao/parcelas/{parcela_id}", headers=_auth()
        )
        assert r.status_code == 204
        assert scoped.table("atendimento_parcela_permuta_ativos").select("*").execute().data == []


class TestDisparaCorretagem:
    def test_round_trips_on_create_and_patch(self, client, scoped):
        cid, _aid = _seed(scoped)
        created = _criar_parcela(client, cid, tipo="sinal", valor="50000.00", dispara_corretagem=True)
        parcela = created.json()["parcelas"][0]
        assert parcela["dispara_corretagem"] is True

        r = _patch_parcela(client, cid, parcela["id"], dispara_corretagem=False)
        assert r.json()["parcelas"][0]["dispara_corretagem"] is False

    def test_defaults_to_false(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_parcela(client, cid, tipo="sinal", valor="1.00")
        assert r.json()["parcelas"][0]["dispara_corretagem"] is False

    def test_an_explicit_null_on_a_not_null_column_is_a_named_400(self, client, scoped):
        cid, _aid = _seed(scoped)
        parcela_id = _criar_parcela(client, cid, tipo="sinal", valor="1.00").json()["parcelas"][0]["id"]
        assert "dispara_corretagem" in _mensagem_400(
            _patch_parcela(client, cid, parcela_id, dispara_corretagem=None)
        )
        assert "valor" in _mensagem_400(_patch_parcela(client, cid, parcela_id, valor=None))


# ─── intermediários: PF/PJ qualification ─────────────────────────────────


class TestIntermediarioQualificacao:
    def test_a_pf_is_stored_normalised_and_its_tipo_inferred(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_intermediario(
            client, cid, documento=CPF, email="corretora@example.com",
            endereco_cep="01310-100", endereco_logradouro="Av. Exemplo",
            endereco_numero="1000", endereco_bairro="Centro",
            endereco_cidade="São Paulo", endereco_uf="sp",
        )
        assert r.status_code == 201, r.text
        item = r.json()["intermediarios"][0]
        assert item["pessoa_tipo"] == "pf"
        assert item["documento"] == CPF_NU
        assert item["email"] == "corretora@example.com"
        assert item["endereco_cep"] == "01310100"
        assert item["endereco_uf"] == "SP"

    def test_a_pj_with_its_representante(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_intermediario(
            client, cid, pessoa_tipo="pj", documento=CNPJ,
            representante_nome="Sócia Administradora", representante_cpf=CPF_REPRESENTANTE,
        )
        assert r.status_code == 201, r.text
        item = r.json()["intermediarios"][0]
        assert item["pessoa_tipo"] == "pj"
        assert item["documento"] == CNPJ_NU
        assert item["representante_cpf"] == "52998224725"

    def test_an_alphanumeric_cnpj_is_accepted(self, client, scoped):
        cid, _aid = _seed(scoped)
        r = _criar_intermediario(client, cid, documento=CNPJ_ALFANUMERICO)
        assert r.status_code == 201, r.text
        item = r.json()["intermediarios"][0]
        assert item["documento"] == "12ABC34501DE35"
        assert item["pessoa_tipo"] == "pj"

    def test_a_cpf_with_wrong_check_digits_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        assert "CPF inválido" in _mensagem_400(_criar_intermediario(client, cid, documento="111.444.777-36"))

    def test_a_cnpj_with_wrong_check_digits_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        assert "CNPJ inválido" in _mensagem_400(_criar_intermediario(client, cid, documento="11.222.333/0001-82"))

    def test_a_document_of_neither_shape_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        assert "CPF (11 dígitos) ou um CNPJ" in _mensagem_400(_criar_intermediario(client, cid, documento="12345"))

    def test_pf_with_a_cnpj_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        msg = _mensagem_400(_criar_intermediario(client, cid, pessoa_tipo="pf", documento=CNPJ))
        assert "pessoa física exige CPF" in msg

    def test_invalid_contact_and_address_fields_are_refused_by_name(self, client, scoped):
        cid, _aid = _seed(scoped)
        assert "e-mail" in _mensagem_400(_criar_intermediario(client, cid, email="sem-arroba"))
        assert "UF" in _mensagem_400(_criar_intermediario(client, cid, endereco_uf="SPX"))
        assert "CEP" in _mensagem_400(_criar_intermediario(client, cid, endereco_cep="0131"))
        assert "representante" in _mensagem_400(
            _criar_intermediario(client, cid, representante_cpf="111.111.111-11")
        )

    def test_the_favorecido_must_belong_to_this_deal(self, client, scoped):
        estranho_id = str(uuid4())
        cid, _aid = _seed(scoped, favorecidos=[{
            "id": estranho_id, "org_id": ORG_ID, "atendimento_id": str(uuid4()),
            "nome": "De outro card", "cpf_cnpj": None, "banco": None,
            "agencia": None, "conta": None, "pix": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        r = _criar_intermediario(client, cid, favorecido_id=estranho_id)
        assert r.status_code == 404, r.text

    def test_the_commission_can_point_at_this_deals_favorecido(self, client, scoped):
        cid, _aid = _seed(scoped)
        fav = client.post(
            f"/api/clientes/{cid}/negociacao/favorecidos",
            json={"nome": "Parceira Imóveis Ltda"}, headers=_auth(),
        ).json()["favorecidos"][0]["id"]
        r = _criar_intermediario(client, cid, favorecido_id=fav)
        assert r.status_code == 201, r.text
        assert r.json()["intermediarios"][0]["favorecido_id"] == fav

    def test_patching_pessoa_tipo_against_the_stored_document_is_refused(self, client, scoped):
        cid, _aid = _seed(scoped)
        iid = _criar_intermediario(client, cid, documento=CPF).json()["intermediarios"][0]["id"]
        r = client.patch(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            json={"pessoa_tipo": "pj"}, headers=_auth(),
        )
        assert "pessoa jurídica exige CNPJ" in _mensagem_400(r)

    def test_patching_the_document_and_tipo_together_is_accepted(self, client, scoped):
        cid, _aid = _seed(scoped)
        iid = _criar_intermediario(client, cid, documento=CPF).json()["intermediarios"][0]["id"]
        r = client.patch(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            json={"pessoa_tipo": "pj", "documento": CNPJ}, headers=_auth(),
        )
        assert r.status_code == 200, r.text
        item = r.json()["intermediarios"][0]
        assert (item["pessoa_tipo"], item["documento"]) == ("pj", CNPJ_NU)

    def test_a_patch_that_leaves_qualification_alone_keeps_it(self, client, scoped):
        cid, _aid = _seed(scoped)
        iid = _criar_intermediario(client, cid, documento=CPF).json()["intermediarios"][0]["id"]
        r = client.patch(
            f"/api/clientes/{cid}/negociacao/intermediarios/{iid}",
            json={"creci": "12345-F"}, headers=_auth(),
        )
        assert r.status_code == 200, r.text
        item = r.json()["intermediarios"][0]
        assert (item["pessoa_tipo"], item["documento"], item["creci"]) == ("pf", CPF_NU, "12345-F")

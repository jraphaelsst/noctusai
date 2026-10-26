"""The swap scorer — does EACH owner get what they asked for?

The golden cases at the bottom are the pairs brokers KEPT in the legacy
Permutas funnel (social-wiring corpus, 2026-10-26), reduced to the fields the
scorer reads. The similarity engine scored them 29–50 or rejected them; they
are the ground truth this module was calibrated against, so a change that
loses one of them must be a deliberate decision, not a side effect.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.real_estate import matching
from noctusai_lib.domain.real_estate.permuta import (
    MODELO,
    SCORE_MINIMO_PERMUTA,
    avaliar_recebimento,
    emitir_permuta,
    emitir_permutas,
    lugar_atende,
    pontuar_permuta,
    tipo_atende,
    valor_atende,
)


def _ativo(id_: str, **over) -> dict:
    base = {
        "id": id_,
        "natureza": "imovel",
        "status": "ativo",
        "estado": "SP",
        "cidade": "Cotia",
        "bairro": None,
        "tipo_imovel": "Casa em Condomínio",
        "valor": 1_000_000.0,
        "interesses": [],
        "owner_id": None,
    }
    base.update(over)
    return base


def _quer(**over) -> dict:
    base = {"tipo": "imovel", "tipo_imovel": None, "cidade": None, "bairro": None,
            "zona": None, "valor_min": None, "valor_max": None, "observacoes": None}
    base.update(over)
    return base


class TestTetoSemPisoNoMotorDeSimilaridade:
    """🔴 The shared `matching._valor_na_faixa` ignored a ceiling with no floor.

    That is how people state value ("até 1,2 milhão") — 116 of 118 interests
    in the corpus — so every ceiling was dead and a R$14M house was offered to
    an owner who accepts at most R$1.65M.
    """

    def test_teto_sem_piso_e_respeitado(self):
        assert matching._valor_na_faixa(14_000_000, {"valor_max": 1_650_000}) is False

    def test_teto_sem_piso_com_tolerancia(self):
        assert matching._valor_na_faixa(1_900_000, {"valor_max": 1_650_000}) is True

    def test_piso_sem_teto_e_respeitado(self):
        assert matching._valor_na_faixa(100_000, {"valor_min": 500_000}) is False

    def test_sem_faixa_nao_restringe(self):
        assert matching._valor_na_faixa(9_000_000, {}) is True


class TestTipo:
    @pytest.mark.parametrize("desejado, oferecido, esperado", [
        ("Casa em condomínio", "Casa em Condomínio", True),   # Vista vs interest casing
        ("Casa", "Casa em Condomínio", True),                  # family head admits the variant
        ("Casa em condomínio", "Casa", False),                 # ...not the reverse
        ("Terreno", "Terreno de Rua", True),
        ("Apartamento", "Cobertura", True),                    # cobertura IS an apartment
        ("Apartamento", "Estúdio", True),
        ("Apartamento", "Casa em Condomínio", False),
        (None, "Casa", None),
        ("Casa", None, None),
    ])
    def test_tipo_atende(self, desejado, oferecido, esperado):
        assert tipo_atende(desejado, oferecido) is esperado


class TestValor:
    def test_dentro_do_teto(self):
        assert valor_atende({"valor_max": 1_000_000}, 900_000) == 2

    def test_na_tolerancia(self):
        assert valor_atende({"valor_max": 1_000_000}, 1_150_000) == 1

    def test_alem_da_tolerancia(self):
        assert valor_atende({"valor_max": 1_000_000}, 1_300_000) == 0

    def test_sem_faixa_e_desconhecido(self):
        assert valor_atende({}, 1_000_000) is None

    def test_sem_valor_ofertado_e_desconhecido(self):
        assert valor_atende({"valor_max": 1_000_000}, None) is None


class TestLugar:
    def test_bairro_nomeado_na_prosa(self):
        oferta = _ativo("o", bairro="São Paulo 2")
        assert lugar_atende(_quer(observacoes="Aceita Permuta São Paulo 2"), oferta) is True

    def test_cidade_nao_casa_com_condominio_numerado(self):
        # "São Paulo 2" is a condominium in Cotia; the city São Paulo must not hit it.
        oferta = _ativo("o", cidade="São Paulo", bairro="Chacara Klabin")
        assert lugar_atende(_quer(observacoes="Aceita Permuta São Paulo 2"), oferta) is None

    def test_regiao_dentro_do_nome_do_bairro(self):
        oferta = _ativo("o", bairro="Miolo Granja Viana - Km 23")
        assert lugar_atende(_quer(observacoes="Casa na Granja Viana"), oferta) is True

    def test_km_dentro_da_faixa(self):
        oferta = _ativo("o", bairro="Villa Vianna - Km 23")
        texto = "casa isolada em condomínio (Km 21 ao Km 30 Rap. Tavares)"
        assert lugar_atende(_quer(observacoes=texto), oferta) is True

    def test_km_fora_da_faixa_nao_confirma(self):
        oferta = _ativo("o", bairro="Moradas do Sol - Km 34")
        assert lugar_atende(_quer(observacoes="entre o Km 22 e o Km 26"), oferta) is None

    def test_macrozona_nao_identifica_lugar(self):
        # zona='Oeste' is on 80% of interests — it identifies nothing.
        assert lugar_atende(_quer(zona="Oeste"), _ativo("o", bairro="Granja Viana")) is None

    def test_lugar_estruturado_que_nao_casa_e_falso(self):
        oferta = _ativo("o", cidade="Cotia")
        assert lugar_atende(_quer(cidade="Barueri"), oferta) is False

    def test_palavra_generica_nao_casa(self):
        oferta = _ativo("o", bairro="Jardim")
        assert lugar_atende(_quer(observacoes="quero casa com jardim"), oferta) is None


class TestRecebimento:
    def test_dono_aberto_aceita_com_credito_neutro(self):
        r = avaliar_recebimento(_ativo("a"), _ativo("b"))
        assert r["aceita"] and r["aberto"]
        assert r["pontos"] < 20

    def test_tipo_declarado_divergente_rejeita(self):
        a = _ativo("a", interesses=[_quer(tipo_imovel="Apartamento")])
        assert avaliar_recebimento(a, _ativo("b", tipo_imovel="Casa"))["aceita"] is False

    def test_valor_alem_do_teto_rejeita(self):
        a = _ativo("a", interesses=[_quer(valor_max=1_650_000)])
        assert avaliar_recebimento(a, _ativo("b", valor=14_000_000))["aceita"] is False

    def test_melhor_interesse_vence(self):
        a = _ativo("a", interesses=[
            _quer(tipo_imovel="Apartamento"),
            _quer(tipo_imovel="Casa em condomínio", valor_max=1_200_000),
        ])
        r = avaliar_recebimento(a, _ativo("b", valor=1_000_000))
        assert r["aceita"] and r["tipo"] is True and r["valor"] == 2

    def test_so_interesse_em_veiculo_nao_aceita_imovel(self):
        a = _ativo("a", interesses=[{"tipo": "automovel", "marca": "Volvo"}])
        assert avaliar_recebimento(a, _ativo("b"))["aceita"] is False

    def test_subida_grande_sem_teto_perde_credito_mas_nao_o_par(self):
        """🔴 SOFT, not a gate — brokers KEPT trade-ups of 3–4× (see golden)."""
        a = _ativo("a", valor=1_000_000, interesses=[_quer(tipo_imovel="Casa em condomínio")])
        perto = avaliar_recebimento(a, _ativo("b", valor=1_500_000))
        longe = avaliar_recebimento(a, _ativo("b", valor=4_000_000))
        assert longe["aceita"] and longe["subida_sem_teto"]
        assert longe["pontos"] < perto["pontos"]


class TestPar:
    def test_simetrico(self):
        a = _ativo("a", valor=3_300_000, interesses=[_quer(valor_max=1_650_000)])
        b = _ativo("b", tipo_imovel="Apartamento", valor=1_080_000,
                   interesses=[_quer(tipo_imovel="Casa em condomínio")])
        assert pontuar_permuta(a, b)["score"] == pontuar_permuta(b, a)["score"]

    def test_mesmo_dono_nao_casa(self):
        a, b = _ativo("a", owner_id="tel:1"), _ativo("b", owner_id="tel:1")
        assert pontuar_permuta(a, b) is None

    def test_dono_desconhecido_nao_exclui(self):
        assert pontuar_permuta(_ativo("a"), _ativo("b")) is not None

    def test_estados_diferentes_nao_casam(self):
        assert pontuar_permuta(_ativo("a"), _ativo("b", estado="RJ")) is None

    def test_dois_que_so_descem_de_patamar_nao_casam(self):
        """Both owners trade DOWN: neither ceiling admits the other's value."""
        a = _ativo("a", valor=2_000_000, interesses=[_quer(valor_max=1_000_000)])
        b = _ativo("b", valor=2_000_000, interesses=[_quer(valor_max=1_000_000)])
        assert pontuar_permuta(a, b) is None

    def test_dois_abertos_ficam_abaixo_do_piso(self):
        a, b = _ativo("a"), _ativo("b")
        assert pontuar_permuta(a, b)["score"] < SCORE_MINIMO_PERMUTA

    def test_troca_cruzada_de_tipos_casa(self):
        """House-owner wants an apartment; apartment-owner wants a house."""
        a = _ativo("a", valor=1_980_000, interesses=[_quer(tipo_imovel="Apartamento")])
        b = _ativo("b", tipo_imovel="Apartamento", valor=1_200_000,
                   interesses=[_quer(tipo_imovel="Casa em condomínio")])
        r = pontuar_permuta(a, b)
        assert r["detalhes"]["origem_recebe"]["tipo"] is True
        assert r["detalhes"]["destino_recebe"]["tipo"] is True

    def test_saida_carrega_modelo_e_justificativa(self):
        a = _ativo("a", interesses=[_quer(valor_max=1_200_000)])
        r = pontuar_permuta(a, _ativo("b"))
        assert r["detalhes"]["modelo"] == MODELO
        assert "Origem recebe" in r["justificativa"]
        assert r["detalhes"]["semantica_disponivel"] is False

    def test_semantica_entra_quando_os_quatro_vetores_existem(self):
        v = [1.0, 0.0]
        a = _ativo("a", embedding=v, embedding_interesses=v)
        b = _ativo("b", embedding=v, embedding_interesses=v)
        regras = pontuar_permuta(_ativo("a"), _ativo("b"))["score"]
        r = pontuar_permuta(a, b)
        assert r["detalhes"]["semantica_disponivel"] is True
        assert r["score"] == round(0.6 * regras + 0.4 * 100, 1)


class TestEmissao:
    def test_inativo_nao_emite(self):
        a = _ativo("a", interesses=[_quer(valor_max=1_200_000)])
        assert emitir_permuta(a, _ativo("b", status="inativo"), 0) is None

    def test_orientacao_e_do_chamador(self):
        a = _ativo("a", interesses=[_quer(valor_max=1_200_000)])
        m = emitir_permuta(a, _ativo("b"), 0)
        assert (m["ativo_origem_id"], m["ativo_destino_id"]) == ("a", "b")

    def test_lista_ordenada_pelo_score(self):
        a = _ativo("a", interesses=[_quer(valor_max=1_200_000)])
        forte = _ativo("b", interesses=[_quer(tipo_imovel="Casa em condomínio", valor_max=1_200_000)])
        fraco = _ativo("c")
        saida = emitir_permutas([(a, fraco), (a, forte)], 0)
        assert [m["ativo_destino_id"] for m in saida] == ["b", "c"]


# ── Golden: the pairs brokers KEPT in the legacy funnel ─────────────────────

_KEPT = [
    pytest.param(
        _ativo("a", bairro="Nova Vianna - Km 26", valor=960_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", zona="Oeste",
                                 valor_max=1_000_000, observacoes="Casa de 3 dormitórios")]),
        _ativo("b", bairro="Villaggio Viana", valor=980_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", zona="Oeste", valor_max=1_200_000,
                                 observacoes="Estuda permuta por casa isolada em condomínio na "
                                             "Granja Viana (Km 21 ao Km 30 Rap. Tavares)")]),
        70, id="casa-por-casa-mesmo-patamar",
    ),
    pytest.param(
        _ativo("a", bairro="São Paulo 2", valor=3_300_000,
               interesses=[_quer(zona="Oeste", valor_max=1_650_000,
                                 observacoes="Aceito imóvel de menor valor até 50% no máximo")]),
        _ativo("b", tipo_imovel="Apartamento", cidade="São Paulo", bairro="Chacara Klabin",
               valor=1_080_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", zona="Oeste",
                                 observacoes="Aceita Permuta São Paulo 2")]),
        50, id="casa-3.3M-por-apto-1.08M-que-pede-o-condominio",
    ),
    pytest.param(
        _ativo("a", cidade="Carapicuíba", bairro="Pousada dos Bandeirantes - Km 23", valor=1_980_000,
               interesses=[_quer(tipo_imovel="Apartamento", zona="Oeste",
                                 observacoes="Estudo permuta por apartamento Zona Oeste SP.")]),
        _ativo("b", tipo_imovel="Apartamento", cidade="Barueri", bairro="Tamboré", valor=1_200_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", zona="Oeste",
                                 observacoes="Casa na Aldeia da Granja.")]),
        45, id="casa-quer-apto-apto-quer-casa",
    ),
    pytest.param(
        _ativo("a", natureza="permuta_imovel", tipo_imovel="Apartamento", cidade="Osasco",
               bairro="Vila Osasco", valor=360_000,
               interesses=[_quer(observacoes="Estuda permuta por imóvel, sem especificação de região.")]),
        _ativo("b", bairro="Vila da Mata - Km 23", valor=1_480_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", zona="Oeste", valor_max=740_000),
                           _quer(tipo_imovel="Apartamento", zona="Oeste", valor_max=740_000)]),
        SCORE_MINIMO_PERMUTA, id="apto-360k-de-entrada-em-casa-1.48M",
    ),
]


@pytest.mark.parametrize("a, b, piso", _KEPT)
def test_par_mantido_pelos_corretores_e_emitido(a, b, piso):
    r = pontuar_permuta(a, b)
    assert r is not None, "um par que os corretores mantiveram não pode cair num gate"
    assert r["score"] >= piso
    assert emitir_permuta(a, b) is not None


def test_par_que_estoura_o_teto_dos_dois_lados_nao_existe():
    """The similarity engine's #6 live suggestion: R$3.3M ↔ R$14M, scored 53."""
    a = _ativo("a", bairro="São Paulo 2", valor=3_300_000,
               interesses=[_quer(valor_max=1_650_000)])
    b = _ativo("b", bairro="São Paulo 2", valor=14_000_000,
               interesses=[_quer(tipo_imovel="Casa em condomínio", valor_max=2_000_000)])
    assert pontuar_permuta(a, b) is None

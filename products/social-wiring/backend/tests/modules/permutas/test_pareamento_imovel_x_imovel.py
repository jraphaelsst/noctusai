"""The pairing shape erp does not have, and that this business runs on.

In the legacy corpus **77 of 82 matches are imóvel × imóvel** — two catalog
listings whose owners each accept a swap, trading with each other. Only 5 pair
a listing against a separately-registered permuta, which is the ONLY shape erp
models. Scoring just erp's shape would silently return 6% of the answer: no
error, no empty result, simply far fewer matches than exist.
"""
from __future__ import annotations

from noctusai_lib.domain.real_estate.matching import gerar_matches_para_imovel

from app.modules.permutas import adapter


def _listagem(id_: str, **over) -> dict:
    """A catalog listing whose owner accepts a swap, already projected."""
    base = {
        "id": id_,
        "natureza": "imovel",
        "aceita_permutas": True,
        "status": "ativo",
        "tipo_imovel": "Casa em Condomínio",
        "cidade": "Cotia",
        "bairro": "Granja Viana",
        "estado": "SP",
        "valor": 1_200_000.0,
        "quartos": 3,
        "vagas": 2,
        "area_total": 300.0,
        "interesses": [],
        "owner_id": None,
    }
    base.update(over)
    return base


class TestComoOferta:
    def test_relabela_natureza_sem_inventar_dados(self):
        origem = _listagem("a")
        oferta = adapter.como_oferta(origem)
        assert oferta["natureza"] == "permuta_imovel"
        # Everything else is the same object's data — nothing fabricated.
        assert {k: v for k, v in oferta.items() if k != "natureza"} == {
            k: v for k, v in origem.items() if k != "natureza"
        }

    def test_nao_muta_o_original(self):
        origem = _listagem("a")
        adapter.como_oferta(origem)
        assert origem["natureza"] == "imovel"


class TestSemORelabelONadaCasa:
    """🔴 The reason `como_oferta` exists rather than passing the row through.

    `calcular_compatibilidade_specs` and `passa_filtros_minimos` both branch on
    the RIGHT-hand side's `natureza`. With `imovel` there, specs falls through
    every branch and scores 0, and the region gate never applies — so the pair
    fails the two-of-three rule on a technicality about labelling.
    """

    def test_duas_listagens_cruas_nao_casam(self):
        a, b = _listagem("a"), _listagem("b", valor=1_150_000.0)
        assert gerar_matches_para_imovel(a, [b]) == []

    def test_as_mesmas_duas_casam_quando_a_segunda_e_oferta(self):
        a, b = _listagem("a"), _listagem("b", valor=1_150_000.0)
        matches = gerar_matches_para_imovel(a, [adapter.como_oferta(b)])
        assert matches, "duas listagens compatíveis devem casar entre si"
        assert matches[0]["ativo_origem_id"] == "a"
        assert matches[0]["ativo_destino_id"] == "b"
        assert matches[0]["detalhes"]["compatibilidade_specs"] > 0


class TestScoreNaoESimetrico:
    """Why the dedupe must pick ONE orientation rather than trusting the pair.

    `calcular_qualidade_anuncio` is scored on the ORIGEM side only, so A→B and
    B→A are genuinely different numbers. Letting both rows reach the upsert
    means the second silently overwrites the first with the reverse score.
    """

    def test_a_para_b_difere_de_b_para_a(self):
        rico = _listagem(
            "rico",
            titulo_anuncio="Casa com vista",
            descricao_seo="Descrição completa",
            fotos=["1", "2", "3"],
            tour_virtual_url="https://tour",
            condominio_nome="Passargada",
        )
        pobre = _listagem("pobre", valor=1_150_000.0)

        ab = gerar_matches_para_imovel(rico, [adapter.como_oferta(pobre)])
        ba = gerar_matches_para_imovel(pobre, [adapter.como_oferta(rico)])

        assert ab and ba
        assert ab[0]["score"] != ba[0]["score"], (
            "a qualidade do anúncio é pontuada só na origem, então as duas "
            "direções não podem ter o mesmo score — é por isso que o dedupe "
            "precisa escolher uma orientação"
        )

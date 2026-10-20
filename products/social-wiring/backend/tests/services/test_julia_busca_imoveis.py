"""Julia v2 listing search (`julia_busca_imoveis`): hard filters, the price band, every widening step, ranking.

Pure unit tests on plain rows -- no database, no HTTP."""
from __future__ import annotations

import pytest

from app.services import julia_busca_imoveis as b


def row(codigo, **over):
    r = {
        "codigo": codigo, "categoria": "Casa", "bairro": "Granja Viana", "cidade": "Cotia", "uf": "SP",
        "empreendimento": None, "valor_venda": 1_000_000, "valor_locacao": None, "dormitorios": 3, "vagas": 2,
        "area_total": 300, "caracteristicas": [],
    }
    r.update(over)
    return r


def q(**over):
    return b.Consulta(**{"operacao": "compra", **over})


def codes(res):
    return [r["codigo"] for r in res.linhas]


class TestHardFilters:
    def test_tipo_quartos_vagas_regiao_are_hard(self):
        rows = [row("OK"), row("APT", categoria="Apartamento"), row("Q2", dormitorios=2), row("V1", vagas=1),
                row("ALPHA", bairro="Alphaville")]
        res = b.buscar(rows, q(tipo="casa", quartos_min=3, vagas_min=2, regioes=("granja viana",)), limite=1)
        assert codes(res) == ["OK"] and res.relaxado == []

    def test_a_listing_missing_a_field_a_filter_needs_does_not_pass(self):
        rows = [row("NOVAGAS", vagas=None), row("NOPRECO", valor_venda=None), row("NOQ", dormitorios=None), row("OK")]
        assert not b.passa(rows[0], q(vagas_min=1), b.Folgas()) and b.passa(rows[3], q(vagas_min=1), b.Folgas())
        assert not b.passa(rows[1], q(preco_max=2_000_000), b.Folgas()) and b.passa(rows[3], q(preco_max=2_000_000), b.Folgas())
        assert not b.passa(rows[2], q(quartos_min=1), b.Folgas()) and b.passa(rows[3], q(quartos_min=1), b.Folgas())

    def test_essential_items_are_hard_with_accent_and_case_folding_and_pets_synonyms(self):
        rows = [row("PISC", caracteristicas=["Piscina", "Churrasqueira"]), row("PET", caracteristicas=["Aceita Pets"]),
                row("NADA"), row("ANIM", caracteristicas=["Permitido animais"])]
        assert codes(b.buscar(rows, q(essenciais=("piscina",)), limite=3)) == ["PISC"]
        assert sorted(codes(b.buscar(rows, q(essenciais=("pets",)), limite=3))) == ["ANIM", "PET"]
        assert codes(b.buscar([row("X", caracteristicas=["Área gourmet"])], q(essenciais=("area gourmet",)), limite=1)) == ["X"]

    def test_essential_items_are_never_relaxed(self):
        res = b.buscar([row("NADA")], q(essenciais=("piscina",), desejaveis=("sauna",)), limite=3)
        assert res.linhas == []

    def test_excluir_codigos_is_case_insensitive_and_never_returns_an_offered_code(self):
        res = b.buscar([row("A1"), row("B2"), row("C3")], q(), limite=3, excluir=["a1", " C3 "])
        assert codes(res) == ["B2"]

    def test_limite_caps_and_restantes_counts_the_rest(self):
        res = b.buscar([row(f"M{i}") for i in range(7)], q(), limite=3)
        assert len(res.linhas) == 3 and res.restantes == 4


class TestPriceBand:
    @pytest.mark.parametrize("valor,entra", [(849_999, False), (850_000, True), (1_000_000, True), (1_100_000, True), (1_100_001, False)])
    def test_the_band_is_minus_15_plus_10_percent_of_the_range(self, valor, entra):
        # `passa` is the strict filter (no widening): the band edges are exact
        assert b.passa(row("X", valor_venda=valor), q(preco_min=1_000_000, preco_max=1_000_000), b.Folgas()) is entra

    def test_aluguel_reads_the_rent_price(self):
        res = b.buscar([row("R", valor_venda=None, valor_locacao=4_500)], q(operacao="aluguel", preco_max=4_500), limite=1)
        assert codes(res) == ["R"]


class TestWideningOrder:
    def test_1_desejaveis_first(self):
        rows = [row("COM", caracteristicas=["piscina"]), row("SEM")]
        res = b.buscar(rows, q(desejaveis=("piscina",)), limite=2)
        assert res.relaxado == ["desejaveis"] and sorted(codes(res)) == ["COM", "SEM"]
        assert codes(res)[0] == "COM"  # the nice-to-have still ranks

    def test_enough_strict_results_means_no_widening(self):
        rows = [row(f"C{i}", caracteristicas=["piscina"]) for i in range(3)] + [row("SEM")]
        res = b.buscar(rows, q(desejaveis=("piscina",)), limite=3)
        assert res.relaxado == [] and "SEM" not in codes(res)

    def test_2_regiao_adjacente_only_when_the_org_configured_it(self):
        rows = [row("DENTRO"), row("VIZ", bairro="Vila Vizinha")]
        sem = b.buscar(rows, q(regioes=("Granja Viana",)), limite=2)
        assert codes(sem) == ["DENTRO"] and sem.relaxado == []  # no adjacency configured => nothing to widen
        com = b.buscar(rows, q(regioes=("Granja Viana",), adjacentes={"granja viana": ("vila vizinha",)}), limite=2)
        assert codes(com) == ["DENTRO", "VIZ"] and com.relaxado == ["regiao_adjacente"]

    def test_3_preco_goes_to_plus_20_percent_of_the_ceiling(self):
        rows = [row("DENTRO", valor_venda=1_000_000), row("PERTO", valor_venda=1_150_000), row("LONGE", valor_venda=1_250_000)]
        res = b.buscar(rows, q(preco_max=1_000_000), limite=3)
        assert res.relaxado == ["preco"] and sorted(codes(res)) == ["DENTRO", "PERTO"]

    def test_4_tipologia_drops_tipo_and_lowers_quartos_by_one(self):
        rows = [row("CASA3"), row("APT3", categoria="Apartamento"), row("CASA2", dormitorios=2), row("APT1", categoria="Apartamento", dormitorios=1)]
        res = b.buscar(rows, q(tipo="casa", quartos_min=3), limite=4)
        assert res.relaxado == ["tipologia"] and sorted(codes(res)) == ["APT3", "CASA2", "CASA3"]

    def test_axes_relax_one_at_a_time_cumulatively_in_the_fixed_order(self):
        # Needs all four: nice-to-have, adjacent region, price and typology.
        alvo = row("ALVO", categoria="Apartamento", bairro="Vila Vizinha", valor_venda=1_150_000, dormitorios=2)
        res = b.buscar([alvo], q(tipo="casa", quartos_min=3, preco_max=1_000_000, regioes=("Granja Viana",),
                                 desejaveis=("piscina",), adjacentes={"granja viana": ("vila vizinha",)}), limite=1)
        assert codes(res) == ["ALVO"] and res.relaxado == ["desejaveis", "regiao_adjacente", "preco", "tipologia"]

    def test_stops_at_the_first_axis_that_fills_the_lote(self):
        rows = [row("A"), row("B", caracteristicas=[]), row("CARO", valor_venda=1_150_000)]
        res = b.buscar(rows, q(preco_max=1_000_000, desejaveis=("piscina",)), limite=2)
        assert res.relaxado == ["desejaveis"] and "CARO" not in codes(res)

    def test_an_axis_the_result_did_not_need_is_not_reported(self):
        res = b.buscar([row("A")], q(preco_max=1_000_000, tipo="casa"), limite=3)
        assert res.relaxado == []
        # price is needed for CARO; tipologia is tried too (limite not reached) but adds nothing => not reported
        res = b.buscar([row("A"), row("CARO", valor_venda=1_150_000)], q(preco_max=1_000_000, tipo="casa"), limite=3)
        assert res.relaxado == ["preco"]

    def test_nothing_to_relax_returns_what_passes(self):
        res = b.buscar([], q(), limite=3)
        assert res.linhas == [] and res.relaxado == [] and res.restantes == 0


class TestRanking:
    def test_same_condominio_then_same_region_then_adjacent(self):
        rows = [row("ADJ", bairro="Vila Vizinha"), row("REG"), row("COND", empreendimento="Cond Alfa")]
        res = b.buscar(rows, q(regioes=("Granja Viana",), condominio="Cond Alfa", adjacentes={"granja viana": ("vila vizinha",)}), limite=3)
        assert codes(res) == ["COND", "REG", "ADJ"]

    def test_more_matched_nice_to_haves_rank_first_within_a_tier(self):
        rows = [row("UM", caracteristicas=["piscina"]), row("DOIS", caracteristicas=["piscina", "sauna"]), row("ZERO")]
        res = b.buscar(rows, q(desejaveis=("piscina", "sauna")), limite=3)
        assert codes(res) == ["DOIS", "UM", "ZERO"]

    def test_the_seed_matcher_breaks_ties_closer_price_first(self):
        rows = [row("A_LONGE", valor_venda=1_090_000), row("PERTO", valor_venda=1_000_000)]
        res = b.buscar(rows, q(preco_min=1_000_000, preco_max=1_000_000), limite=2)
        assert codes(res)[0] == "PERTO"


class TestCasaTipo:
    @pytest.mark.parametrize("tipo,categoria,esperado", [
        ("casa_condominio", "Casa em Condomínio", True), ("casa_condominio", "Casa", False),
        ("casa", "Casa em Condomínio", True), ("apartamento", "Cobertura", True), ("terreno", "Lote", True),
        ("comercial", "Galpão", True), ("casa", "Apartamento", False),
        ("casa", "Casa comercial", False), ("casa_condominio", "Casa comercial", False),
        ("comercial", "Casa comercial", True), ("terreno", "Área", True), ("terreno", "Terreno em Condomínio", True),
        ("comercial", "Salas/Conjuntos", True), ("apartamento", "Loft", True), ("casa", "Sobrado", True),
        ("Casa em Condominio", "Casa em Condomínio", True),  # a free value from a campaign listing: folded substring
        (None, "Qualquer", True),
    ])
    def test_mapping(self, tipo, categoria, esperado):
        assert b.casa_tipo(tipo, categoria) is esperado

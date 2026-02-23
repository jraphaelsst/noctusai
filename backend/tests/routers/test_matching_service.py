"""
Tests for the matching scoring algorithm.
Covers region, price, specs, interests, quality, and edge cases.
"""
import pytest
from app.services.matching import (
    calcular_compatibilidade_regiao,
    calcular_compatibilidade_preco,
    calcular_compatibilidade_specs,
    calcular_alinhamento_interesses,
    calcular_qualidade_anuncio,
    calcular_score_total,
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
)


# ========== REGION SCORING ==========
class TestCompatibilidadeRegiao:
    def test_exact_city_state_bairro_match(self):
        imovel = {"estado": "SP", "cidade": "São Paulo", "bairro": "Moema"}
        permuta = {"estado": "SP", "cidade": "São Paulo", "bairro": "Moema"}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score >= 25  # estado + cidade + bairro

    def test_same_state_different_city(self):
        imovel = {"estado": "SP", "cidade": "Campinas"}
        permuta = {"estado": "SP", "cidade": "Sorocaba"}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score == 5  # only estado match

    def test_no_location_data(self):
        score = calcular_compatibilidade_regiao({}, {})
        assert score == 0

    def test_regiao_preferida_match(self):
        imovel = {"cidade": "Campinas", "estado": "SP"}
        permuta = {"regiao_preferida": ["Campinas", "Jundiaí"]}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score >= 5

    def test_regiao_preferida_no_match(self):
        imovel = {"cidade": "Manaus", "estado": "AM"}
        permuta = {"regiao_preferida": ["São Paulo", "Campinas"]}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score == 0

    def test_zona_match(self):
        imovel = {"zona": "Zona Sul"}
        permuta = {"zona": "Zona Sul"}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score >= 5

    def test_case_insensitive_match(self):
        imovel = {"cidade": "são paulo", "estado": "sp"}
        permuta = {"cidade": "São Paulo", "estado": "SP"}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score >= 15

    def test_partial_data_imovel_only(self):
        imovel = {"cidade": "São Paulo", "estado": "SP", "bairro": "Moema"}
        permuta = {}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score == 0

    def test_max_score_capped_at_30(self):
        imovel = {"estado": "SP", "cidade": "São Paulo", "bairro": "Moema", "zona": "Zona Sul"}
        permuta = {"estado": "SP", "cidade": "São Paulo", "bairro": "Moema", "zona": "Zona Sul",
                   "regiao_preferida": ["São Paulo"]}
        score = calcular_compatibilidade_regiao(imovel, permuta)
        assert score <= 30


# ========== PRICE SCORING ==========
class TestCompatibilidadePreco:
    def test_within_price_range(self):
        imovel = {"valor": 500000}
        permuta = {"faixa_preco_min": 400000, "faixa_preco_max": 600000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score >= 15

    def test_below_range_close(self):
        imovel = {"valor": 350000}
        permuta = {"faixa_preco_min": 400000, "faixa_preco_max": 600000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score >= 5

    def test_above_range_far(self):
        imovel = {"valor": 1000000}
        permuta = {"faixa_preco_min": 400000, "faixa_preco_max": 600000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score < 15

    def test_zero_valor(self):
        imovel = {"valor": 0}
        permuta = {"faixa_preco_min": 100000, "faixa_preco_max": 200000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score == 0

    def test_none_valor(self):
        imovel = {"valor": None}
        permuta = {"faixa_preco_min": 100000, "faixa_preco_max": 200000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score == 0

    def test_exact_value_match(self):
        imovel = {"valor": 500000}
        permuta = {"valor": 500000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score >= 10

    def test_accepts_complement_bonus(self):
        imovel = {"valor": 500000}
        permuta = {"valor": 400000, "aceita_completar_diferenca": True}
        score_with = calcular_compatibilidade_preco(imovel, permuta)

        permuta2 = {"valor": 400000, "aceita_completar_diferenca": False}
        score_without = calcular_compatibilidade_preco(imovel, permuta2)
        assert score_with > score_without

    def test_max_score_capped_at_25(self):
        imovel = {"valor": 500000}
        permuta = {"valor": 500000, "faixa_preco_min": 490000, "faixa_preco_max": 510000,
                   "aceita_completar_diferenca": True}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score <= 25

    def test_very_large_values(self):
        imovel = {"valor": 50_000_000}
        permuta = {"valor": 49_000_000, "faixa_preco_min": 45_000_000, "faixa_preco_max": 55_000_000}
        score = calcular_compatibilidade_preco(imovel, permuta)
        assert score > 0


# ========== SPECS SCORING ==========
class TestCompatibilidadeSpecs:
    def test_imovel_type_match(self):
        imovel = {"tipo_imovel": "apartamento"}
        permuta = {"natureza": "permuta_imovel", "tipo_imovel": "apartamento"}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score >= 5

    def test_quartos_sufficient(self):
        imovel = {"quartos": 3}
        permuta = {"natureza": "permuta_imovel", "quartos": 2}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score >= 5

    def test_quartos_insufficient(self):
        imovel = {"quartos": 1}
        permuta = {"natureza": "permuta_imovel", "quartos_min": 3}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score == 0  # quartos < quartos_min

    def test_automovel_marca_match(self):
        imovel = {"interesses": [{"tipo": "automovel", "marca": "Toyota", "valor_min": 50000, "valor_max": 100000}]}
        permuta = {"natureza": "permuta_automovel", "marca": "Toyota", "valor": 75000}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score >= 10

    def test_automovel_no_interests(self):
        imovel = {"interesses": []}
        permuta = {"natureza": "permuta_automovel", "marca": "Toyota", "valor": 75000}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score == 0

    def test_empty_specs(self):
        score = calcular_compatibilidade_specs({}, {"natureza": "permuta_imovel"})
        assert score == 0

    def test_max_score_capped_at_20(self):
        imovel = {"tipo_imovel": "casa", "quartos": 5, "vagas": 3, "area_total": 200}
        permuta = {"natureza": "permuta_imovel", "tipo_imovel": "casa",
                   "quartos_min": 2, "vagas_min": 1, "metragem_min": 100, "metragem_max": 300}
        score = calcular_compatibilidade_specs(imovel, permuta)
        assert score <= 20


# ========== INTEREST ALIGNMENT ==========
class TestAlinhamentoInteresses:
    def test_imovel_interest_matches_permuta_imovel(self):
        imovel = {"interesses": [{"tipo": "imovel", "tipo_imovel": "casa", "cidade": "Campinas"}]}
        permuta = {"natureza": "permuta_imovel", "tipo_imovel": "casa", "cidade": "Campinas"}
        score = calcular_alinhamento_interesses(imovel, permuta)
        assert score >= 8

    def test_automovel_interest_matches_permuta_automovel(self):
        imovel = {"interesses": [{"tipo": "automovel"}]}
        permuta = {"natureza": "permuta_automovel"}
        score = calcular_alinhamento_interesses(imovel, permuta)
        assert score >= 8

    def test_no_interests(self):
        imovel = {"interesses": []}
        permuta = {"natureza": "permuta_imovel"}
        assert calcular_alinhamento_interesses(imovel, permuta) == 0

    def test_none_interests(self):
        imovel = {"interesses": None}
        permuta = {"natureza": "permuta_imovel"}
        assert calcular_alinhamento_interesses(imovel, permuta) == 0

    def test_interest_type_mismatch(self):
        imovel = {"interesses": [{"tipo": "automovel"}]}
        permuta = {"natureza": "permuta_imovel"}
        score = calcular_alinhamento_interesses(imovel, permuta)
        assert score == 0

    def test_max_score_capped_at_15(self):
        imovel = {"interesses": [{"tipo": "imovel", "tipo_imovel": "casa", "cidade": "São Paulo"}]}
        permuta = {"natureza": "permuta_imovel", "tipo_imovel": "casa", "cidade": "São Paulo"}
        score = calcular_alinhamento_interesses(imovel, permuta)
        assert score <= 15


# ========== QUALITY SCORING ==========
class TestQualidadeAnuncio:
    def test_complete_listing(self):
        imovel = {
            "titulo_anuncio": "Lindo apartamento",
            "descricao_seo": "Descrição detalhada",
            "fotos": ["a.jpg", "b.jpg", "c.jpg"],
            "tour_virtual_url": "http://tour.com",
            "pontos_de_interesse": ["escola"],
            "condominio_nome": "Edifício Aurora",
        }
        score = calcular_qualidade_anuncio(imovel)
        assert score == 10

    def test_empty_listing(self):
        assert calcular_qualidade_anuncio({}) == 0

    def test_only_title(self):
        score = calcular_qualidade_anuncio({"titulo_anuncio": "Test"})
        assert score == 2

    def test_few_photos(self):
        score = calcular_qualidade_anuncio({"fotos": ["a.jpg"]})
        assert score == 1

    def test_many_photos(self):
        score = calcular_qualidade_anuncio({"fotos": ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]})
        assert score == 3


# ========== TOTAL SCORE ==========
class TestScoreTotal:
    def test_perfect_match(self):
        imovel = {
            "estado": "SP", "cidade": "São Paulo", "bairro": "Moema", "zona": "Zona Sul",
            "valor": 500000, "tipo_imovel": "apartamento", "quartos": 3, "vagas": 2,
            "area_total": 100,
            "titulo_anuncio": "Lindo", "descricao_seo": "Desc", "fotos": ["a", "b", "c"],
            "condominio_nome": "Aurora",
            "interesses": [{"tipo": "imovel", "tipo_imovel": "apartamento", "cidade": "São Paulo"}],
        }
        permuta = {
            "natureza": "permuta_imovel",
            "estado": "SP", "cidade": "São Paulo", "bairro": "Moema", "zona": "Zona Sul",
            "valor": 500000, "faixa_preco_min": 450000, "faixa_preco_max": 550000,
            "tipo_imovel": "apartamento", "quartos_min": 2, "vagas_min": 1,
            "metragem_min": 80, "metragem_max": 150,
            "aceita_completar_diferenca": True,
        }
        result = calcular_score_total(imovel, permuta)
        assert result["score"] >= 70
        assert "detalhes" in result
        assert "justificativa" in result

    def test_no_match_at_all(self):
        result = calcular_score_total({}, {"natureza": "permuta_imovel"})
        assert result["score"] < 20

    def test_detalhes_structure(self):
        result = calcular_score_total({"valor": 100000}, {"natureza": "permuta_imovel", "valor": 100000})
        assert "compatibilidade_regiao" in result["detalhes"]
        assert "compatibilidade_preco" in result["detalhes"]
        assert "compatibilidade_specs" in result["detalhes"]
        assert "qualidade_anuncio" in result["detalhes"]
        assert "gap_valor" in result["detalhes"]


# ========== MATCH GENERATION ==========
class TestGerarMatches:
    def test_generates_matches(self):
        imovel = {
            "id": "imovel-1", "owner_id": "user-a", "valor": 500000, "aceita_permutas": True,
            "status": "ativo", "cidade": "São Paulo", "estado": "SP",
            "interesses": [{"tipo": "imovel"}],
        }
        permutas = [
            {"id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel",
             "valor": 500000, "cidade": "São Paulo", "estado": "SP", "status": "ativo"},
        ]
        matches = gerar_matches_para_imovel(imovel, permutas, score_minimo=1)
        assert len(matches) >= 1
        assert matches[0]["ativo_origem_id"] == "imovel-1"
        assert matches[0]["ativo_destino_id"] == "perm-1"

    def test_same_owner_excluded(self):
        imovel = {"id": "imovel-1", "owner_id": "user-a", "valor": 500000}
        permutas = [
            {"id": "perm-1", "owner_id": "user-a", "natureza": "permuta_imovel",
             "valor": 500000, "status": "ativo"},
        ]
        matches = gerar_matches_para_imovel(imovel, permutas, score_minimo=0)
        assert len(matches) == 0

    def test_inactive_permuta_excluded(self):
        imovel = {"id": "imovel-1", "owner_id": "user-a", "valor": 500000}
        permutas = [
            {"id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel",
             "valor": 500000, "status": "inativo"},
        ]
        matches = gerar_matches_para_imovel(imovel, permutas, score_minimo=0)
        assert len(matches) == 0

    def test_below_minimum_score_filtered(self):
        imovel = {"id": "imovel-1", "owner_id": "user-a", "valor": 500000}
        permutas = [
            {"id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel",
             "valor": 100, "status": "ativo"},
        ]
        matches = gerar_matches_para_imovel(imovel, permutas, score_minimo=90)
        assert len(matches) == 0

    def test_sorted_by_score_desc(self):
        imovel = {
            "id": "imovel-1", "owner_id": "user-a", "valor": 500000,
            "cidade": "São Paulo", "estado": "SP", "interesses": [{"tipo": "imovel"}],
        }
        permutas = [
            {"id": "perm-bad", "owner_id": "user-b", "natureza": "permuta_imovel",
             "valor": 100, "status": "ativo"},
            {"id": "perm-good", "owner_id": "user-c", "natureza": "permuta_imovel",
             "valor": 500000, "cidade": "São Paulo", "estado": "SP", "status": "ativo"},
        ]
        matches = gerar_matches_para_imovel(imovel, permutas, score_minimo=0)
        if len(matches) >= 2:
            assert matches[0]["score"] >= matches[1]["score"]

    def test_gerar_para_permuta(self):
        permuta = {
            "id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel",
            "valor": 500000, "cidade": "São Paulo", "estado": "SP", "status": "ativo",
        }
        imoveis = [
            {"id": "imovel-1", "owner_id": "user-a", "valor": 500000,
             "aceita_permutas": True, "cidade": "São Paulo", "estado": "SP", "status": "ativo",
             "interesses": [{"tipo": "imovel"}]},
        ]
        matches = gerar_matches_para_permuta(permuta, imoveis, score_minimo=1)
        assert len(matches) >= 1

    def test_gerar_para_permuta_excludes_non_aceita(self):
        permuta = {"id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel",
                   "valor": 500000, "status": "ativo"}
        imoveis = [
            {"id": "imovel-1", "owner_id": "user-a", "valor": 500000,
             "aceita_permutas": False, "status": "ativo"},
        ]
        matches = gerar_matches_para_permuta(permuta, imoveis, score_minimo=0)
        assert len(matches) == 0

    def test_empty_permutas_list(self):
        imovel = {"id": "imovel-1", "owner_id": "user-a", "valor": 500000}
        assert gerar_matches_para_imovel(imovel, [], score_minimo=0) == []

    def test_empty_imoveis_list(self):
        permuta = {"id": "perm-1", "owner_id": "user-b", "natureza": "permuta_imovel", "valor": 500000}
        assert gerar_matches_para_permuta(permuta, [], score_minimo=0) == []

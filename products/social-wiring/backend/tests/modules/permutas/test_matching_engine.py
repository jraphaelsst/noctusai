"""The shared scorer, exercised through the cases this product depends on.

erp already owns the scorer's own regression suite (56 tests). These do NOT
repeat it. They pin the four behaviours the promotion introduced or that
social-wiring's data shape depends on, each of which fails SILENTLY — no
exception, just a worse or empty answer — and so has no other detector.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.real_estate.matching import (
    SIM_THRESHOLD,
    calcular_bilateral_similarity,
    calcular_score_total,
    falta_vetor_bilateral,
    gerar_matches_para_imovel,
    gerar_matches_para_permuta,
)


def _imovel(**over) -> dict:
    base = {
        "id": "im-1",
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
        "area_total": 250.0,
        "interesses": [],
    }
    base.update(over)
    return base


def _permuta(**over) -> dict:
    base = {
        "id": "pm-1",
        "natureza": "permuta_imovel",
        "status": "ativo",
        "tipo_imovel": "Casa em Condomínio",
        "cidade": "Cotia",
        "bairro": "Granja Viana",
        "estado": "SP",
        "valor": 1_150_000.0,
        "faixa_preco_min": 1_000_000.0,
        "faixa_preco_max": 1_300_000.0,
        "interesses": [],
    }
    base.update(over)
    return base


class TestGuardaDeDonoAusente:
    """🔴 The one deliberate divergence from erp's implementation.

    The original guard was ``permuta['owner_id'] == imovel['owner_id']``.
    With no owner on either side that is ``None == None`` — true — so every
    pair was skipped and the matcher returned ``[]`` while reporting success.
    social-wiring carries no owner identity on these rows (the legacy
    `proprietario` rows are deliberately not promoted to `clientes`), so
    without this fix the entire feature would return nothing, with no error
    anywhere to explain it.
    """

    def test_pares_sem_dono_ainda_casam(self):
        matches = gerar_matches_para_imovel(_imovel(), [_permuta()])
        assert matches, (
            "um par sem owner_id em nenhum dos lados deve casar — o guarda de "
            "auto-permuta não pode tratar None == None como 'mesmo dono'"
        )

    def test_pares_sem_dono_casam_no_sentido_inverso(self):
        matches = gerar_matches_para_permuta(_permuta(), [_imovel()])
        assert matches

    def test_mesmo_dono_real_continua_excluido(self):
        """The guard must still do its job when owners ARE present."""
        matches = gerar_matches_para_imovel(
            _imovel(owner_id="u-1"), [_permuta(owner_id="u-1")]
        )
        assert matches == []

    def test_donos_diferentes_casam(self):
        matches = gerar_matches_para_imovel(
            _imovel(owner_id="u-1"), [_permuta(owner_id="u-2")]
        )
        assert matches


class TestSemanticaAusenteEhVisivel:
    """A missing vector must be REPORTABLE, not merely a lower score.

    This is the erp defect the promotion documents: a pair with no embeddings
    still produces a plausible rule score, so "the AI half never ran" is
    invisible in the output.
    """

    def test_falta_vetor_quando_nenhum_lado_tem(self):
        assert falta_vetor_bilateral(_imovel(), _permuta()) is True

    def test_falta_vetor_quando_so_um_lado_tem(self):
        # Exactly erp's live state: profile vectors written, interest vectors
        # never — so the composite cannot run despite `embedding` being set.
        im = _imovel(embedding=[1.0, 0.0], embedding_interesses=[1.0, 0.0])
        pm = _permuta(embedding=[1.0, 0.0])  # no embedding_interesses
        assert falta_vetor_bilateral(im, pm) is True
        assert calcular_bilateral_similarity(im, pm) == 0.0

    def test_detalhes_registram_disponibilidade_da_semantica(self):
        resultado = calcular_score_total(_imovel(), _permuta())
        assert resultado is not None
        assert resultado["detalhes"]["semantica_disponivel"] is False

    def test_com_os_quatro_vetores_a_semantica_entra(self):
        vec = [1.0, 0.0, 0.0]
        im = _imovel(embedding=vec, embedding_interesses=vec)
        pm = _permuta(embedding=vec, embedding_interesses=vec)
        assert falta_vetor_bilateral(im, pm) is False
        assert calcular_bilateral_similarity(im, pm) == pytest.approx(1.0)
        resultado = calcular_score_total(im, pm)
        assert resultado["detalhes"]["semantica_disponivel"] is True
        assert resultado["detalhes"]["embedding_similarity"] > 0


class TestSimilaridadeEhBilateral:
    """One-sided enthusiasm is worth nothing in a swap."""

    def test_uma_direcao_abaixo_do_limiar_zera_o_par(self):
        # B→A perfect, A→B orthogonal. An average would report ~0.5 and let
        # the pair through; the contract is 0.0.
        im = _imovel(embedding=[1.0, 0.0], embedding_interesses=[0.0, 1.0])
        pm = _permuta(embedding=[1.0, 0.0], embedding_interesses=[1.0, 0.0])
        assert calcular_bilateral_similarity(im, pm) == 0.0

    def test_ambas_as_direcoes_acima_do_limiar_passam(self):
        vec = [1.0, 0.0]
        im = _imovel(embedding=vec, embedding_interesses=vec)
        pm = _permuta(embedding=vec, embedding_interesses=vec)
        assert calcular_bilateral_similarity(im, pm) > SIM_THRESHOLD


class TestPortaoRejeitaComNone:
    """A rejected pair is None, never a zero-scored row.

    A stored zero reads as "considered and incompatible", which invites a UI
    to render it and a re-run to keep it alive.
    """

    def test_regiao_totalmente_diferente_e_rejeitada(self):
        resultado = calcular_score_total(
            _imovel(),
            _permuta(estado="RJ", cidade="Niterói", bairro="Icaraí",
                     faixa_preco_min=None, faixa_preco_max=None),
        )
        assert resultado is None

    def test_imovel_que_nao_aceita_permuta_nunca_entra(self):
        matches = gerar_matches_para_permuta(
            _permuta(), [_imovel(aceita_permutas=False)]
        )
        assert matches == []

"""`GET /api/clientes/{id}/empresas`'s `exige_certidoes`/`motivo` MUST equal
what the contract-generation gate decides for the SAME empresa data (P0c
integration item 3, `sw-drive-extraction-P0c-contract.md`).

`classificar_situacao_pj` (`contrato_gerador.derivacao`) is the single
source for the E1 decision. `card_hub.empresas_service._motivo_e_exigencia`
(the display-only badge) and `derivacao.classificar_empresa`/
`empresas_exigidas` (the contract-generation gate) both call it — this
suite pins that BOTH callers agree, for every branch of the classification,
rather than re-testing the classification itself (already pinned by
`test_contrato_gerador.py`'s `TestQ9CertidoesDeEmpresa`/`TestPJClassification`-
shaped cases).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.modules.card_hub import empresas_service
from app.modules.card_hub.contrato_gerador import derivacao, politica
from app.modules.card_hub.contrato_gerador.dados import Empresa

REFERENCIA = date(2026, 9, 24)
JANELA = politica.POLITICA_PADRAO.pj_baixada_janela_anos


def _empresa_dict(situacao, data_situacao) -> dict:
    return {
        "id": "empresa-1",
        "situacao_cadastral": situacao,
        "data_situacao_cadastral": data_situacao.isoformat() if data_situacao else None,
    }


def _empresa_dataclass(situacao, data_situacao) -> Empresa:
    return Empresa(
        id="empresa-1", cnpj="11222333000181",
        situacao_cadastral=situacao, data_situacao_cadastral=data_situacao,
    )


CASOS = [
    # (situacao, data_situacao_cadastral, exigido esperado, motivo esperado)
    pytest.param(None, None, False, "sem_cartao_cnpj", id="sem_cartao"),
    pytest.param("ativa", None, True, "ativa", id="ativa"),
    pytest.param("inapta", None, True, "inapta", id="inapta"),
    pytest.param("suspensa", None, False, "outra_situacao", id="suspensa"),
    pytest.param("nula", None, False, "outra_situacao", id="nula"),
    pytest.param(
        "baixada", None, False, "sem_cartao_cnpj", id="baixada_sem_data",
    ),
    pytest.param(
        "baixada", REFERENCIA.replace(year=REFERENCIA.year - 2),
        True, "baixada_menos_5_anos", id="baixada_recente",
    ),
    pytest.param(
        "baixada", REFERENCIA.replace(year=REFERENCIA.year - 6),
        False, "baixada_5_anos_ou_mais", id="baixada_antiga",
    ),
    pytest.param(
        "situacao_desconhecida_xyz", None, False, "outra_situacao",
        id="situacao_nao_catalogada",
    ),
]


class TestMotivoParity:
    @pytest.mark.parametrize("situacao,data_situacao,exigido,motivo", CASOS)
    def test_empresas_service_matches_derivacao_gate(
        self, situacao, data_situacao, exigido, motivo
    ):
        # (a) the display-only badge (`GET /api/clientes/{id}/empresas`).
        got_exige, got_motivo = empresas_service._motivo_e_exigencia(
            _empresa_dict(situacao, data_situacao), referencia=REFERENCIA
        )
        assert (got_exige, got_motivo) == (exigido, motivo)

        # (b) the contract-generation gate's own classification, over the
        # SAME data, through the `Empresa` dataclass path.
        codigo = derivacao.classificar_empresa(
            _empresa_dataclass(situacao, data_situacao), REFERENCIA, politica.POLITICA_PADRAO,
        )
        gate_exigido = codigo in derivacao.PJ_CODIGOS_EXIGIDOS
        assert gate_exigido == exigido, (
            f"empresas_service says exigido={exigido} but the contract gate "
            f"says exigido={gate_exigido} for situacao={situacao!r} "
            f"data_situacao_cadastral={data_situacao!r} — the badge and the "
            "gate disagree on the SAME data."
        )

        # (c) `motivo_publico` — the SAME translation `_motivo_e_exigencia`
        # itself calls — must reproduce (a) exactly (a parity tautology by
        # construction today, but the one a future re-fork of either call
        # site would break).
        assert derivacao.motivo_publico(codigo, situacao) == (got_exige, got_motivo)

    def test_janela_boundary_is_shared(self):
        """The `pj_baixada_janela_anos` boundary itself (exactly `JANELA`
        years ago) — both callers must draw the line in the same place."""
        borda = date(REFERENCIA.year - JANELA, REFERENCIA.month, REFERENCIA.day)

        exige, motivo = empresas_service._motivo_e_exigencia(
            _empresa_dict("baixada", borda), referencia=REFERENCIA
        )
        codigo = derivacao.classificar_empresa(
            _empresa_dataclass("baixada", borda), REFERENCIA, politica.POLITICA_PADRAO,
        )
        assert exige == (codigo in derivacao.PJ_CODIGOS_EXIGIDOS)
        assert motivo == derivacao.motivo_publico(codigo, "baixada")[1]

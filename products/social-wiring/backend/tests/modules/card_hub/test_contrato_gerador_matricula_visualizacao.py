"""P5 — the matrícula reader (migration 199) tells a Certidão de Matrícula
from a mere VISUALIZAÇÃO and says why an emission date is missing. The gate
used to drop every undated imóvel certidão — a visualização (no emission by
construction) produced NO blocker, and the pre-118 `onus_certidao_em` field
could answer for it: a silent false-ready. Synthetic data only.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.contrato_gerador.dados import CertidaoImovel
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _com_certidoes(*certidoes: CertidaoImovel, **extra):
    d = fx.variante(1)  # carries the pre-118 `onus_certidao_em` fallback
    return replace(d, imovel=replace(d.imovel, certidoes=tuple(certidoes)), **extra)


VISUALIZACAO = CertidaoImovel(
    tipo="matricula", numero="12345", emitida_em=None,
    tipo_documento_matricula="visualizacao", emissao_motivo="visualizacao_sem_valor_de_certidao",
    documento_id="doc-vis",
)
CERTIDAO = CertidaoImovel(
    tipo="matricula", numero="12345", emitida_em=fx.dias_antes(5),
    tipo_documento_matricula="certidao", documento_id="doc-cert",
)


def _faltas(av) -> dict[str, dict]:
    return {f["campo"]: f for f in av.faltando}


class TestVisualizacaoDaMatricula:
    def test_a_lone_visualizacao_asks_for_the_certidao(self):
        av = _avaliar(_com_certidoes(VISUALIZACAO))
        item = _faltas(av)["imovel.certidao.matricula"]
        assert "visualização, sem valor de certidão" in item["rotulo"]
        assert item["destino"]["tela"] == "imovel"
        assert item["destino"]["alvo"] == derivacao.ALVO_DOCUMENTOS_DO_IMOVEL
        assert not av.pronto

    def test_the_old_onus_certidao_em_never_answers_for_a_visualizacao(self):
        d = _com_certidoes(VISUALIZACAO)
        assert d.imovel.onus_certidao_em is not None
        assert [c.tipo for c in derivacao.certidoes_imovel(d)] == []

    def test_a_certidao_beside_a_visualizacao_wins(self):
        av = _avaliar(_com_certidoes(VISUALIZACAO, CERTIDAO))
        assert not any(k.startswith("imovel.certidao.matricula") for k in _faltas(av))
        assert av.pronto, (av.faltando, av.bloqueios)
        assert derivacao.certidoes_imovel(_com_certidoes(VISUALIZACAO, CERTIDAO))[0] is CERTIDAO

    def test_legacy_waives_age_never_the_type(self):
        av = _avaliar(_com_certidoes(VISUALIZACAO, processo_legado=True))
        assert "imovel.certidao.matricula" in _faltas(av)


class TestCertidaoSemDataDeEmissao:
    @pytest.mark.parametrize(
        "motivo, texto",
        [
            ("emissao_anterior_ao_ultimo_ato", "anterior ao último ato da matrícula"),
            ("emissao_divergente", "datas de emissão divergentes"),
            ("emissao_nao_encontrada", "não foi encontrada no documento"),
            (None, "não foi lida"),
        ],
    )
    def test_an_undated_matricula_certidao_asks_for_the_date_saying_why(self, motivo, texto):
        c = replace(CERTIDAO, emitida_em=None, emissao_motivo=motivo)
        av = _avaliar(_com_certidoes(c))
        item = _faltas(av)["imovel.certidao.matricula.emitida_em"]
        assert texto in item["rotulo"]
        assert item["destino"]["alvo"] == "certidao-matricula-emitida_em"
        assert "imovel.certidao.matricula" not in _faltas(av), "a certidão is on file — only its date is missing"
        assert not av.pronto

    def test_an_undated_iptu_cnd_is_named_too(self):
        cnd = CertidaoImovel(tipo="cnd_iptu", numero="IPTU-1", emitida_em=None, resultado="negativa")
        av = _avaliar(_com_certidoes(CERTIDAO, cnd))
        assert "imovel.certidao.cnd_iptu.emitida_em" in _faltas(av)

    def test_legacy_still_requires_the_date(self):
        c = replace(CERTIDAO, emitida_em=None, emissao_motivo="emissao_nao_encontrada")
        av = _avaliar(_com_certidoes(c, processo_legado=True))
        assert "imovel.certidao.matricula.emitida_em" in _faltas(av)

    def test_the_emission_date_alvo_is_the_input_the_certidoes_card_renders(self):
        """`destino.alvo` is a DOM id: `ImovelCertidoesCard` renders the
        emission-date input as `certidao-${tipo}-${campo}`."""
        fonte = (
            Path(__file__).resolve().parents[4]
            / "frontend" / "src" / "components" / "imovel" / "ImovelCertidoesCard.tsx"
        )
        if not fonte.is_file():
            pytest.skip(f"frontend source not in this checkout: {fonte}")
        texto = fonte.read_text(encoding="utf-8")
        assert "id={`certidao-${tipo}-${campo}`}" in texto
        assert '"emitida_em"' in texto

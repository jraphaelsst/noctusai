"""Deal 876 (2026-10-15): a quotable averbação (AV.06 CONSTRUÇÃO) the operator
did not select left the house out of the `IMÓVEL:` quote and readiness still
said "pronto". Now it blocks (`imovel.matricula.averbacao.<n>`), and the
suggester pre-ticks it. Invented data only."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from noctusai_lib.integrations.documents import segment_matricula_atos

from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.matriculas import estrutura_service as svc
from tests.modules.card_hub import contrato_gerador_fixtures as fx

TEXTO = (
    "Matrícula 12.345\nIMÓVEL: Lote 5 da quadra B, com 250,00m².\n"
    "R-1/12.345 - Em 1 de março de 2000. COMPRA E VENDA - Fulano vendeu a Beltrano.\n"
    "AV-2/12.345 - Em 5 de maio de 2010. CONSTRUÇÃO - Construído um prédio com 120,00m², Habite-se nº 1/2010.\n"
    "AV-3/12.345 - Em 6 de maio de 2010. CADASTRO - Cadastrado na prefeitura, construção existente.\n"
)


def _linhas(texto: str) -> list[dict]:
    return svc.linhas_de_atos(str(uuid4()), str(uuid4()), segment_matricula_atos(texto))


def _avaliar(nao_selecionadas):
    d = fx.variante(1)
    d = replace(
        d,
        matricula=replace(
            d.matricula, averbacoes_citaveis_nao_selecionadas=tuple(nao_selecionadas)
        ),
    )
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _campos(av) -> list[str]:
    return [f["campo"] for f in av.faltando]


class TestProntidao:
    def test_an_unselected_construcao_blocks_with_its_own_campo(self):
        av = _avaliar([(6, "construção / logradouro")])

        item = next(f for f in av.faltando if f["campo"] == "imovel.matricula.averbacao.6")
        assert item["rotulo"].startswith("AV.06 (construção / logradouro)")
        assert "Matrícula → Atos do contrato" in item["rotulo"]
        assert not av.pronto

    def test_everything_selected_is_pronto(self):
        av = _avaliar([])

        assert not [c for c in _campos(av) if c.startswith("imovel.matricula.averbacao.")]
        assert av.pronto, (av.faltando, av.bloqueios)


class TestPredicadoUnico:
    def test_construcao_is_quotable_and_cadastro_is_vetoed(self):
        linhas = _linhas(TEXTO)

        achados = svc.averbacoes_citaveis(TEXTO, linhas)

        assert [(a["numero"], a["titulo"]) for a in achados] == [(2, "construção")]

    def test_sugerir_preticks_the_quotable_averbacao_only(self):
        out = svc.sugerir(TEXTO, _linhas(TEXTO))["descricao"]

        assert [(a["numero"], a["sugerido"]) for a in out] == [(2, True)]

    def test_no_quotable_averbacao_yields_an_empty_list(self):
        texto = TEXTO.split("AV-2")[0]

        assert svc.sugerir(texto, _linhas(texto))["descricao"] == []

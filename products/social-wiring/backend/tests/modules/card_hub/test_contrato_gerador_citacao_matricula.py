"""The `IMÓVEL:` quote follows the office's rule: description + the selected
averbações (`Conforme AV.<n>, …`), never the matrícula's own inscrição
cadastral, areas with a decimal comma. Invented data only."""
from __future__ import annotations

from dataclasses import replace

from noctusai_lib.integrations.docx_render import FakeDocxRenderAdapter
from noctusai_lib.integrations.documents.formatting import FormatRange

from app.modules.card_hub.contrato_gerador import citacao_matricula as cm
from app.modules.card_hub.contrato_gerador.contexto import _descricao_matricula_rica
from tests.modules.card_hub import contrato_gerador_fixtures as fx

DESCRICAO = "Lote 5 da quadra B, encerrando a área de 250,00m²."
AV_HABITE = (
    "AV-4/12.345 - Em 5 de maio de 2010. CONSTRUÇÃO - Pelo requerimento firmado em "
    "1 de abril de 2010, procede-se à presente para constar que foi construído um prédio "
    "com 120,00m² de área construída, conforme Habite-se nº 1/2010."
)
AV_NUMERO = "AV.6/12.345 - Em 10/10/2012.\nVerifica-se a oficialização do nº 77\nda Rua Fictícia."


def _quote(d) -> str:
    return str(_descricao_matricula_rica(d, FakeDocxRenderAdapter()))


def _dados(averbacoes=(), descricao=DESCRICAO):
    d = fx.variante(1)
    m = replace(
        d.matricula,
        descricao_imovel_texto=descricao,
        descricao_imovel_formatacao=(),
        averbacoes=tuple(averbacoes),
    )
    return replace(d, matricula=m)


class TestAverbacoesNaCitacao:
    def test_selected_averbacoes_follow_the_description_in_order_verbatim(self):
        q = _quote(_dados([("4", AV_HABITE), ("6", AV_NUMERO)]))
        assert q.startswith(DESCRICAO + " Conforme AV.4, Pelo requerimento firmado em 1 de abril")
        assert "CONSTRUÇÃO" not in q and "12.345" not in q and "Em 5 de maio" not in q
        assert q.index("Conforme AV.4") < q.index("Conforme AV.6")
        assert q.endswith("Conforme AV.6, Verifica-se a oficialização do nº 77 da Rua Fictícia.")

    def test_no_selected_averbacao_leaves_the_description_alone(self):
        assert _quote(_dados()) == DESCRICAO

    def test_an_act_with_nothing_after_its_header_is_not_quoted(self):
        assert cm.averbacao_citada("3", "AV-3/1.000 - Em 1/1/2010.") is None

    def test_the_number_falls_back_to_the_header(self):
        assert cm.averbacao_citada(None, "AV.9/5 - Em 1/1/2010. Cadastro do imóvel.").startswith(
            "Conforme AV.9, "
        )


AV_ONUS = "AV-3/12.345 - Em 1/2/2009. CÉDULA DE CRÉDITO IMOBILIÁRIO - Pelo instrumento, o Banco Ficticio S.A. é credor; área construída de 90,00m²."
AV_CANCELAMENTO = "AV.5/12.345 - Em 1/2/2011. CANCELAMENTO - Procedo a presente para constar o cancelamento da construção dada em garantia."
AV_CASAMENTO = "AV.7/12.345 - Em 1/2/2013. CASAMENTO - Pelo requerimento, consta o casamento de Fulano e Beltrana."
AV_CADASTRO = "AV.8/12.345 - Em 1/2/2014. CADASTRO - procede-se a presente para constar o cadastro municipal do imóvel."


class TestSoAverbacoesQueMudamADescricao:
    def test_selected_onus_party_and_cadastro_acts_are_not_quoted(self):
        q = _quote(_dados([("3", AV_ONUS), ("5", AV_CANCELAMENTO), ("7", AV_CASAMENTO), ("8", AV_CADASTRO)]))
        assert q == DESCRICAO

    def test_only_the_description_changing_act_survives_among_selected(self):
        q = _quote(_dados([("3", AV_ONUS), ("4", AV_HABITE), ("7", AV_CASAMENTO)]))
        assert "Conforme AV.4," in q and "AV.3" not in q and "AV.7" not in q

    def test_an_untitled_numbering_act_is_recognised_by_its_opening(self):
        t = "AV.9/1 - Em 1/1/2015. Pelo requerimento, procedo a presente para constar que o imóvel recebeu o nº 55 da Rua Fictícia."
        assert cm.averbacao_deve_ser_citada(t)

    def test_the_policy_sets_are_declared_in_politica(self):
        from app.modules.card_hub.contrato_gerador import politica

        assert "construcao" in politica.AVERBACOES_CITADAS
        assert "cancelamento" in politica.AVERBACOES_NAO_CITADAS


class TestSemInscricaoDaMatricula:
    def test_the_matriculas_own_inscricao_line_is_dropped(self):
        d = _dados(descricao=DESCRICAO + "\n\nINSCRIÇÃO CADASTRAL: nº 1234-56 (área maior).")
        assert _quote(d) == DESCRICAO

    def test_a_formatted_range_survives_the_cut(self):
        texto = "Casa ficticia.\nINSCRIÇÃO CADASTRAL: 99.\nFim."
        out, ranges = cm.sem_inscricao_da_matricula(texto, [FormatRange(0, 4, bold=True)])
        assert "INSCRIÇÃO" not in out and out.endswith("Fim.")
        assert ranges == [FormatRange(0, 4, bold=True)]


class TestAreasPtBr:
    def test_dot_thousands_glued_to_a_unit_becomes_a_decimal_comma(self):
        assert cm.normalizar_areas("área de 11.500m2 e 3.200 m²") == "área de 11,500m2 e 3,200 m²"

    def test_already_correct_numbers_are_untouched(self):
        s = "mede 11,500m2, área de 1.234,56m² e Habite-se nº 1.234/2010"
        assert cm.normalizar_areas(s) == s

    def test_the_quote_applies_it(self):
        assert "126,700m2" in _quote(_dados(descricao="encerrando a área de 126.700m2."))


AV_COM_MOBILIARIO = (
    "Av.12, em 3 de janeiro de 2019. -\n\nCONSTRUÇÃO -\n\nPelo requerimento firmado em 1 de dezembro de 2018, "
    "procedo a presente para constar que foi construída uma residência com área to-\ntal de 120,00 metros\n"
    "quadrados, conforme Habite-se nº 5/2018. Foi apresentada a certidão negativa, sendo atribuído o valor de R$ 1,00. -\n"
    "- segue ficha 2 -\n\nCNM 000000.0.0000000-00\n\nLIVRO N.º 2 - REGISTRO GERAL\n\n"
    "SERVENTIA DO REGISTRO DE IMÓVEIS\nde Cidadeficticia\n\nmatrícula\n\n-12.345-\n\ndata\n\n-03-\n\n"
    "Cidadeficticia, de _____________ de _____________\n\nEU, ____ (Fulano Ficticio) escrevente\nautorizado, digitei.\n"
    "D.R$10,00\n\nMOD. 10\n"
)
AV_PAGINA_NO_MEIO = (
    "AV. 4 - em 9 de janeiro de 2017 (CONSTRUÇÃO)\n(prenotado em 8 de janeiro de 2017 – protocolo nº 1.234)\n\n"
    "Nos termos do requerimento, procede-se a averbação para constar que o imóvel recebeu o número 7 da\n\n"
    "continua na ficha 2\n\nLIVRO Nº 2\nREGISTRO GERAL\n\nmatrícula\n\n999\n\ndata\n\n09\n\n"
    "Cidadeficticia, 9 de janeiro de 2017\n\nRua das Flores. Foi apresentada certidão negativa.\n\n"
    "Beltrano de Tal – Escrevente\n"
)


class TestSoOCorpoDoAto:
    def test_footer_signatures_selo_and_closing_sentences_are_cut(self):
        q = cm.averbacao_citada("12", AV_COM_MOBILIARIO)
        assert q == (
            "Conforme AV.12, Pelo requerimento firmado em 1 de dezembro de 2018, procedo a presente "
            "para constar que foi construída uma residência com área total de 120,00 metros quadrados, "
            "conforme Habite-se nº 5/2018."
        )

    def test_the_header_is_not_duplicated(self):
        q = cm.averbacao_citada("12", AV_COM_MOBILIARIO)
        assert q.count("Av.") + q.count("AV.") == 1

    def test_page_furniture_inside_the_act_is_removed_and_the_sentence_rejoined(self):
        q = cm.averbacao_citada("4", AV_PAGINA_NO_MEIO)
        assert q == (
            "Conforme AV.4, Nos termos do requerimento, procede-se a averbação para constar que "
            "o imóvel recebeu o número 7 da Rua das Flores."
        )

    def test_dehyphenation_needs_lowercase_on_both_sides(self):
        assert cm.corpo_do_ato("AV.1 - Em 1/1/2010. Cotia-\nSP e to-\ntal e 2- 3 e a - b.") == "Cotia- SP e total e 2- 3 e a - b."

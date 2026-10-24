"""`certidao_resultado` — a certidão's verdict from the issuer's printed
sentence. Fixtures are SYNTHETIC sentences shaped after each issuer's real
wording; no real names or numbers."""
import pytest

from noctusai_lib.integrations.documents.certidao_resultado import (
    LEITORES,
    NAO_EMITIDA,
    NEGATIVA,
    NEGATIVA_COM_HOMONIMOS,
    POSITIVA,
    POSITIVA_COM_EFEITO_DE_NEGATIVA,
    ler_resultado_certidao,
)

CASOS = [
    # Receita / PGFN
    ("cnd_federal", "CERTIDÃO NEGATIVA DE DÉBITOS RELATIVOS AOS TRIBUTOS FEDERAIS E À DÍVIDA ATIVA DA UNIÃO", NEGATIVA),
    ("cnd_federal", "CERTIDÃO POSITIVA COM EFEITOS DE NEGATIVA DE DÉBITOS RELATIVOS AOS TRIBUTOS FEDERAIS. "
                    "Constam débitos administrados pela Secretaria da Receita Federal", POSITIVA_COM_EFEITO_DE_NEGATIVA),
    ("cnd_federal", "As informações disponíveis na Secretaria da Receita Federal sobre o contribuinte "
                    "são insuficientes para emitir a certidão pela Internet.", NAO_EMITIDA),
    ("cnd_federal", "Inscrição no CNPJ inapta - Emissão de certidão não permitida.", NAO_EMITIDA),
    # SEFAZ-SP
    ("cnd_fazenda_sp", "é certificado que não constam débitos declarados ou apurados pendentes de inscrição", NEGATIVA),
    ("cnd_fazenda_sp", "Não foi possível emitir a Certidão Negativa. Por favor, acesse a opção "
                       "\"Relatório de Pendências Fiscais\"", NAO_EMITIDA),
    # PGE-SP dívida ativa
    ("divida_ativa_sp", "CERTIDÃO NEGATIVA DE DÉBITOS INSCRITOS DA DÍVIDA ATIVA. é certificado que: "
                        "não constam débitos inscritos em Dívida Ativa de responsabilidade", NEGATIVA),
    ("divida_ativa_sp", "As informações do contribuinte que constam da base de dados não permitem a emissão "
                        "da certidão de regularidade. O pedido de certidão positiva ou certidão positiva com "
                        "efeito de negativa deverá ser feito mediante requerimento", NAO_EMITIDA),
    # TST
    ("cnd_trabalhista_tst", "CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS Nome: FULANO. Certifica-se que FULANO, "
                            "inscrito(a) no CPF sob o nº 000, NÃO CONSTA como inadimplente no Banco Nacional "
                            "de Devedores Trabalhistas.", NEGATIVA),
    ("cnd_trabalhista_tst", "CERTIDÃO POSITIVA DE DÉBITOS TRABALHISTAS Nome: FULANO. Certifica-se que FULANO "
                            "CONSTA do Banco Nacional de Devedores Trabalhistas em face do inadimplemento", POSITIVA),
    # TRF3
    ("trf3", "CERTIFICAMOS, na forma da lei, que, consultando os sistemas processuais abaixo indicados, "
             "NÃO CONSTAM, até a presente data e hora, processos de classes cíveis", NEGATIVA),
    ("trf3_sp", "consultando os sistemas processuais abaixo indicados, CONSTAM, até a presente data e hora, "
                "processos de classes cíveis em tramitação contra: FULANO", POSITIVA),
    # TRT2
    ("trt2_digital", "QUE ATÉ A PRESENTE DATA NÃO CONSTAM AÇÕES TRABALHISTAS NESTE TRIBUNAL REGIONAL", NEGATIVA),
    ("trt2_digital", "QUE ATÉ A PRESENTE DATA CONSTAM AS SEGUINTES AÇÕES TRABALHISTAS NESTE TRIBUNAL", POSITIVA),
    ("trt2_fisico", "até 01/01/2026, NÃO CONSTA AÇÃO TRABALHISTA EM TRAMITAÇÃO em face da pessoa", NEGATIVA),
    ("trt2_fisico", "CONSTAM, até 01/01/2026, as ações trabalhistas em tramitação em face da pessoa", POSITIVA),
    # TJSP e-SAJ / e-Proc
    ("tjsp_esaj", "verificou NADA CONSTAR como réu/requerido/interessado em nome de: *** FULANO, RG: 1, CPF: 2", NEGATIVA),
    ("tjsp_esaj", "verificou CONSTAR como réu/requerido/interessado em nome de: *** FULANO, RG: 1, CPF: 2, "
                  "conforme indicação constante do pedido. A SEGUINTE DISTRIBUIÇÃO: Foro de Exemplo", POSITIVA),
    ("tjsp_eproc", "no sistema eproc, verificamos NADA CONSTAR em nome de: Nome: FULANO", NEGATIVA),
    ("tjsp_eproc", "no sistema eproc, verificamos CONSTAR em nome de: Nome: FULANO", POSITIVA),
    # CENPROT
    ("cenprot", "Resumo da consulta: No Estado de São Paulo não constam protestos nos cartórios participantes", NEGATIVA),
    ("cenprot", "1º Tabelião de Protesto de Exemplo - SP. Quantidade de protestos: 2 · Valor protestado: R$ 10,00", POSITIVA),
]


@pytest.mark.parametrize("tipo,texto,esperado", CASOS)
def test_issuer_sentence(tipo, texto, esperado):
    assert ler_resultado_certidao(tipo, texto) == esperado


def test_tjsp_unqualified_homonyms_next_to_nada_constar():
    texto = (
        "verificou NADA CONSTAR como réu/requerido/interessado em nome de: *** FULANO DE TAL, RG: 1, CPF: 2. "
        "CERTIFICA AINDA QUE, em razão da inexistência de elementos de identificação pessoal (RG ou CPF) "
        "na base de dados do distribuidor, verificou CONSTAR como réu/requerido/interessado em nome de "
        "FULANO DE TAL, NÃO QUALIFICADO(A), a distribuição abaixo relacionada, que pode referir-se a homônimo:"
    )
    assert ler_resultado_certidao("tjsp_esaj", texto) == NEGATIVA_COM_HOMONIMOS


def test_tjsp_qualified_hit_stays_positiva_even_with_a_homonym_list():
    texto = (
        "verificou CONSTAR como réu/requerido/interessado em nome de: *** FULANO, RG: 1, CPF: 2. "
        "CERTIFICA AINDA QUE … NÃO QUALIFICADO(A), as distribuições abaixo relacionadas, que podem "
        "referir-se a homônimos:"
    )
    assert ler_resultado_certidao("tjsp_esaj", texto) == POSITIVA


def test_contradictory_sentences_are_not_guessed():
    texto = "NÃO CONSTAM AÇÕES TRABALHISTAS ... CONSTAM AS SEGUINTES AÇÕES TRABALHISTAS"
    assert ler_resultado_certidao("trt2_digital", texto) is None


def test_a_refusal_that_quotes_the_other_kinds_is_still_a_refusal():
    # The PGE page names "certidão positiva com efeito de negativa" while refusing.
    assert ler_resultado_certidao("divida_ativa_sp", CASOS[7][1]) == NAO_EMITIDA


@pytest.mark.parametrize("tipo,texto", [
    ("serasa", "NÃO CONSTAM OCORRÊNCIAS"),          # own parser, not here
    ("cnd_federal", ""),
    ("cnd_federal", "   "),
    ("cnd_federal", None),
    ("trf3", "página sem o texto de certificação"),
])
def test_nothing_unambiguous_is_none(tipo, texto):
    assert ler_resultado_certidao(tipo, texto) is None


def test_every_registry_tipo_with_a_fixed_sentence_has_a_reader():
    assert set(LEITORES) == {
        "cnd_federal", "cnd_fazenda_sp", "divida_ativa_sp", "cnd_trabalhista_tst", "trf3", "trf3_sp",
        "trt2_digital", "trt2_fisico", "tjsp_esaj", "tjsp_eproc", "cenprot",
    }


# --- identificação impressa (RG + CPF) -------------------------------------
from noctusai_lib.integrations.documents.certidao_resultado import ler_identificacao_impressa  # noqa: E402

_ESAJ = (
    "TRIBUNAL DE JUSTIÇA DO ESTADO DE SÃO PAULO SISTEMA E-SAJ "
    "CERTIDÃO DE DISTRIBUIÇÃO CÍVEL\nNome: MARIA TESTE\nRG: 30.738.581-4\nCPF: 111.444.777-35\n"
)


class TestIdentificacaoImpressa:
    def test_esaj_devolve_rg_com_dv_e_cpf(self):
        assert ler_identificacao_impressa("tjsp_esaj", _ESAJ) == ("30.738.581-4", "111.444.777-35")

    def test_tipo_sem_rg_impresso_ou_sem_texto(self):
        assert ler_identificacao_impressa("cnd_federal", _ESAJ) is None
        assert ler_identificacao_impressa("tjsp_esaj", "") is None
        assert ler_identificacao_impressa("tjsp_esaj", None) is None

    def test_sem_rotulo_rg_ou_cpf_nao_conta(self):
        assert ler_identificacao_impressa("tjsp_esaj", "SISTEMA E-SAJ CPF: 111.444.777-35") is None
        assert ler_identificacao_impressa("tjsp_esaj", "SISTEMA E-SAJ RG: 30.738.581-4") is None

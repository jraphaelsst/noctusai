"""`extrair_detalhes_ato` — one act of a matrícula, read into typed details.

🔴 WHAT THESE PIN
-----------------
1. Every text value is a SUBSTRING of the act (checked over every fixture):
   the contract quotes names and instruments, and a "cleaned" name is a
   different name.
2. Unknown is `None` with confidence `nenhuma` — a missing label, a foreign
   currency, two disagreeing dates are never resolved by guessing.
3. The real-world phrasing variants that tripped the first draft: a CPF at
   the end of a sentence, `S.A.` before a comma, a street named after a date,
   a citation of ANOTHER matrícula's act.

Every name, CPF, CNPJ, bank, cartório and address below is invented; the
CPF/CNPJ numbers are check-digit-valid synthetic values unless a test says
otherwise.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents import (
    NATUREZAS_ATO,
    AtoDetalhes,
    AtoReferido,
    Instrumento,
    Parte,
    cpf_cnpj_valido,
    extrair_detalhes_ato,
    formatar_cpf_cnpj,
    frase_titulo_aquisitivo,
    parse_detalhes_json,
)

# ─── fixtures ─────────────────────────────────────────────────────────────

CV_SIMPLES = (
    "R-1/45.678 - Em 10 de março de 2001. COMPRA E VENDA. Transmitente: Fulana de "
    "Teste Exemplar; adquirente: Beltrano Modelo. Valor R$ 100.000,00.\n"
)

ESCRITURA_COMPLETA = (
    "R.3/12.345 - Protocolo nº 223.344 de 01/03/2020. Data: 12/03/2020. VENDA E COMPRA. "
    "TÍTULO: Escritura Pública de Venda e Compra lavrada em 12/03/2020 no 2º Tabelionato "
    "de Notas de Cotia, Livro 100, fls. 20. "
    "TRANSMITENTES: JOÃO EXEMPLO DA SILVA, brasileiro, engenheiro, CPF 123.456.789-09, "
    "e sua mulher MARIA FICTÍCIA DA SILVA, brasileira, CPF nº 111.444.777-35, residentes "
    "na Rua Inventada, 10 - Centro, Cotia-SP; "
    "ADQUIRENTE: PEDRO AMOSTRA SOUZA, brasileiro, solteiro, inscrito no CPF/MF sob nº "
    "987.654.321-00. VALOR: R$ 450.000,00 (quatrocentos e cinquenta mil reais). Valor "
    "venal R$ 300.000,00. O Oficial.\n"
)

HIPOTECA_NARRATIVA = (
    "R-2/45.678 - Em 11 de março de 2001. HIPOTECA em favor do Banco Imaginario S/A.\n"
)

HIPOTECA_SA = (
    "R-6/7.777 - Em 04/04/2004. HIPOTECA em favor do BANCO EXEMPLO S.A., CNPJ "
    "11.222.333/0001-81, para garantia da dívida de R$ 90.000,00.\n"
)

AF_ROTULADA = (
    "R.4/12.345 - Em 12/03/2020 - ALIENAÇÃO FIDUCIÁRIA - Pelo instrumento particular de "
    "05/03/2020, com força de escritura pública, nos termos da Lei 9.514/97, o adquirente "
    "do R-3 alienou fiduciariamente o imóvel. CREDORA FIDUCIÁRIA: CAIXA ECONÔMICA EXEMPLO "
    "- CEE, CNPJ 11.222.333/0001-81. DEVEDOR FIDUCIANTE: PEDRO AMOSTRA SOUZA. Valor da "
    "dívida: R$ 360.000,00.\n"
)

CANCELAMENTO = (
    "AV-3/45.678 - Em 5 de maio de 2010. CANCELAMENTO da hipoteca objeto do R-2, por "
    "quitaçao.\n"
)

LEVANTAMENTO = (
    "AV-9/9.876 - Em 03/03/2023. LEVANTAMENTO DA PENHORA objeto da AV-8, conforme "
    "mandado expedido em 20/02/2023.\n"
)

DOACAO_COM_USUFRUTO = (
    "R-7/9.876 — 15/08/2019 — DOAÇÃO com reserva de usufruto. Formal: Escritura de "
    "doação de 02/08/2019, do 15º Tabelião de Notas de São Paulo/SP, livro 3.210, "
    "páginas 101/104. DOADORES: ANTONIO FALSO NETO e LUIZA FALSA NETO, brasileiros, "
    "casados. DONATÁRIA: CARLA FALSA NETO, CPF 246.813.579-28. Valor R$ 200.000,00.\n"
)

PENHORA = (
    "AV.8/9.876 - Data: 10/10/2021. PENHORA. Mandado de Penhora expedido em 01/10/2021 "
    "pelo Juízo da 3ª Vara Cível. Exequente: CONDOMINIO EDIFICIO FICTICIO. Executado: "
    "CARLA FALSA NETO.\n"
)

PARTILHA = (
    "R-5/3.333 - Em 20/11/2010. PARTILHA. Título: Formal de Partilha expedido em "
    "10/10/2010 pelo Juízo da 2ª Vara da Família e Sucessões da Comarca Fictícia, "
    "extraído dos autos de inventário dos bens deixados por OSVALDO EXEMPLAR. "
    "HERDEIROS: (1) ANA EXEMPLO COSTA, CPF 135.792.468-28 (2) BRUNO EXEMPLO COSTA, "
    "CPF 314.159.265-90.\n"
)

ARREMATACAO = (
    "R-9/2.222 - Em 01/02/2022. ARREMATAÇÃO. Carta de Arrematação expedida em 15/01/2022 "
    "pelo Juízo da 1ª Vara Cível. ARREMATANTE: IMOBILIARIA MODELO LTDA, CNPJ "
    "99.888.777/0001-00. Lance: R$ 150.000,00.\n"
)

OUTORGANTES = (
    "R.2/8.080 - 05/05/2005 - VENDA E COMPRA. OUTORGANTES VENDEDORES: RICARDO EXEMPLO "
    "PINTO, CPF 12345678909; OUTORGADO COMPRADOR: SERGIO AMOSTRA ALVES, CPF "
    "111.444.777-36.\n"
)

PARENTESES = (
    "R-3/8.080 - Em 06/06/2006. VENDA. TRANSMITENTE(S): SERGIO AMOSTRA ALVES, CPF "
    "111.444.777-35. ADQUIRENTE(S): TANIA EXEMPLO ROCHA, CPF 987.654.321-00.\n"
)

NARRATIVA_VENDA = "R-3/555 - Em 2017 venda a CICRANO FALSO por R$ 80.000,00.\n"

#: The real-world shape that motivated the narrative role fallback: numbered,
#: already-qualified transmitentes (no label at all) followed by a
#: permuta verb whose object description ("por permuta o imóvel
#: matriculado") sits between the verb and the buyer's own preposition.
NARRATIVA_PERMUTA_JA_QUALIFICADOS = (
    "R-4/33.222 - Em 10/09/2020. PERMUTA. Por escritura pública datada de 10 de "
    "setembro de 2020, do 3º Tabelião de Notas de Cotia, livro 200, fls. 55, "
    "1) RODRIGO EXEMPLO SOUZA, residente e domiciliado na Rua Amostra, nº 12, "
    "Cotia-SP; e 2) TAUANE EXEMPLO SOUZA, residente e domiciliada na Rua Amostra, "
    "nº 12, Cotia-SP, ambos já qualificados, transmitiram por permuta o imóvel "
    "matriculado a MARIA FICTÍCIA ROCHA, brasileira, divorciada, secretária "
    "executiva, RG nº 22.333.444-SSP/SP, CPF nº 111.222.333-96, residente e "
    "domiciliada na Avenida Modelo, nº 500, Cotia-SP, pelo valor de R$ "
    "250.000,00.\n"
)

#: A couple named together as the (unlabelled) buyer side — the cap this
#: fallback used to apply (`achados[:1]`) would silently drop the second one.
NARRATIVA_CASAL_ADQUIRENTE = (
    "R-8/99.111 - Em 05/05/2022. VENDA. Por escritura, o imóvel foi vendido a "
    "RODRIGO EXEMPLO SOUZA e TAUANE EXEMPLO SOUZA, brasileiros, casados.\n"
)

CONSTRUCAO = (
    "AV-2/555 - Em 2016 construcao. Averba-se a CONSTRUÇÃO de um prédio residencial com "
    "120,00m², conforme habite-se nº 55/2016. Dou fe.\n"
)

PROMESSA = (
    "R-4/6.060 - Em 07/07/2007. PROMESSA DE VENDA E COMPRA do imóvel, irrevogável.\n"
)

PERMUTA = "R-2/4.040 - Em 08/08/2008. PERMUTA. Valor atribuído: R$ 320.000,00.\n"

DACAO = "R-6/4.040 - Em 09/09/2009. DAÇÃO EM PAGAMENTO a credor fictício.\n"

SEM_NATUREZA = "AV-5/4.040 - Em 10/10/2010. Averba-se a alteração do nome da rua.\n"

CRUZEIROS = (
    "R-1/100 - Em 10 de março de 1985. COMPRA E VENDA. Valor Cr$ 1.500.000,00.\n"
)

SO_VALOR_VENAL = "R-2/100 - Em 11/03/1999. VENDA. Valor venal R$ 70.000,00.\n"

DOIS_VALORES = (
    "R-3/100 - Em 12/03/2012. VENDA E COMPRA. Preço: R$ 300.000,00, sendo o valor de "
    "R$ 60.000,00 pago à vista.\n"
)

DATAS_EM_CONFLITO = "R-2/100 - Em 10/03/2001. VENDA. Registrado em 11/03/2001.\n"

DATA_NO_FECHO = (
    "AV-4/100 - Averba-se o casamento do proprietário, conforme certidão apresentada. "
    "Cotia, 12 de março de 2020.\n"
)

CPF_INVALIDO = (
    "R-8/100 - Em 01/01/2018. VENDA. Adquirente: HELENA EXEMPLO DIAS, CPF 123.456.789-00.\n"
)

CITACOES = (
    "R-1/45.678 - Em 02/02/2002. VENDA E COMPRA. Imóvel: lote 5 da Quadra R-1, na Av. 9 "
    "de Julho, 100. REGISTRO ANTERIOR: R-3/1.234 do 9º Oficio. Adquirente: RENATA "
    "EXEMPLO LIMA; averbada a construção na AV-2/45.678 e referido no registro nº 4.\n"
)

MINUSCULAS_OCR = (
    "r.2 — em 03/04/2011 — alienaçao fiduciaria em garantia a favor do banco "
    "ficticio s/a.\n"
)

TODAS = [
    CV_SIMPLES, ESCRITURA_COMPLETA, HIPOTECA_NARRATIVA, HIPOTECA_SA, AF_ROTULADA,
    CANCELAMENTO, LEVANTAMENTO, DOACAO_COM_USUFRUTO, PENHORA, PARTILHA, ARREMATACAO,
    OUTORGANTES, PARENTESES, NARRATIVA_VENDA, CONSTRUCAO, PROMESSA, PERMUTA, DACAO,
    SEM_NATUREZA, CRUZEIROS, SO_VALOR_VENAL, DOIS_VALORES, DATAS_EM_CONFLITO,
    DATA_NO_FECHO, CPF_INVALIDO, CITACOES, MINUSCULAS_OCR,
    NARRATIVA_PERMUTA_JA_QUALIFICADOS, NARRATIVA_CASAL_ADQUIRENTE,
]


# ─── invariants ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("texto", TODAS)
def test_every_text_value_is_a_literal_substring(texto):
    d = extrair_detalhes_ato(texto)
    textos = [p.nome for p in d.transmitentes + d.adquirentes]
    if d.credor:
        textos.append(d.credor)
    if d.instrumento:
        i = d.instrumento
        textos.extend(v for v in (i.tipo, i.tabelionato, i.livro, i.folhas, i.cidade) if v)
    for valor in textos:
        assert valor in texto, f"{valor!r} is not a slice of the act"
        assert valor == valor.strip()


@pytest.mark.parametrize("texto", TODAS)
def test_confidence_and_value_agree(texto):
    """`nenhuma` <=> no value, for every field — no half-reported reading."""
    d = extrair_detalhes_ato(texto)
    pares = [
        (d.natureza, d.natureza_confianca),
        (d.data_registro, d.data_registro_confianca),
        (d.valor, d.valor_confianca),
        (d.transmitentes or None, d.transmitentes_confianca),
        (d.adquirentes or None, d.adquirentes_confianca),
        (d.credor, d.credor_confianca),
        (d.instrumento, d.instrumento_confianca),
        (d.atos_referidos or None, d.atos_referidos_confianca),
    ]
    for valor, confianca in pares:
        assert confianca in ("alta", "baixa", "nenhuma")
        assert (valor is None) == (confianca == "nenhuma")
    assert d.natureza is None or d.natureza in NATUREZAS_ATO


@pytest.mark.parametrize("texto", TODAS)
def test_json_round_trip(texto):
    d = extrair_detalhes_ato(texto)
    assert parse_detalhes_json(d.to_json()) == d


def test_empty_text_is_all_unknown():
    assert extrair_detalhes_ato("") == AtoDetalhes()
    assert extrair_detalhes_ato("   \n") == AtoDetalhes()


# ─── natureza ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "natureza", "confianca"),
    [
        (CV_SIMPLES, "compra_e_venda", "alta"),
        (ESCRITURA_COMPLETA, "compra_e_venda", "alta"),
        (HIPOTECA_NARRATIVA, "hipoteca", "alta"),
        (AF_ROTULADA, "alienacao_fiduciaria", "alta"),
        (CANCELAMENTO, "cancelamento", "alta"),
        (LEVANTAMENTO, "cancelamento", "alta"),
        (PENHORA, "penhora", "alta"),
        (PARTILHA, "partilha", "alta"),
        (ARREMATACAO, "arrematacao", "alta"),
        (CONSTRUCAO, "construcao", "alta"),
        (PERMUTA, "permuta", "alta"),
        (DACAO, "dacao", "alta"),
        (MINUSCULAS_OCR, "alienacao_fiduciaria", "alta"),
    ],
)
def test_natureza(texto, natureza, confianca):
    d = extrair_detalhes_ato(texto)
    assert (d.natureza, d.natureza_confianca) == (natureza, confianca)


def test_a_cancellation_is_not_the_encumbrance_it_cancels():
    assert extrair_detalhes_ato(CANCELAMENTO).natureza == "cancelamento"


def test_a_promise_of_sale_is_not_a_sale():
    assert extrair_detalhes_ato(PROMESSA).natureza == "outro"


def test_a_competing_nature_in_the_same_sentence_lowers_confidence():
    """`DOAÇÃO com reserva de usufruto` is a doação — but not an unambiguous one."""
    d = extrair_detalhes_ato(DOACAO_COM_USUFRUTO)
    assert (d.natureza, d.natureza_confianca) == ("doacao", "baixa")


def test_an_act_with_no_known_nature_is_none_not_outro():
    d = extrair_detalhes_ato(SEM_NATUREZA)
    assert (d.natureza, d.natureza_confianca) == (None, "nenhuma")


# ─── data_registro ────────────────────────────────────────────────────────


def test_textual_date_right_after_the_header():
    d = extrair_detalhes_ato(CV_SIMPLES)
    assert (d.data_registro, d.data_registro_confianca) == (date(2001, 3, 10), "alta")


def test_numeric_date_right_after_the_header():
    assert extrair_detalhes_ato(DOACAO_COM_USUFRUTO).data_registro == date(2019, 8, 15)
    assert extrair_detalhes_ato(OUTORGANTES).data_registro == date(2005, 5, 5)


def test_the_protocol_and_instrument_dates_are_not_the_registration_date():
    d = extrair_detalhes_ato(ESCRITURA_COMPLETA)
    assert (d.data_registro, d.data_registro_confianca) == (date(2020, 3, 12), "alta")
    assert extrair_detalhes_ato(PENHORA).data_registro == date(2021, 10, 10)


def test_two_labelled_dates_that_disagree_are_absence():
    d = extrair_detalhes_ato(DATAS_EM_CONFLITO)
    assert (d.data_registro, d.data_registro_confianca) == (None, "nenhuma")


def test_the_closing_city_date_is_a_low_confidence_reading():
    d = extrair_detalhes_ato(DATA_NO_FECHO)
    assert (d.data_registro, d.data_registro_confianca) == (date(2020, 3, 12), "baixa")


def test_a_year_alone_is_not_a_date():
    assert extrair_detalhes_ato(CONSTRUCAO).data_registro is None


# ─── valor ────────────────────────────────────────────────────────────────


def test_labelled_value_in_reais():
    d = extrair_detalhes_ato(CV_SIMPLES)
    assert (d.valor, d.valor_confianca) == (Decimal("100000.00"), "alta")


def test_valor_venal_is_never_the_value():
    assert extrair_detalhes_ato(ESCRITURA_COMPLETA).valor == Decimal("450000.00")
    d = extrair_detalhes_ato(SO_VALOR_VENAL)
    assert (d.valor, d.valor_confianca) == (None, "nenhuma")


def test_a_foreign_or_old_currency_is_not_read_as_reais():
    assert extrair_detalhes_ato(CRUZEIROS).valor is None


def test_two_different_labelled_amounts_keep_the_first_at_low_confidence():
    d = extrair_detalhes_ato(DOIS_VALORES)
    assert (d.valor, d.valor_confianca) == (Decimal("300000.00"), "baixa")


def test_an_unlabelled_amount_is_low_confidence():
    d = extrair_detalhes_ato(NARRATIVA_VENDA)
    assert (d.valor, d.valor_confianca) == (Decimal("80000.00"), "baixa")


# ─── partes ───────────────────────────────────────────────────────────────


def test_labelled_parties_with_verified_documents_are_alta():
    d = extrair_detalhes_ato(ESCRITURA_COMPLETA)
    assert d.transmitentes == (
        Parte("JOÃO EXEMPLO DA SILVA", "123.456.789-09"),
        Parte("MARIA FICTÍCIA DA SILVA", "111.444.777-35"),
    )
    assert d.transmitentes_confianca == "alta"
    assert d.adquirentes == (Parte("PEDRO AMOSTRA SOUZA", "987.654.321-00"),)
    assert d.adquirentes_confianca == "alta"


def test_parties_without_a_document_are_baixa():
    d = extrair_detalhes_ato(CV_SIMPLES)
    assert d.transmitentes == (Parte("Fulana de Teste Exemplar"),)
    assert d.adquirentes == (Parte("Beltrano Modelo"),)
    assert d.transmitentes_confianca == d.adquirentes_confianca == "baixa"


def test_outorgante_labels_and_a_bare_eleven_digit_cpf():
    d = extrair_detalhes_ato(OUTORGANTES)
    assert d.transmitentes == (Parte("RICARDO EXEMPLO PINTO", "123.456.789-09"),)
    assert d.transmitentes_confianca == "alta"
    # 111.444.777-36 fails its check digit: kept for the operator, never alta.
    assert d.adquirentes == (Parte("SERGIO AMOSTRA ALVES", "111.444.777-36"),)
    assert d.adquirentes_confianca == "baixa"


def test_plural_in_parentheses_labels():
    d = extrair_detalhes_ato(PARENTESES)
    assert [p.nome for p in d.transmitentes] == ["SERGIO AMOSTRA ALVES"]
    assert [p.nome for p in d.adquirentes] == ["TANIA EXEMPLO ROCHA"]


def test_a_failed_check_digit_is_baixa():
    d = extrair_detalhes_ato(CPF_INVALIDO)
    assert d.adquirentes == (Parte("HELENA EXEMPLO DIAS", "123.456.789-00"),)
    assert d.adquirentes_confianca == "baixa"


def test_two_names_sharing_one_qualification_get_no_cpf():
    d = extrair_detalhes_ato(DOACAO_COM_USUFRUTO)
    assert d.transmitentes == (Parte("ANTONIO FALSO NETO"), Parte("LUIZA FALSA NETO"))
    assert d.transmitentes_confianca == "baixa"
    assert d.adquirentes == (Parte("CARLA FALSA NETO", "246.813.579-28"),)


def test_numbered_heirs():
    d = extrair_detalhes_ato(PARTILHA)
    assert d.adquirentes == (
        Parte("ANA EXEMPLO COSTA", "135.792.468-28"),
        Parte("BRUNO EXEMPLO COSTA", "314.159.265-90"),
    )
    assert d.adquirentes_confianca == "alta"


def test_a_company_party_with_a_cnpj():
    d = extrair_detalhes_ato(ARREMATACAO)
    assert d.adquirentes == (Parte("IMOBILIARIA MODELO LTDA", "99.888.777/0001-00"),)


def test_narrative_buyer_is_baixa():
    d = extrair_detalhes_ato(NARRATIVA_VENDA)
    assert d.adquirentes == (Parte("CICRANO FALSO"),)
    assert d.adquirentes_confianca == "baixa"


def test_parties_of_other_roles_are_not_transmitentes():
    d = extrair_detalhes_ato(PENHORA)
    assert d.transmitentes == () and d.adquirentes == ()


def test_unlabelled_transmitentes_come_from_the_narrative_before_the_verb():
    """No `TRANSMITENTE:` label anywhere — the numbered, already-qualified
    pair before "transmitiram" is read off the narrative, and the buyer
    after "por permuta o imóvel matriculado a" survives the object
    description sitting between the verb and the preposition."""
    d = extrair_detalhes_ato(NARRATIVA_PERMUTA_JA_QUALIFICADOS)
    assert d.transmitentes == (
        Parte("RODRIGO EXEMPLO SOUZA"),
        Parte("TAUANE EXEMPLO SOUZA"),
    )
    assert d.transmitentes_confianca == "baixa"
    assert d.adquirentes == (Parte("MARIA FICTÍCIA ROCHA", "111.222.333-96"),)
    # unlabelled is always "baixa" here, even with a check-digit-valid CPF —
    # same rule `test_narrative_buyer_is_baixa` already pins.
    assert d.adquirentes_confianca == "baixa"


def test_an_unlabelled_couple_is_two_adquirentes_not_one():
    """The old `achados[:1]` cap would have dropped the second name here."""
    d = extrair_detalhes_ato(NARRATIVA_CASAL_ADQUIRENTE)
    assert d.adquirentes == (
        Parte("RODRIGO EXEMPLO SOUZA"),
        Parte("TAUANE EXEMPLO SOUZA"),
    )
    assert d.adquirentes_confianca == "baixa"


# ─── credor ───────────────────────────────────────────────────────────────


def test_narrative_creditor_is_baixa():
    d = extrair_detalhes_ato(HIPOTECA_NARRATIVA)
    assert (d.credor, d.credor_confianca) == ("Banco Imaginario S/A", "baixa")


def test_narrative_creditor_with_a_verified_cnpj_keeps_the_sa_dot():
    d = extrair_detalhes_ato(HIPOTECA_SA)
    assert (d.credor, d.credor_confianca) == ("BANCO EXEMPLO S.A.", "alta")


def test_labelled_fiduciary_creditor():
    d = extrair_detalhes_ato(AF_ROTULADA)
    assert (d.credor, d.credor_confianca) == ("CAIXA ECONÔMICA EXEMPLO", "alta")


def test_ocr_lowercase_creditor():
    assert extrair_detalhes_ato(MINUSCULAS_OCR).credor == "banco ficticio s/a"


def test_only_hipoteca_and_af_have_a_creditor():
    assert extrair_detalhes_ato(PENHORA).credor is None
    assert extrair_detalhes_ato(DACAO).credor is None


# ─── instrumento ──────────────────────────────────────────────────────────


def test_notarial_deed_fully_read():
    d = extrair_detalhes_ato(ESCRITURA_COMPLETA)
    assert d.instrumento == Instrumento(
        tipo="Escritura Pública de Venda e Compra",
        data=date(2020, 3, 12),
        tabelionato="2º Tabelionato de Notas",
        livro="100",
        folhas="20",
        cidade="Cotia",
    )
    assert d.instrumento_confianca == "alta"


def test_tabeliao_city_with_uf_and_page_range():
    i = extrair_detalhes_ato(DOACAO_COM_USUFRUTO).instrumento
    assert i == Instrumento(
        tipo="Escritura de doação",
        data=date(2019, 8, 2),
        tabelionato="15º Tabelião de Notas",
        livro="3.210",
        folhas="101/104",
        cidade="São Paulo",
    )


def test_private_instrument_needs_no_tabelionato():
    d = extrair_detalhes_ato(AF_ROTULADA)
    assert d.instrumento == Instrumento(tipo="instrumento particular", data=date(2020, 3, 5))
    assert d.instrumento_confianca == "alta"


def test_judicial_instruments():
    assert extrair_detalhes_ato(PARTILHA).instrumento == Instrumento(
        tipo="Formal de Partilha", data=date(2010, 10, 10)
    )
    assert extrair_detalhes_ato(ARREMATACAO).instrumento.tipo == "Carta de Arrematação"
    assert extrair_detalhes_ato(PENHORA).instrumento.data == date(2021, 10, 1)


def test_no_instrument_is_none():
    d = extrair_detalhes_ato(CV_SIMPLES)
    assert (d.instrumento, d.instrumento_confianca) == (None, "nenhuma")


# ─── atos referidos ───────────────────────────────────────────────────────


def test_a_cancellation_cites_its_object():
    d = extrair_detalhes_ato(CANCELAMENTO)
    assert d.atos_referidos == (AtoReferido("R", 2),)
    assert d.atos_referidos_confianca == "alta"
    assert extrair_detalhes_ato(LEVANTAMENTO).atos_referidos == (AtoReferido("AV", 8),)


def test_look_alikes_and_other_matriculas_are_not_citations():
    d = extrair_detalhes_ato(CITACOES)
    # Quadra R-1, Av. 9 de Julho, R-3/1.234 (another matrícula) excluded;
    # the act's own R-1 header is not a citation of itself.
    assert d.atos_referidos == (AtoReferido("AV", 2), AtoReferido("R", 4))
    assert d.atos_referidos_confianca == "baixa"  # "registro nº 4" is verbal


# ─── document helpers ─────────────────────────────────────────────────────


def test_document_helpers():
    assert formatar_cpf_cnpj("12345678909") == "123.456.789-09"
    assert formatar_cpf_cnpj("11222333000181") == "11.222.333/0001-81"
    assert formatar_cpf_cnpj("123") is None
    assert cpf_cnpj_valido("123.456.789-09")
    assert cpf_cnpj_valido("11.222.333/0001-81")
    assert not cpf_cnpj_valido("11.222.333/0001-82")
    assert not cpf_cnpj_valido("000.000.000-00")


# ─── frase_titulo_aquisitivo ──────────────────────────────────────────────


def test_the_title_phrase_of_a_notarial_deed():
    d = extrair_detalhes_ato(ESCRITURA_COMPLETA)
    assert frase_titulo_aquisitivo(d.instrumento, kind="R", numero=3) == (
        "por Escritura Pública de Venda e Compra lavrada em 12/03/2020 no "
        "2º Tabelionato de Notas de Cotia, Livro 100, fls. 20, registrada sob o R-3"
    )


def test_the_title_phrase_agrees_in_gender_and_omits_what_is_missing():
    assert frase_titulo_aquisitivo(
        Instrumento(tipo="Instrumento particular", data=date(2015, 6, 5)), kind="R", numero=5
    ) == "por Instrumento particular datado de 05/06/2015, registrado sob o R-5"
    assert frase_titulo_aquisitivo(
        Instrumento(tipo="Formal de Partilha", data=date(2010, 10, 10)), kind="R", numero=5
    ) == "por Formal de Partilha expedido em 10/10/2010, registrado sob o R-5"
    assert frase_titulo_aquisitivo(
        Instrumento(tipo="Carta de Arrematação"), kind="AV", numero=7
    ) == "por Carta de Arrematação, averbada sob a AV-7"


def test_no_instrument_type_means_no_phrase():
    assert frase_titulo_aquisitivo(None, kind="R", numero=1) is None
    assert frase_titulo_aquisitivo(Instrumento(data=date(2020, 1, 1)), kind="R", numero=1) is None
    with pytest.raises(ValueError):
        frase_titulo_aquisitivo(Instrumento(tipo="Escritura"), kind="abertura", numero=0)

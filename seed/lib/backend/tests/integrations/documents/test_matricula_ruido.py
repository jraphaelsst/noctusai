"""`detectar_ruido` / `subtrair_ruido` — page furniture as offsets.

🔴 WHAT THESE PIN
------------------
1. Header/footer blocks detected on both fixture providers, offsets slicing
   back to exactly the furniture (nothing more, nothing less).
2. THE REGRESSION THAT MATTERS: a genuine registry signature line repeating
   mid-page is never mistaken for furniture — position, not repetition, is
   the signal (see `matricula_ruido.py`'s module docstring).
3. `subtrair_ruido` over an act span that straddles a real page break —
   `PROVIDER_A`'s `AV-2` act — leaves the registry text (including the
   signature line inside it) and removes only page 1's footer + page 2's
   header.
4. A single-page document never yields noise.
5. Every offset is valid against the joined text it was computed from.

Two fixture providers, modelled on real ONR/registry-viewer certidão exports
(structure only — every name, number and address below is invented).
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.matricula_atos import (
    segment_matricula_atos,
)
from noctusai_lib.integrations.documents.matricula_ruido import (
    RuidoSpan,
    detectar_ruido,
    subtrair_ruido,
)
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)
from noctusai_lib.integrations.documents.types import TextSource

# ─── Provider A — signed ONR certidão, 3 pages ────────────────────────────

_ASSINATURA = "O Oficial, ________ João da Silva Exemplo."

_A_PAGINA_1 = [
    "================================================",
    "Valide aqui este documento",
    "Mat. 3917 - Página 1/3 - PROT. 445566",
    "CNM: 12345678",
    "LIVRO Nº 2 - REGISTRO",
    "GERAL",
    "",
    "—matrícula—",
    "3917",
    "—ficha—",
    "01",
    "OFICIAL DE REGISTRO DE IMÓVEIS",
    "DA COMARCA DE SÃO PAULO/SP",
    "",
    "IMÓVEL: Um lote de terreno sob o nº 7 da quadra B, situado na Rua das "
    "Acácias Inventadas, com a área de 250,00m².",
    "CADASTRO MUNICIPAL: Contribuinte nº 123.456.7-8.",
    "PROPRIETÁRIOS: FULANO DE TESTE EXEMPLAR, brasileiro, casado.",
    "REGISTRO ANTERIOR: Matrícula nº 2.001 deste registro.",
    "",
    "R-1/3917 - Em 10 de março de 2001, foi registrada a venda e compra do "
    "imóvel acima descrito, tendo como transmitente FULANO DE TESTE EXEMPLAR "
    "e como adquirente BELTRANA MODELO DE SOUZA, pelo valor de R$ 150.000,00, "
    f"conforme instrumento particular datado de 05 de março de 2001. {_ASSINATURA}",
    "",
    "AV-2/3917 - Em 05 de abril de 2002, foi averbada a construção de uma "
    "edificação residencial no imóvel supra descrito, conforme habite-se "
    "expedido pela Prefeitura, iniciando-se aqui um novo parágrafo que "
    "(continua no verso)",
    "",
    "Valide este documento clicando no link a seguir: "
    "https://ridigital.org.br/validar/998877",
    "Documento gerado oficialmente pelo Registro de Imóveis via www.ridigital.org.br",
    "ridigital | Todos os Registros de Imóveis do Brasil em um só lugar",
]

_A_PAGINA_2 = [
    "================================================",
    "Valide aqui este documento",
    "Mat. 3917 - Página 2/3 - PROT. 445566",
    "CNM: 12345678",
    "LIVRO Nº 2 - REGISTRO",
    "GERAL",
    "",
    "descrita no habite-se, com área construída de 180,00m², averbando-se "
    "ainda a numeração predial definitiva atribuída pela municipalidade ao "
    f"imóvel objeto desta matrícula. {_ASSINATURA}",
    "",
    "R-3/3917 - Em 12 de julho de 2005, foi registrada a instituição de "
    "hipoteca em favor do Banco Fictício S/A, no valor de R$ 80.000,00, "
    f"garantindo financiamento imobiliário concedido ao proprietário. {_ASSINATURA}",
    "",
    "Valide este documento clicando no link a seguir: "
    "https://ridigital.org.br/validar/112233",
    "Documento gerado oficialmente pelo Registro de Imóveis via www.ridigital.org.br",
    "ridigital | Todos os Registros de Imóveis do Brasil em um só lugar",
]

_A_PAGINA_3 = [
    "CERTIDÃO DIGITAL",
    "",
    "CERTIFICO E DOU FÉ que a presente é cópia fiel do teor da matrícula "
    "nº 3.917 do Livro nº 2 - Registro Geral desta Serventia, extraída "
    "eletronicamente nesta data, nada mais constando que prejudique a "
    "validade da presente certidão.",
    "",
    "| Emolumentos | Valor |",
    "| --- | --- |",
    "| Certidão | R$ 45,90 |",
    "| Total | R$ 45,90 |",
    "",
    "Selo Digital TJSP: AB12.CD34.EF56.GH78",
    "",
    "Valide este documento clicando no link a seguir: "
    "https://ridigital.org.br/validar/556677",
    "Documento gerado oficialmente pelo Registro de Imóveis via www.ridigital.org.br",
    "ridigital | Todos os Registros de Imóveis do Brasil em um só lugar",
]


def _pagina(numero: int, linhas: list[str]) -> TranscribedPage:
    return TranscribedPage(
        number=numero, text="\n".join(linhas), source=TextSource.TEXT_LAYER
    )


PROVIDER_A = (
    _pagina(1, _A_PAGINA_1),
    _pagina(2, _A_PAGINA_2),
    _pagina(3, _A_PAGINA_3),
)

# ─── Provider B — registry-viewer export, 4 pages ─────────────────────────


def _b_cabecalho(ficha: str) -> list[str]:
    return [
        "CNM: 87654321",
        "LIVRO Nº 2 - REGISTRO GERAL",
        "matrícula",
        "9988",
        "ficha",
        ficha,
        "OFICIAL DE REGISTRO DE IMÓVEIS",
        "DA COMARCA DE CAMPINAS/SP",
        "SOLICITADO POR: MARIA EXEMPLO DA CRUZ - CPF/CNPJ: ***.111.222-** - "
        "DATA: 12/06/2026 10:15:32",
    ]


_B_PAGINA_1 = _b_cabecalho("01") + [
    "",
    "IMÓVEL: Um apartamento nº 42, localizado no 4º andar do Edifício "
    "Modelo, situado na Avenida Fictícia, 500, com área privativa de 85,00m².",
    "CADASTRO MUNICIPAL: Contribuinte nº 998.877-6.",
    "REGISTRO ANTERIOR: Matrícula nº 5.500 deste registro.",
    "",
    "R-1/9988 - Em 20 de janeiro de 2010, foi registrada a instituição de "
    "condomínio do edifício acima referido, conforme especificações "
    "constantes do memorial de incorporação arquivado nesta serventia sob "
    "nº 33.221.",
]

_B_PAGINA_2 = _b_cabecalho("02") + [
    "",
    "continuação do R-1, com a descrição das frações ideais atribuídas a "
    "cada unidade autônoma do condomínio, na forma da convenção condominial "
    "registrada sob o nº 33.222.",
    "",
    "R-2/9988 - Em 15 de março de 2012, foi registrada a compra e venda da "
    "unidade acima descrita, tendo como transmitente a CONSTRUTORA EXEMPLO "
    "LTDA e como adquirente CARLOS AMOSTRA PEREIRA, pelo valor de "
    "R$ 320.000,00.",
]

_B_PAGINA_3 = _b_cabecalho("03") + [
    "",
    "AV-3/9988 - Em 02 de maio de 2015, foi averbada a quitação integral do "
    "financiamento imobiliário concedido ao adquirente, mediante "
    "apresentação de carta de quitação do agente financeiro. O Oficial "
    "Substituto, ________ Ana Paula Exemplo.",
]

_B_PAGINA_4 = _b_cabecalho("04") + [
    "",
    "AV-4/9988 - Em 10 de agosto de 2018, foi averbada a alteração de "
    "estado civil do proprietário, de solteiro para casado, conforme "
    "certidão de casamento apresentada. O Oficial Substituto, ________ Ana "
    "Paula Exemplo.",
]

PROVIDER_B = (
    _pagina(1, _B_PAGINA_1),
    _pagina(2, _B_PAGINA_2),
    _pagina(3, _B_PAGINA_3),
    _pagina(4, _B_PAGINA_4),
)


def _texto(pages) -> str:
    return Transcription(pages=tuple(pages)).text


def _por_kind_e_pagina(spans, kind, pagina):
    return [s for s in spans if s.kind == kind and pagina in s.paginas]


class TestCabecalhoERodape:
    def test_provider_a_header_on_pages_1_and_2_not_3(self):
        texto = _texto(PROVIDER_A)
        spans = detectar_ruido(PROVIDER_A)
        cabecalhos = [s for s in spans if s.kind == "cabecalho_pagina"]
        assert len(cabecalhos) == 2
        assert {s.paginas for s in cabecalhos} == {(1, 2)}
        for s in cabecalhos:
            assert texto[s.start : s.end].startswith("====")
            assert texto[s.start : s.end].rstrip().endswith("GERAL")
        # Page 3's own leading line never shows up as a header span.
        assert not _por_kind_e_pagina(spans, "cabecalho_pagina", 3)

    def test_provider_a_footer_on_all_three_pages(self):
        texto = _texto(PROVIDER_A)
        spans = detectar_ruido(PROVIDER_A)
        rodapes = [s for s in spans if s.kind == "rodape_pagina"]
        assert len(rodapes) == 3
        assert {s.paginas for s in rodapes} == {(1, 2, 3)}
        for s in rodapes:
            bloco = texto[s.start : s.end]
            assert bloco.startswith("Valide este documento clicando")
            assert bloco.rstrip().endswith(
                "ridigital | Todos os Registros de Imóveis do Brasil em um só lugar"
            )

    def test_provider_b_header_detected_on_all_four_pages(self):
        spans = detectar_ruido(PROVIDER_B)
        cabecalhos = [s for s in spans if s.kind == "cabecalho_pagina"]
        assert len(cabecalhos) == 4
        assert {s.paginas for s in cabecalhos} == {(1, 2, 3, 4)}
        texto = _texto(PROVIDER_B)
        for s in cabecalhos:
            assert texto[s.start : s.end].startswith("CNM:")

    def test_signature_line_repeating_three_times_is_not_noise(self):
        texto = _texto(PROVIDER_A)
        assert texto.count(_ASSINATURA) == 3  # sanity: the fixture is real
        spans = detectar_ruido(PROVIDER_A)
        for s in spans:
            assert "João da Silva Exemplo" not in texto[s.start : s.end]

    def test_spans_sorted_and_non_overlapping(self):
        spans = detectar_ruido(PROVIDER_A) + detectar_ruido(PROVIDER_B)
        for grupo in (detectar_ruido(PROVIDER_A), detectar_ruido(PROVIDER_B)):
            starts = [s.start for s in grupo]
            assert starts == sorted(starts)
            for a, b in zip(grupo, grupo[1:]):
                assert a.end <= b.start


class TestSemPaginaSuficiente:
    def test_single_page_returns_empty(self):
        pagina = _pagina(1, ["MATRICULA 1", "Abertura.", "R-1 - venda."])
        assert detectar_ruido((pagina,)) == ()

    def test_one_real_page_plus_a_blank_page_returns_empty(self):
        real = _pagina(1, ["MATRICULA 1", "Abertura.", "R-1 - venda."])
        vazia = TranscribedPage(number=2, text="", source=TextSource.TEXT_LAYER)
        assert detectar_ruido((real, vazia)) == ()


class TestSubtrairRuidoUnitario:
    def test_no_overlap_returns_the_whole_span_unchanged(self):
        ruido = (RuidoSpan(start=100, end=120, kind="rodape_pagina", paginas=(1,)),)
        assert subtrair_ruido(0, 50, ruido) == ((0, 50),)

    def test_ruido_fully_inside_splits_around_it(self):
        ruido = (RuidoSpan(start=10, end=20, kind="cabecalho_pagina", paginas=(1, 2)),)
        assert subtrair_ruido(0, 30, ruido) == ((0, 10), (20, 30))

    def test_ruido_covering_the_whole_span_yields_nothing(self):
        ruido = (RuidoSpan(start=0, end=30, kind="cabecalho_pagina", paginas=(1, 2)),)
        assert subtrair_ruido(0, 30, ruido) == ()

    def test_overlapping_ruido_entries_are_merged(self):
        ruido = (
            RuidoSpan(start=5, end=15, kind="cabecalho_pagina", paginas=(1,)),
            RuidoSpan(start=10, end=20, kind="cabecalho_pagina", paginas=(2,)),
        )
        assert subtrair_ruido(0, 30, ruido) == ((0, 5), (20, 30))

    def test_ruido_outside_the_span_is_ignored(self):
        ruido = (RuidoSpan(start=-50, end=-10, kind="rodape_pagina", paginas=(1,)),)
        assert subtrair_ruido(0, 30, ruido) == ((0, 30),)


class TestSubtrairRuidoAtoQueAtravessaPagina:
    def test_av2_act_loses_only_the_page1_footer_and_page2_header(self):
        texto = _texto(PROVIDER_A)
        ruido = detectar_ruido(PROVIDER_A)
        atos = segment_matricula_atos(texto)
        av2 = next(a for a in atos if a.kind == "AV" and a.numero == 2)

        # The fixture is built so the act genuinely straddles the join: it
        # must contain page 1's footer and page 2's header verbatim before
        # subtraction, proving this test exercises the real problem.
        bruto = av2.quote(texto)
        assert "ridigital | Todos os Registros" in bruto
        assert "CNM: 12345678" in bruto

        partes = subtrair_ruido(av2.start, av2.end, ruido)
        limpo = "".join(texto[s:e] for s, e in partes)

        assert "ridigital" not in limpo
        assert "Valide este documento" not in limpo
        assert "CNM: 12345678" not in limpo
        assert "LIVRO Nº 2 - REGISTRO" not in limpo
        assert "Mat. 3917 - Página 2/3" not in limpo

        # Real registry content — including the signature line inside the
        # straddling act — survives untouched.
        assert "averbada a construção" in limpo
        assert "descrita no habite-se" in limpo
        assert _ASSINATURA in limpo

    def test_subtracted_parts_are_ordered_and_within_the_act(self):
        texto = _texto(PROVIDER_A)
        ruido = detectar_ruido(PROVIDER_A)
        atos = segment_matricula_atos(texto)
        av2 = next(a for a in atos if a.kind == "AV" and a.numero == 2)
        partes = subtrair_ruido(av2.start, av2.end, ruido)
        assert partes  # something real remains between the furniture
        for s, e in partes:
            assert av2.start <= s < e <= av2.end
        for (_, fim), (inicio, _) in zip(partes, partes[1:]):
            assert fim < inicio


class TestOffsetsSaoValidos:
    def test_every_span_is_a_valid_slice(self):
        for pages in (PROVIDER_A, PROVIDER_B):
            texto = _texto(pages)
            for s in detectar_ruido(pages):
                assert 0 <= s.start <= s.end <= len(texto)

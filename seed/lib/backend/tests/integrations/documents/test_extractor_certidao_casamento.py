"""`LadderIdentityExtractor.extract` against a REAL certidão de casamento's
structure — a sibling of `test_extractor.py` (that file already trips
`test_seam_guard` on any edit via its own pre-existing `patch(...)` calls;
this file exists so the fixes below get end-to-end coverage without
touching it).

`CERTIDAO_ANONIMIZADA` mirrors, verbatim in STRUCTURE and WORDING, a real
client's cartório certidão de casamento that a live production run put
through the fixed ladder (Anthropic vision, complete/accurate OCR — 4,611
chars) and got back a `LadderIdentityExtractor.extract` result carrying
ONLY `data_casamento`, `data_emissao`, and a FABRICATED `rg_orgao`. Every
name, CPF, date and registry number below is invented; only the document's
shape and wording are faithful — see the dispatch brief for the full
provenance note. `FakeIdentityExtractor`'s scripted married-reading is
`test_civil_status.py`'s `TestCivilStatusWiring`; this file is the
divorced-with-two-titulars case that scripted fixture does not cover.

🔴 THE FIXTURE'S TAIL MATTERS AS MUCH AS ITS HEAD
---------------------------------------------------
The trailing "DETALHAMENTO DA MATRÍCULA" book-type legend below is not
decorative — an EARLIER, truncated version of this fixture (missing that
legend) let `estado_civil` pass while the real document still failed,
because the legend is exactly what breaks it (see
`test_civil_status.py`'s `TestEstadoCivilDetalhamentoMatriculaLegendIsNotAnEvent`
for the isolated bare-parser regression). Do not trim it back.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import ExtractionConfidence
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

CERTIDAO_ANONIMIZADA = """
[documento PDF digitalizado] Selo Digital nº: 1155682PV000000027069722Z

REPÚBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS

CERTIDÃO DE CASAMENTO

NOMES

ALMIR TEIXEIRA DA COSTA

CPF
303.102.653-55

MARIANA PELLEGRINI RANGEL

CPF
478.982.096-30

MATRÍCULA
115568 01 55 2011 2 00198 278 0059433-91

NOMES COMPLETOS DE SOLTEIRO, DATAS DE NASCIMENTO, NATURALIDADE, NACIONALIDADE E FILIAÇÕES DOS CÔNJUGES

ALMIR TEIXEIRA DA COSTA, nascido no dia quatro de outubro de mil novecentos e sessenta e um (04/10/1961), em Duque de Caxias, RJ, de nacionalidade brasileira, filho de PEDRO TEIXEIRA DA COSTA e de MARIA JACIRA MENDES DA COSTA.
MARIANA PELLEGRINI RANGEL, nascida no dia vinte de abril de mil novecentos e sessenta e quatro (20/04/1964), no Subdistrito Aclimação, São Paulo, SP, de nacionalidade brasileira, filha de EMILIO RANGEL e de ANGELINA NUNES RANGEL.

DATA DE REGISTRO DO CASAMENTO POR EXTENSO
TRINTA DE JULHO DE DOIS MIL E ONZE

DIA
30

MÊS
07

ANO
2011

REGIME DE BENS DO CASAMENTO
SEPARAÇÃO ABSOLUTA DE BENS, CONFORME ESCRITURA DE PACTO ANTENUPCIAL LAVRADA NO TABELIONATO LOCAL, LIVRO 659, PÁGINAS 002, 003 E 004, DATADA DE 01/07/2011

NOME QUE CADA UM DOS CÔNJUGES PASSOU A UTILIZAR (QUANDO HOUVER ALTERAÇÃO)
ELE: Continua a usar o MESMO NOME.
ELA: Continua a usar o MESMO NOME.

AVERBAÇÕES/ANOTAÇÕES À ACRESCER
Casamento registrado sob n° 000059433, Folhas 278 do Livro B - 0198. Nada consta. A PRESENTE CERTIDÃO ENVOLVE ELEMENTOS DE AVERBAÇÃO À MARGEM DO TERMO. VIDE VERSO.

O conteúdo da certidão é verdadeiro. Dou fé.
CARAPICUÍBA, 17 de agosto de 2022

AVERBAÇÕES/ANOTAÇÕES

AVERBAÇÃO: CERTIFICO e dou fé que, através da ESCRITURA PÚBLICA de Divórcio Consensual, lavrada aos 08/07/2022, no Livro N° 310, Páginas 373/376, do Tabelião de Notas do Distrito Caucaia do Alto, Comarca de Cotia/SP, foi realizado o DIVÓRCIO CONSENSUAL do casal ALMIR TEIXEIRA DA COSTA e MARIANA PELLEGRINI RANGEL. Não houve alteração no nome das partes. O referido é verdade e dou fé. Carapicuíba, 17/08/2022.

DETALHAMENTO DA MATRÍCULA
115568 01 55 2011 2 00198 278 0059433-91
Onde:
e (1) Tipo do livro, sendo:
1. Livro A (Nascimento)
2. Livro B (Casamento)
3. Livro B Auxiliar (Registro de casamento religioso para fins civis)
4. Livro C (Obito)
5. Livro C Auxiliar (Registro de Natimortos)
6. Livro D (Registro de Proclamas)
7. Livro E (Demais atos relativos ao Registro Civil)
"""


class _StubResolved:
    def __init__(self, text="", error=None, error_message=None):
        self.text, self.error, self.error_message = text, error, error_message


class _StubResolver:
    """Dependency injection standing in for the media resolver's vision
    rung — never a patch of our own code. Same pattern
    `test_civil_status.py`'s `TestCivilStatusWiring` already uses."""

    def __init__(self, resolved=None):
        self._resolved = resolved or _StubResolved(text="")

    async def resolve(self, media):
        return self._resolved


class TestRealCertidaoDeCasamentoEndToEnd:
    """The four defects, verified together through the full `extract()`
    call — not just at each bare-parser level."""

    @pytest.mark.asyncio
    async def test_regime_bens_reads_separacao_absoluta(self):
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.regime_bens == "separacao_total"
        assert out.persistable_regime_bens is True

    @pytest.mark.asyncio
    async def test_estado_civil_reads_divorciado_despite_the_nada_consta_disclaimer(
        self,
    ):
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.estado_civil == "divorciado"
        assert out.persistable_estado_civil is True

    @pytest.mark.asyncio
    async def test_rg_orgao_is_never_fabricated_from_a_jurisdiction_mention(self):
        """The document carries no RG at all — `Comarca de Cotia/SP` (the
        AVERBAÇÃO's own jurisdiction) must not surface as a fabricated
        issuer."""
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.rg is None
        assert out.rg_orgao is None
        assert out.rg_orgao_confianca is ExtractionConfidence.NENHUMA

    @pytest.mark.asyncio
    async def test_two_titulares_are_named_not_silently_dropped(self):
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.nome is None
        assert out.cpf is None
        # A NOTICE, not a failure: the couple-level facts on the same result
        # must survive for the consumer to persist them.
        assert out.error is None
        assert out.aviso == "titulares_multiplos"
        assert out.aviso_mensagem is not None
        assert "nome" in out.aviso_mensagem
        assert "cpf" in out.aviso_mensagem
        assert out.estado_civil == "divorciado"

    @pytest.mark.asyncio
    async def test_dates_and_source_are_unaffected_by_any_of_the_above(self):
        """The pre-existing, already-correct behaviour must survive."""
        from datetime import date

        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.data_casamento == date(2011, 7, 30)
        assert out.data_emissao == date(2022, 8, 17)


class TestRgOrgaoNeverTravelsWithoutRg:
    """The compositional coherence gate in `real.py`, isolated from the
    certidão fixture — any document where `rg` is absent must never carry
    an `rg_orgao`, regardless of what shape-only match `find_rg_orgao`
    makes on its own."""

    @pytest.mark.asyncio
    async def test_a_jurisdiction_mention_with_no_rg_number_never_surfaces(self):
        resolver = _StubResolver(
            _StubResolved(text="COMARCA DE COTIA/SP\nNENHUM RG NESTE DOCUMENTO\n")
        )
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.rg is None
        assert out.rg_orgao is None

    @pytest.mark.asyncio
    async def test_a_real_rg_with_its_own_issuer_still_travels_together(self):
        resolver = _StubResolver(
            _StubResolved(text="REGISTRO GERAL 12.345.678-9 SSP/SP")
        )
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.rg == "12.345.678-9"
        assert out.rg_orgao == "SSP/SP"


class TestTitularesMultiplosDoesNotFireOnOrdinaryDocuments:
    @pytest.mark.asyncio
    async def test_a_single_holder_document_carries_no_error(self):
        resolver = _StubResolver(
            _StubResolved(text="NOME: JOAO PEREIRA DA SILVA\nCPF: 412.954.238-98\n")
        )
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.nome == "JOAO PEREIRA DA SILVA"
        assert out.cpf == "412.954.238-98"
        assert out.error is None
        assert out.error_message is None

    @pytest.mark.asyncio
    async def test_a_document_with_neither_name_nor_cpf_is_not_a_conflict(self):
        """Ordinary absence must not be reported as `titulares_multiplos` —
        only a genuine multi-holder ambiguity may set that error."""
        resolver = _StubResolver(_StubResolved(text="MATRICULA 123456\n"))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.nome is None
        assert out.cpf is None
        assert out.error is None



class TestTitularHintSelectsTheCardHolder:
    """The caller knows whose card the certidão was uploaded to."""

    @pytest.mark.asyncio
    async def test_hinted_cpf_selects_that_spouse(self):
        from noctusai_lib.integrations.documents import TitularEsperado

        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x",
            mimetype="image/png",
            titular=TitularEsperado(cpf="47898209630"),
        )
        assert out.cpf == "478.982.096-30"
        assert out.cpf_confianca is ExtractionConfidence.ALTA

    @pytest.mark.asyncio
    async def test_hinted_name_selects_the_printed_spelling(self):
        from noctusai_lib.integrations.documents import TitularEsperado

        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x",
            mimetype="image/png",
            titular=TitularEsperado(nome="Mariana Pellegrini Rangel", cpf="478.982.096-30"),
        )
        assert out.nome == "MARIANA PELLEGRINI RANGEL"
        # Vision read: the hint picked WHICH name, not how well it was read.
        assert out.nome_confianca is not ExtractionConfidence.ALTA
        assert out.aviso is None

    @pytest.mark.asyncio
    async def test_a_hint_matching_nobody_changes_nothing(self):
        from noctusai_lib.integrations.documents import TitularEsperado

        resolver = _StubResolver(_StubResolved(text=CERTIDAO_ANONIMIZADA))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x",
            mimetype="image/png",
            titular=TitularEsperado(nome="FULANO DE TAL", cpf="412.954.238-98"),
        )
        assert out.nome is None
        assert out.cpf is None
        assert out.aviso == "titulares_multiplos"

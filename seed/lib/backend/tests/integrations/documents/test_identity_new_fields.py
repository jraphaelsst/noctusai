"""The identity-extraction fields added for the contract gate (2026-09-22):
profissão, endereço, both spouses of a certidão de casamento, CIN "Sexo",
the `m`/`f` canonicaliser, and the text-layer -> vision fallthrough.

Every document shape below mirrors a real document's STRUCTURE and wording
(CIN digital PDF text layer, old SSP-SP RG, CNH, a two-spouse certidão de
casamento, Enel / Sabesp / Vivo bills); every name, number and address is
invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    canonical_gender,
    find_conjuges,
    find_endereco,
    find_gender,
    find_profissao,
    find_profissoes,
)
from noctusai_lib.integrations.documents.gender import FEMININO, MASCULINO, _mrz_check
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TextSource, TitularEsperado

# ─── Document shapes ──────────────────────────────────────────────────────

CIN_TEXTO = """REPÚBLICA FEDERATIVA DO BRASIL
CARTEIRA DE IDENTIDADE
Nome / Name
TAUANE GONÇALVES DIAS
Nome Social / Social Name

Sexo / Sex
F
Nacionalidade / Nationality
BRA
Data de Nascimento / Date of Birth
14/03/1994
CPF
448.864.938-66
Órgão Expedidor / Issuing Authority
IIGDR/SP
"""

CIN_TABELA = """CARTEIRA DE IDENTIDADE
Nome / Name
TAUANE GONÇALVES DIAS
Sexo / Sex    Nacionalidade / Nationality    Data de Nascimento / Date of Birth
F    BRA    14/03/1994
"""

RG_ANTIGO = """REPÚBLICA FEDERATIVA DO BRASIL
ESTADO DE SÃO PAULO
SECRETARIA DA SEGURANÇA PÚBLICA
INSTITUTO DE IDENTIFICAÇÃO RICARDO GUMBLETON DAUNT
REGISTRO GERAL 52.179.965-X   DATA DE EXPEDIÇÃO 10/05/2011
NOME JOÃO CARLOS PEREIRA
FILIAÇÃO JOSÉ PEREIRA
MARIA DA SILVA PEREIRA
NATURALIDADE SÃO PAULO - SP   DATA DE NASCIMENTO 12/05/1980
DOC. ORIGEM SÃO PAULO - SP CN:LV.A123 FLS.45 N.6789
CPF 412.954.238-98
"""

CNH = """REPÚBLICA FEDERATIVA DO BRASIL
MINISTÉRIO DA INFRAESTRUTURA
DEPARTAMENTO NACIONAL DE TRÂNSITO
CARTEIRA NACIONAL DE HABILITAÇÃO
NOME
MARIANA PELLEGRINI RANGEL
DOC. IDENTIDADE / ÓRG. EMISSOR / UF
23.456.789-0 SSP SP
CPF
478.982.096-30
DATA NASCIMENTO
20/04/1964
SEXO
F
"""

CERTIDAO_DOIS_CONJUGES = """REPÚBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO

NOMES

ALMIR TEIXEIRA DA COSTA

CPF
303.102.653-55

MARIANA PELLEGRINI RANGEL

CPF
478.982.096-30

NOMES COMPLETOS DE SOLTEIRO, DATAS DE NASCIMENTO, NATURALIDADE, NACIONALIDADE E FILIAÇÕES DOS CÔNJUGES

ALMIR TEIXEIRA DA COSTA, de profissão comerciante, nascido no dia quatro de outubro de mil novecentos e sessenta e um (04/10/1961), em Duque de Caxias, RJ, de nacionalidade brasileira, filho de PEDRO TEIXEIRA DA COSTA e de MARIA JACIRA MENDES DA COSTA.
MARIANA PELLEGRINI RANGEL, de profissão professora, nascida no dia vinte de abril de mil novecentos e sessenta e quatro (20/04/1964), no Subdistrito Aclimação, São Paulo, SP, de nacionalidade brasileira, filha de EMILIO RANGEL e de ANGELINA NUNES RANGEL.

DATA DE REGISTRO DO CASAMENTO POR EXTENSO
TRINTA DE JULHO DE DOIS MIL E ONZE

REGIME DE BENS DO CASAMENTO
COMUNHÃO PARCIAL DE BENS

AVERBAÇÕES/ANOTAÇÕES À ACRESCER
Nada consta.

O conteúdo da certidão é verdadeiro. Dou fé.
CARAPICUÍBA, 17 de agosto de 2022
"""

#: Some certidão de casamento layouts state the "nome que passou a adotar"
#: clause with the value under the PRONOUN (`Ele:` / `Ela:`) instead of
#: `NOME` — `name._PRONOUN_NAME_LABELS`. This layout carries NO `NOMES`/`CPF`
#: interleaved header at all (unlike `CERTIDAO_DOIS_CONJUGES`, a different
#: layout variant) — the pronoun clause is its only holder-naming block.
#: Every name below is invented.
CERTIDAO_NOME_ADOTADO_PRONOME = """REPÚBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO

RODRIGO MORAES ENRIQUES, CPF 412.954.238-98, de profissão engenheiro, de
nacionalidade brasileira, e TAUANE GONÇALVES DIAS, CPF 478.982.096-30, de
profissão professora, de nacionalidade brasileira, compareceram perante o
Oficial do Registro Civil e contraíram casamento sob o regime de comunhão
parcial de bens.

REGIME DE BENS DO CASAMENTO
COMUNHÃO PARCIAL DE BENS

NOME QUE CADA UM DOS CÔNJUGES PASSA A USAR EM RAZÃO DO CASAMENTO

Ele: RODRIGO MORAES ENRIQUES
Ela: TAUANE GONÇALVES DIAS ENRIQUES

O conteúdo da certidão é verdadeiro. Dou fé.
CARAPICUÍBA, 17 de agosto de 2022
"""

CONTA_LUZ_ENEL = """ENEL DISTRIBUIÇÃO SÃO PAULO
Rua Ática, 673 - Jardim Brasil - São Paulo - SP - CEP 04634-042
CNPJ 61.695.227/0001-93  Inscrição Estadual 108.042.323.117
CONTA DE ENERGIA ELÉTRICA
MARIA APARECIDA DE SOUZA
RUA DAS FLORES 123 AP 45
JARDIM PAULISTA
01234-567 SAO PAULO SP
Nº DA INSTALAÇÃO 12345678
Vencimento 10/09/2026   Total a pagar R$ 245,90
"""

CONTA_AGUA_SABESP = """SABESP - Companhia de Saneamento Básico do Estado de São Paulo
CNPJ 43.776.517/0001-80
Rua Costa Carvalho, 300 - Pinheiros - CEP 05429-900
Nome: JOSÉ CARLOS PEREIRA
Endereço: R PROF ARTUR RAMOS, 123 - APTO 12
Bairro: JARDIM PAULISTANO   CEP: 01454-011
Cidade: SÃO PAULO - SP
Fornecimento: 0123456789
"""

CONTA_TELEFONE_UMA_LINHA = """Vivo - Telefônica Brasil S.A. CNPJ 02.558.157/0001-62
Av. Engenheiro Luís Carlos Berrini, 1376 - Cidade Monções - São Paulo/SP - CEP 04571-936
ANA BEATRIZ LIMA
Alameda Santos, 1000, Conj 52 - Cerqueira César - São Paulo - SP - CEP 01418-100
"""


# ─── profissão ────────────────────────────────────────────────────────────


class TestProfissao:
    def test_labelled_form_box_on_the_next_line(self):
        assert find_profissao("PROFISSÃO\nENGENHEIRO CIVIL\nNACIONALIDADE\nBRASILEIRA") == (
            "engenheiro civil", "alta", "PROFISSAO",
        )

    def test_inline_label_stops_at_the_next_column(self):
        valor, conf, _ = find_profissao("Profissão: Advogada   Estado Civil: casada")
        assert (valor, conf) == ("advogada", "alta")

    def test_prose_de_profissao_stops_at_the_comma_and_keeps_accents(self):
        valor, _, rotulo = find_profissao("FULANO, de profissão Médico, nascido em 01/01/1970")
        assert valor == "médico"
        assert rotulo == "DE PROFISSAO"

    def test_a_parents_profissao_is_never_the_holders(self):
        assert find_profissao("PROFISSÃO DO PAI: comerciante") == (None, "nenhuma", None)

    def test_an_empty_form_box_is_not_a_value(self):
        assert find_profissao("PROFISSÃO\nNACIONALIDADE\nBRASILEIRA")[0] is None
        assert find_profissao("Profissão: não consta")[0] is None

    def test_an_unlabelled_word_is_never_a_profissao(self):
        assert find_profissao("ele era comerciante em Cotia")[0] is None

    def test_two_spouses_disagree_so_the_whole_document_read_is_absent(self):
        assert find_profissao(CERTIDAO_DOIS_CONJUGES) == (None, "nenhuma", None)
        assert [v for v, _, _ in find_profissoes(CERTIDAO_DOIS_CONJUGES)] == [
            "comerciante", "professora",
        ]


# ─── endereço ─────────────────────────────────────────────────────────────


class TestEndereco:
    def test_envelope_block_of_a_light_bill_skips_the_issuers_cep(self):
        e = find_endereco(CONTA_LUZ_ENEL)
        assert e.partes() == {
            "cep": "01234-567",
            "logradouro": "RUA DAS FLORES",
            "numero": "123",
            "complemento": "AP 45",
            "bairro": "JARDIM PAULISTA",
            "cidade": "SAO PAULO",
            "uf": "SP",
        }
        assert e.titular == "MARIA APARECIDA DE SOUZA"
        assert e.confianca == "baixa"

    def test_labelled_water_bill_reads_high_with_accents_kept(self):
        e = find_endereco(CONTA_AGUA_SABESP)
        assert e.partes() == {
            "cep": "01454-011",
            "logradouro": "R PROF ARTUR RAMOS",
            "numero": "123",
            "complemento": "APTO 12",
            "bairro": "JARDIM PAULISTANO",
            "cidade": "SÃO PAULO",
            "uf": "SP",
        }
        assert e.titular == "JOSÉ CARLOS PEREIRA"
        assert e.confianca == "alta"

    def test_single_line_address_splits_bairro_city_and_uf(self):
        e = find_endereco(CONTA_TELEFONE_UMA_LINHA)
        assert (e.cep, e.logradouro, e.numero, e.complemento) == (
            "01418-100", "Alameda Santos", "1000", "Conj 52",
        )
        assert (e.bairro, e.cidade, e.uf) == ("Cerqueira César", "São Paulo", "SP")
        assert e.titular == "ANA BEATRIZ LIMA"

    def test_no_cep_no_address(self):
        assert not find_endereco("RUA DAS FLORES 123\nJARDIM PAULISTA\nSAO PAULO SP").presente

    def test_an_issuer_only_bill_yields_nothing(self):
        texto = "ENEL\nRua Ática, 673 - Jardim Brasil - CEP 04634-042\nCNPJ 61.695.227/0001-93\n"
        assert not find_endereco(texto).presente

    def test_two_different_holder_addresses_are_ambiguous(self):
        texto = (
            "RUA A 10\nCENTRO\n01000-000 SAO PAULO SP\n\n"
            "RUA B 20\nMOEMA\n04000-000 SAO PAULO SP\n"
        )
        assert not find_endereco(texto).presente

    def test_an_identity_document_has_no_address(self):
        assert not find_endereco(RG_ANTIGO).presente
        assert not find_endereco(CIN_TEXTO).presente


# ─── gênero ──────────────────────────────────────────────────────────────


class TestGeneroCin:
    def test_cin_label_then_value_line(self):
        assert find_gender(CIN_TEXTO)[:2] == (FEMININO, "alta")

    def test_cin_table_layout_reads_as_a_suggestion(self):
        assert find_gender(CIN_TABELA)[:2] == (FEMININO, "baixa")

    def test_cnh_sexo_box(self):
        assert find_gender(CNH)[:2] == (FEMININO, "alta")

    def test_mrz_sex_letter_with_verified_check_digits(self):
        nasc, val = "940314", "340314"
        linha = f"{nasc}{_mrz_check(nasc)}F{val}{_mrz_check(val)}BRA<<<<<<<<<<<0"
        texto = f"IDBRA4488649386<<<<<<<<<<<<<<<\n{linha}\nDIAS<<TAUANE<GONCALVES<<<<<<<<"
        assert find_gender(texto) == (FEMININO, "alta", "MRZ")

    def test_mrz_with_a_broken_check_digit_is_ignored(self):
        texto = "9403140F3403141BRA<<<<<<<<<<<0"
        assert find_gender(texto) == (None, "nenhuma", None)

    def test_old_rg_prints_no_sex(self):
        assert find_gender(RG_ANTIGO)[0] is None

    @pytest.mark.parametrize(
        "bruto,esperado",
        [
            ("m", MASCULINO), ("F", FEMININO), ("Masculino", MASCULINO),
            ("feminino", FEMININO), ("MASC", MASCULINO), ("fem.", FEMININO),
            ("x", None), ("", None), (None, None),
        ],
    )
    def test_canonical_gender(self, bruto, esperado):
        assert canonical_gender(bruto) == esperado


# ─── both spouses ──────────────────────────────────────────────────────────


class TestConjuges:
    def test_each_spouse_gets_their_own_facts(self):
        a, b = find_conjuges(CERTIDAO_DOIS_CONJUGES)
        assert (a.nome, a.cpf, a.data_nascimento, a.profissao, a.genero, a.nacionalidade) == (
            "ALMIR TEIXEIRA DA COSTA", "303.102.653-55", date(1961, 10, 4),
            "comerciante", MASCULINO, "brasileiro",
        )
        assert (b.nome, b.cpf, b.data_nascimento, b.profissao, b.genero) == (
            "MARIANA PELLEGRINI RANGEL", "478.982.096-30", date(1964, 4, 20),
            "professora", FEMININO,
        )
        assert a.genero_confianca == "baixa"  # grammar, not a SEXO box

    def test_a_single_holder_document_has_no_conjuges(self):
        assert find_conjuges(RG_ANTIGO) == ()
        assert find_conjuges(CNH) == ()

    def test_the_adopted_name_clause_under_ele_ela_still_resolves_both_spouses(self):
        """🔴 THE LAYOUT VARIANT THIS TEST COVERS

        `find_name`/`find_conjuges` see ZERO candidates on a certidão whose
        only holder-naming block is this pronoun clause — `NOME` never
        matches (the value sits under `Ele`/`Ela`, not `NOME`), so
        `extracao_conjuges` would land `null` without
        `name._PRONOUN_NAME_LABELS`.
        """
        # The wife's resolved `nome` is her POST-marriage name (the value
        # under `Ela:`, including the husband's surname) — `find_conjuges`
        # matches a candidate's OWN occurrences to find its CPF/qualification
        # window, and "TAUANE GONCALVES DIAS ENRIQUES" only occurs once, at
        # the `Ela:` line, so no CPF window is found for her from this
        # layout. The name itself is what this test protects.
        a, b = find_conjuges(CERTIDAO_NOME_ADOTADO_PRONOME)
        assert (a.nome, a.cpf) == ("RODRIGO MORAES ENRIQUES", "412.954.238-98")
        assert b.nome == "TAUANE GONCALVES DIAS ENRIQUES"


# ─── the extractor ────────────────────────────────────────────────────────


class _Ladder:
    """DI stand-in for `DocumentTextLadder` — scripted per rung."""

    def __init__(self, camada: str, visao=("", TextSource.OCR, None)):
        self.camada = camada
        self.visao = visao
        self.chamadas: list[bool] = []

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        self.chamadas.append(pular_camada_texto)
        if pular_camada_texto:
            return self.visao
        return (self.camada, TextSource.TEXT_LAYER, None)


class TestExtractorFallthrough:
    @pytest.mark.asyncio
    async def test_a_text_layer_with_no_identity_field_falls_through_to_vision(self):
        ladder = _Ladder(
            "SECRETARIA DA SEGURANÇA PÚBLICA\nASSINADO DIGITALMENTE\nQR CODE",
            visao=(RG_ANTIGO, TextSource.OCR, None),
        )
        out = await LadderIdentityExtractor(ladder=ladder).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert ladder.chamadas == [False, True]
        assert out.source is TextSource.OCR
        assert out.cpf == "412.954.238-98"
        assert out.rg == "52.179.965-X"

    @pytest.mark.asyncio
    async def test_a_useful_text_layer_never_pays_for_vision(self):
        ladder = _Ladder(RG_ANTIGO)
        out = await LadderIdentityExtractor(ladder=ladder).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert ladder.chamadas == [False]
        assert out.source is TextSource.TEXT_LAYER

    @pytest.mark.asyncio
    async def test_vision_failing_after_an_empty_text_layer_is_an_error_not_sem_dados(self):
        ladder = _Ladder(
            "CABEÇALHO SEM CAMPOS",
            visao=("", TextSource.NENHUMA, ("insufficient_quota", "no credit")),
        )
        out = await LadderIdentityExtractor(ladder=ladder).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert out.error == "insufficient_quota"


class _FakeResolverCapturingMedia:
    """Stands in for `get_media_resolver(real=True, ...)` — records every
    `InboundMedia` it was asked to resolve, so a test can assert what the
    REAL `DocumentTextLadder.to_text` (not the `_Ladder` DI stand-in used
    above) actually builds when retrying."""

    def __init__(self, resposta_texto: str) -> None:
        self._resposta_texto = resposta_texto
        self.medias: list = []

    async def resolve(self, media):
        self.medias.append(media)

        class _Resolved:
            error = None
            error_message = None
            text = self._resposta_texto

        return _Resolved()


class TestForcedRetryReachesTheResolverAsForceVision:
    """`ladder.chamadas == [False, True]` above proves `pular_camada_texto`
    is set — it does NOT prove the retry ever escapes a resolver that
    independently re-derives "is this text layer substantive" and hands
    the SAME text back (the actual 2026-09-23 `sem_dados` root cause on a
    "CNH Digital" PDF). This exercises the REAL `DocumentTextLadder`, not
    the `_Ladder` fake, end to end through `LadderIdentityExtractor`."""

    @pytest.mark.asyncio
    async def test_pular_camada_texto_sets_force_vision_on_the_resolved_media(self):
        fitz = pytest.importorskip("fitz")
        from noctusai_lib.integrations.documents.ladder import DocumentTextLadder

        # A REAL, `classify_pdf_text_layer`-substantive text layer (well
        # above the char floor, no provenance-stamp match) that carries
        # NONE of the identity fields — mirrors the "CNH Digital" card-
        # cover boilerplate this fix was measured against, without any
        # real document or PII.
        doc = fitz.open()
        page = doc.new_page()
        texto = "TEXTO DIGITAL SEM CAMPOS DE IDENTIDADE. " * 10
        page.insert_textbox(fitz.Rect(20, 20, 500, 500), texto, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()

        resolver = _FakeResolverCapturingMedia(RG_ANTIGO)
        ladder = DocumentTextLadder(resolver=resolver)
        extractor = LadderIdentityExtractor(ladder=ladder)

        out = await extractor.extract(pdf_bytes, mimetype="application/pdf")

        assert out.cpf == "412.954.238-98"  # the vision answer actually landed
        # The rung-1 text layer never touches the resolver at all (it is
        # non-empty, so `to_text` returns without calling `.resolve`) — the
        # ONE call recorded here is the extractor's forced retry.
        assert len(resolver.medias) == 1
        assert resolver.medias[0].force_vision is True


class TestExtractorNewFields:
    @pytest.mark.asyncio
    async def test_profissao_and_address_ride_on_the_result(self):
        out = await LadderIdentityExtractor(ladder=_Ladder(CONTA_AGUA_SABESP)).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert out.endereco is not None
        assert out.endereco.cep == "01454-011"

    @pytest.mark.asyncio
    async def test_cin_sex_is_read(self):
        out = await LadderIdentityExtractor(ladder=_Ladder(CIN_TEXTO)).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert out.genero == FEMININO
        assert out.persistable_genero

    @pytest.mark.asyncio
    async def test_titular_hint_selects_a_spouse_and_carries_their_per_person_facts(self):
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_DOIS_CONJUGES)).extract(
            b"%PDF", mimetype="application/pdf",
            titular=TitularEsperado(nome="Mariana Pellegrini Rangel"),
        )
        assert out.nome == "MARIANA PELLEGRINI RANGEL"
        assert out.cpf == "478.982.096-30"
        assert out.data_nascimento == date(1964, 4, 20)
        assert out.profissao == "professora"
        assert out.genero == FEMININO
        assert [c.titular for c in out.conjuges] == [False, True]
        # couple-level facts stay on the result for both
        assert out.regime_bens == "comunhao_parcial"
        assert out.aviso is None

    @pytest.mark.asyncio
    async def test_no_hint_keeps_both_spouses_and_the_notice(self):
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_DOIS_CONJUGES)).extract(
            b"%PDF", mimetype="application/pdf"
        )
        assert out.nome is None
        assert out.aviso == "titulares_multiplos"
        assert len(out.conjuges) == 2
        assert not any(c.titular for c in out.conjuges)
        assert out.profissao_confianca is ExtractionConfidence.NENHUMA

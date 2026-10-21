"""Field authority per document type (owner rule 2026-10-13): a document
emits only the fields it is the authoritative source for — `autoridade.py`.
Plus the two owner-reviewed real cases (a foreign seller's RNE and her
married name). All fixtures are invented except where the owner's review
quoted the printed text.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import autoridade
from noctusai_lib.integrations.documents.civil_status import find_estado_civil
from noctusai_lib.integrations.documents.conjuges import find_conjuges
from noctusai_lib.integrations.documents.profession import avaliar_profissao, find_profissao
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import campos_nucleo_faltando
from noctusai_lib.integrations.documents.rg import (
    find_caixa_identidade_cnh,
    find_rne,
    separar_orgao_uf,
)
from noctusai_lib.integrations.documents.types import IdentityFields, TextSource, TitularEsperado


class _Ladder:
    def __init__(self, texto: str) -> None:
        self.texto = texto

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        return (self.texto, TextSource.TEXT_LAYER, None)


async def _ler(texto: str, tipo: str | None, titular: TitularEsperado | None = None) -> IdentityFields:
    return await LadderIdentityExtractor(ladder=_Ladder(texto)).extract(
        b"%PDF", mimetype="application/pdf", tipo_documento=tipo, titular=titular
    )


def _sem_masculino(out: IdentityFields) -> None:
    assert "Masculino" not in repr(out)


# ─── The table itself ───────────────────────────────────────────────────────


class TestTabela:
    def test_unlisted_type_has_no_rule(self) -> None:
        assert autoridade.campos_autorizados("comprovante_endereco") is None
        assert autoridade.campos_autorizados(None) is None

    def test_synonyms_fold(self) -> None:
        assert autoridade.campos_autorizados("crnm") == autoridade.AUTORIDADE["RNE"]

    @pytest.mark.parametrize("tipo", ["certidao_casamento", "certidao_nascimento"])
    def test_certidoes_are_not_a_profissao_rne_or_address_source(self, tipo: str) -> None:
        campos = autoridade.campos_autorizados(tipo)
        assert not campos & {"rne", "profissao", "endereco"}

    def test_certidao_nascimento_is_not_a_cpf_rg_source(self) -> None:
        assert not autoridade.campos_autorizados("certidao_nascimento") & {"cpf", "rg"}

    def test_certidao_casamento_is_a_cpf_rg_source_only_per_spouse(self) -> None:
        # Owner decision 2026-10-21 (supersedes the 2026-10-13 rule).
        assert {"cpf", "rg"} <= autoridade.campos_autorizados("certidao_casamento")
        assert autoridade.so_por_conjuge("cpf", "certidao_casamento")
        assert autoridade.so_por_conjuge("rg", "certidao_casamento")
        assert not autoridade.so_por_conjuge("rg", "rg")

    def test_filiacao_and_naturalidade_are_declared_where_printed(self) -> None:
        for tipo in ("rg", "cin", "certidao_nascimento", "certidao_casamento"):
            assert {"nome_mae", "nome_pai", "naturalidade"} <= autoridade.campos_autorizados(tipo)
        assert {"nome_mae", "nome_pai"} <= autoridade.campos_autorizados("cnh")
        assert "naturalidade" not in autoridade.campos_autorizados("cnh")

    def test_cnh_is_the_registro_source_and_never_a_gender_source(self) -> None:
        campos = autoridade.campos_autorizados("cnh")
        assert {"rg", "rne", "registro_cnh"} <= campos and "genero" not in campos


# ─── Certidão de casamento ──────────────────────────────────────────────────

CERTIDAO_COM_DOCUMENTOS = """
CERTIDAO DE CASAMENTO
MATRICULA: 119917 02 55 1975 2 00012 034 0001234 31
NOMES:
JOAO CARLOS EXEMPLO
CPF: 412.954.238-98
MARIA LUIZA FICTICIA
JOAO CARLOS EXEMPLO, nascido em 01/02/1950, de nacionalidade brasileira, profissao: comerciante, portador do RG 12.345.678-9 SSP/SP, filho de PEDRO EXEMPLO e ANA EXEMPLO
MARIA LUIZA FICTICIA, nascida em 03/04/1952, de nacionalidade brasileira, profissao: professora, filha de JOSE FICTICIO e RITA FICTICIA
DATA DO CASAMENTO: 12/06/1975
REGIME DE BENS: COMUNHAO UNIVERSAL DE BENS
Endereço: RUA DO CARTORIO, 10 - CENTRO - COTIA/SP CEP 06700-000
Data de emissao: 10/01/2024
"""


class TestCertidaoCasamento:
    @pytest.mark.asyncio
    async def test_emits_no_profissao_or_address_and_never_the_other_spouses_cpf(self) -> None:
        out = await _ler(CERTIDAO_COM_DOCUMENTOS, "certidao_casamento", TitularEsperado(nome="Maria Luiza Ficticia"))
        # The CPF printed belongs to JOAO: the titular (Maria) never gets it
        # (owner decision 2026-10-21: CPF/RG are read per spouse only).
        assert out.cpf is None and out.rne is None
        assert out.profissao is None
        assert out.endereco is None
        assert out.data_casamento is not None and out.regime_bens == "comunhao_universal"

    @pytest.mark.asyncio
    async def test_matricula_is_read_and_validated(self) -> None:
        out = await _ler(CERTIDAO_COM_DOCUMENTOS, "certidao_casamento")
        assert out.matricula_certidao == "11991702551975200012034000123431"

    @pytest.mark.asyncio
    async def test_gender_is_only_ever_derived(self) -> None:
        out = await _ler(CERTIDAO_COM_DOCUMENTOS, "certidao_casamento", TitularEsperado(nome="Maria Luiza Ficticia"))
        if out.genero is not None:
            assert out.genero_derivado is True
        assert all(c.genero_derivado for c in out.conjuges if c.genero is not None)

    @pytest.mark.asyncio
    async def test_a_printed_sexo_label_is_not_read_on_a_certidao_de_casamento(self) -> None:
        out = await _ler("CERTIDAO DE CASAMENTO\nSEXO: MASCULINO\nDATA DO CASAMENTO: 12/06/1975", "certidao_casamento")
        assert out.genero is None


#: Owner review, real seller (2026-10-13): her own married name was read as a
#: second spouse and given "Masculino". Titular "SANTA MARIA FRACASSO",
#: married name "SANTA MARIA FRACASSO PICCHI", divorced.
CERTIDAO_SANTA_MARIA = """
CERTIDAO DE CASAMENTO
NOME: SANTA MARIA FRACASSO
NOME: SANTA MARIA FRACASSO PICCHI
nascido em 01/01/1948
DATA DO CASAMENTO: 12/06/1975
AVERBACAO: Divorcio decretado por sentenca de 10/10/1990.
"""

CERTIDAO_SANTA_MARIA_NARRATIVA = """
CERTIDAO DE CASAMENTO
SANTA MARIA FRACASSO, nascida em 10/05/1950, de nacionalidade italiana, filha de JOSE FRACASSO e MARIA ROSSI, casada com
o contraente. A contraente passou a usar o nome de SANTA MARIA FRACASSO PICCHI.
DATA DO CASAMENTO: 12/06/1975
AVERBACAO: Divorcio decretado por sentenca de 10/10/1990.
"""


class TestNomeDeCasadaNaoEConjuge:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("texto", [CERTIDAO_SANTA_MARIA, CERTIDAO_SANTA_MARIA_NARRATIVA])
    async def test_one_spouse_the_titular_with_her_married_name(self, texto: str) -> None:
        out = await _ler(texto, "certidao_casamento", TitularEsperado(nome="SANTA MARIA FRACASSO"))
        assert len(out.conjuges) == 1
        eu = out.conjuges[0]
        assert eu.titular is True
        assert eu.nome_apos_casamento == "SANTA MARIA FRACASSO PICCHI"
        assert eu.nome_anterior == "SANTA MARIA FRACASSO"
        assert out.estado_civil == "divorciado"
        # The other spouse is MISSING — reported, never fabricated.
        assert "campos_nucleo_ausentes" in out.aviso.split("+")
        assert "os dois cônjuges" in out.aviso_mensagem
        _sem_masculino(out)

    def test_without_a_hint_the_married_name_still_never_becomes_a_spouse(self) -> None:
        lido = find_conjuges(CERTIDAO_SANTA_MARIA)
        assert len(lido) == 1
        assert lido[0].nome == "SANTA MARIA FRACASSO PICCHI"
        assert lido[0].nome_anterior == "SANTA MARIA FRACASSO"
        assert lido[0].genero is None

    def test_a_real_couple_with_contained_names_is_not_merged(self) -> None:
        texto = (
            "CERTIDAO DE CASAMENTO\nNOME: JOSE SILVA\nNOME: MARIA JOSE SILVA\n"
            "DATA DO CASAMENTO: 12/06/1975\n"
        )
        assert len(find_conjuges(texto)) == 2


# ─── RNE: its own kind, never `rg` ──────────────────────────────────────────

#: The owner's review quoted this box verbatim for the same seller.
CAIXA_RNE_RG = "NOME: SANTA MARIA FRACASSO\nRG: W-573.678-Z · Órgão expedidor: DIREX\n"

CNH_ESTRANGEIRA = """
CARTEIRA NACIONAL DE HABILITACAO
DETRAN/SP
2 e 1 NOME E SOBRENOME
SANTA MARIA FRACASSO
4c DOC. IDENTIDADE / ORG. EMISSOR / UF
W-573.678-Z DIREX
4d CPF
NACIONALIDADE
ITALIANA
"""


class TestRne:
    def test_owner_box_is_an_rne_with_its_issuer(self) -> None:
        valor, _c, _r, orgao, tipo = find_rne(CAIXA_RNE_RG)
        assert (valor, orgao, tipo) == ("W-573.678-Z", "DIREX", "rne")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", [None, "rg", "rne", "cnh"])
    async def test_rne_never_lands_in_rg(self, tipo: str | None) -> None:
        out = await _ler(CAIXA_RNE_RG, tipo)
        assert out.rg is None and out.rg_orgao is None
        assert out.rne == "W-573.678-Z"
        assert out.rne_orgao == "DIREX"
        assert out.identidade_tipo == "rne"

    def test_cnh_box_routes_an_rne_shaped_value_to_rne(self) -> None:
        assert find_caixa_identidade_cnh(CNH_ESTRANGEIRA) == ("rne", "W-573.678-Z", "DIREX", None)

    @pytest.mark.asyncio
    async def test_foreigner_cnh_end_to_end(self) -> None:
        out = await _ler(CNH_ESTRANGEIRA, "cnh")
        assert out.rg is None and out.rne == "W-573.678-Z" and out.rne_orgao == "DIREX"
        # The box is filled (with an RNE) — `rg` is not a missing core field
        # (the fixture prints no CPF, which IS reported).
        assert campos_nucleo_faltando(out, "cnh") == ("cpf",)

    @pytest.mark.asyncio
    async def test_an_rne_document_is_not_an_rg_source(self) -> None:
        out = await _ler("RNE: V123456-7 CGPI/DIREX/DPF\nSEXO: F\nNOME: ANA EXEMPLO", "rne")
        assert out.rg is None
        assert out.rne == "V123456-7" and out.rne_orgao == "CGPI/DIREX/DPF"
        assert out.genero == "Feminino" and out.genero_derivado is False  # printed SEXO


# ─── CNH ────────────────────────────────────────────────────────────────────

CNH = """
CARTEIRA NACIONAL DE HABILITACAO
DETRAN/SP
NOME: JOAO CARLOS EXEMPLO
3 DATA, LOCAL E UF DE NASCIMENTO
01/02/1980, SAO PAULO, SP
4c DOC. IDENTIDADE / ORG. EMISSOR / UF
13032360 SSP SP
4d CPF
412.954.238-98
5 N° REGISTRO
12345678900
RENACH SP123456789
SEXO: M
"""


class TestCnh:
    @pytest.mark.asyncio
    async def test_rg_comes_with_orgao_and_uf_from_the_box(self) -> None:
        out = await _ler(CNH, "cnh")
        assert out.rg == "13032360"
        assert out.rg_orgao == "SSP/SP"
        assert out.rg_orgao_partes == ("SSP", "SP")

    @pytest.mark.asyncio
    async def test_registro_is_read_and_dv_checked(self) -> None:
        out = await _ler(CNH, "cnh")
        assert out.registro_cnh == "12345678900"

    @pytest.mark.asyncio
    async def test_bad_registro_dv_is_not_emitted(self) -> None:
        out = await _ler(CNH.replace("12345678900", "12345678910"), "cnh")
        assert out.registro_cnh is None

    @pytest.mark.asyncio
    async def test_cnh_is_not_a_gender_source(self) -> None:
        out = await _ler(CNH, "cnh")
        assert out.genero is None

    @pytest.mark.asyncio
    async def test_glued_issuer_and_uf(self) -> None:
        out = await _ler(CNH.replace("13032360 SSP SP", "13032360SSPSP"), "cnh")
        assert out.rg == "13032360" and out.rg_orgao == "SSP/SP"


# ─── CIN / RG ───────────────────────────────────────────────────────────────


class TestCinRg:
    @pytest.mark.asyncio
    async def test_cin_reads_printed_sexo_and_no_rg(self) -> None:
        out = await _ler(
            "CARTEIRA DE IDENTIDADE NACIONAL\nNOME: ANA EXEMPLO\nCPF: 412.954.238-98\n"
            "SEXO: F\nREGISTRO GERAL: 412.954.238-98\nDATA DE NASCIMENTO: 01/02/1980",
            "cin",
        )
        assert out.cpf == "412.954.238-98" and out.rg is None
        assert out.genero == "Feminino" and out.genero_derivado is False

    @pytest.mark.asyncio
    async def test_rg_is_not_a_gender_profissao_or_estado_civil_source(self) -> None:
        out = await _ler(
            "REGISTRO GERAL: 52.179.965-X SSP/SP\nNOME: ANA EXEMPLO\nSEXO: F\n"
            "PROFISSAO: engenheira\nESTADO CIVIL: CASADA",
            "rg",
        )
        assert out.rg == "52.179.965-X" and out.rg_orgao == "SSP/SP"
        assert out.genero is None and out.profissao is None and out.estado_civil is None


# ─── Normalisation and vocabulary ───────────────────────────────────────────


class TestNormalizacao:
    @pytest.mark.parametrize("valor", ["SSP/SP", "SSP-SP", "SSP SP", "ssp/sp"])
    def test_orgao_splits_into_orgao_and_uf(self, valor: str) -> None:
        assert separar_orgao_uf(valor) == ("SSP", "SP")

    def test_federal_issuer_has_no_uf(self) -> None:
        assert separar_orgao_uf("DIREX") == ("DIREX", None)

    def test_aposentanda_is_flagged_not_emitted(self) -> None:
        assert find_profissao("PROFISSAO: aposentanda") == (None, "nenhuma", None)
        assert avaliar_profissao("aposentanda") == (False, "aposentada")

    @pytest.mark.asyncio
    async def test_extractor_names_the_refused_profissao_with_a_suggestion(self) -> None:
        out = await _ler("NOME: ANA EXEMPLO\nPROFISSAO: aposentanda", None)
        assert out.profissao is None
        assert "vocabulario_invalido" in out.aviso.split("+")
        assert "aposentanda" in out.aviso_mensagem and "aposentada" in out.aviso_mensagem

    @pytest.mark.parametrize("valor", ["aposentada", "engenheiro civil", "do lar", "corretora de imóveis"])
    def test_real_professions_pass(self, valor: str) -> None:
        assert avaliar_profissao(valor)[0] is True

    def test_uniao_estavel_is_not_an_estado_civil(self) -> None:
        assert find_estado_civil("ESTADO CIVIL: UNIAO ESTAVEL")[0] is None
        assert find_estado_civil("ESTADO CIVIL: SEPARADA JUDICIALMENTE")[0] == "separado_judicialmente"


class TestPrecedencia:
    """SOURCE precedence per field (owner rule 2026-10-14, prod deal 876)."""

    def test_certidao_casamento_outranks_ficha_for_the_couple_facts(self):
        for campo in ("estado_civil", "regime_bens", "data_casamento"):
            assert autoridade.mais_autoritativo(campo, "certidao_casamento", "ficha_cadastral")
            assert not autoridade.mais_autoritativo(campo, "ficha_cadastral", "certidao_casamento")

    def test_pacto_ties_with_the_certidao_for_regime(self):
        assert not autoridade.mais_autoritativo("regime_bens", "pacto_antenupcial", "certidao_casamento")
        assert autoridade.mais_autoritativo("regime_bens", "pacto_antenupcial", "ficha_cadastral")

    def test_nacionalidade_ladder(self):
        ordem = ["crnm", "certidao_casamento", "cin", "ficha_cadastral"]
        for alto, baixo in zip(ordem, ordem[1:]):
            assert autoridade.mais_autoritativo("nacionalidade", alto, baixo)
        assert autoridade.posto("nacionalidade", "rnm") == autoridade.posto("nacionalidade", "rne") == 0

    def test_identity_documents_outrank_certidao_and_ficha_for_nome(self):
        assert autoridade.mais_autoritativo("nome", "cnh", "certidao_casamento")
        assert autoridade.mais_autoritativo("nome", "certidao_nascimento", "ficha_cadastral")
        assert not autoridade.mais_autoritativo("nome", "rg", "cin")  # same tier

    def test_certidao_casamento_is_the_last_tier_for_rg_orgao(self):
        """Owner decision 2026-10-21: it fills an empty field, but never takes
        over from ANY other document; a real RG/CNH (and the ficha) outrank it."""
        for campo, alto in (("rg", "rg"), ("rg_orgao", "cnh")):
            assert autoridade.mais_autoritativo(campo, alto, "certidao_casamento")
            assert autoridade.mais_autoritativo(campo, "ficha_cadastral", "certidao_casamento")
            assert not autoridade.mais_autoritativo(campo, "certidao_casamento", alto)
            assert not autoridade.mais_autoritativo(campo, "certidao_casamento", "ficha_cadastral")

    def test_cpf_from_the_certidao_stays_unranked_for_the_measured_resolver(self):
        assert autoridade.posto("cpf", "certidao_casamento") is None
        assert not autoridade.mais_autoritativo("cpf", "cin", "certidao_casamento")

    def test_filiacao_identity_docs_tie_and_outrank_the_marriage_clause(self):
        for campo in ("nome_mae", "nome_pai", "naturalidade"):
            assert autoridade.mais_autoritativo(campo, "rg", "certidao_casamento")
            assert autoridade.mais_autoritativo(campo, "certidao_nascimento", "certidao_casamento")
            assert not autoridade.mais_autoritativo(campo, "certidao_casamento", "rg")
            assert not autoridade.mais_autoritativo(campo, "certidao_nascimento", "rg")

    def test_capacidades_are_derived_from_the_authority_table(self):
        from noctusai_lib.integrations.documents.capacidades import CAPACIDADES

        assert CAPACIDADES["rg"] == autoridade.capacidades_de("RG")
        assert "profissao" not in CAPACIDADES["rg"] and "estado_civil" not in CAPACIDADES["rg"]
        assert "rg_orgao" in CAPACIDADES["certidao_casamento"] and "conjuge" in CAPACIDADES["certidao_casamento"]
        for tipo, aut in (("cin", "CIN"), ("cnh", "CNH"), ("certidao_nascimento", "CERTIDAO_NASCIMENTO")):
            assert CAPACIDADES[tipo] == autoridade.capacidades_de(aut)

    def test_rg_ladder_and_endereco_ficha_first(self):
        assert autoridade.mais_autoritativo("rg", "rg", "cnh")
        assert autoridade.mais_autoritativo("rg_orgao", "cnh", "ficha_cadastral")
        assert autoridade.mais_autoritativo("endereco", "ficha_cadastral", "comprovante_endereco")

    def test_an_unranked_side_never_outranks_nor_is_outranked(self):
        assert autoridade.posto("cpf", "serasa_crednet") is None
        assert not autoridade.mais_autoritativo("cpf", "cin", "serasa_crednet")
        assert not autoridade.mais_autoritativo("cpf", "serasa_crednet", "ficha_cadastral")
        assert not autoridade.mais_autoritativo("cpf", "cin", None)
        assert not autoridade.mais_autoritativo("genero", "serasa_crednet", "ficha_cadastral")

    def test_genero_a_printed_sex_then_the_fichas_declaration(self):
        """Deal 876 (2026-10-19): `genero` gained a ladder — CIN/RNE/certidão
        de nascimento print it, the ficha's checked box declares it."""
        assert autoridade.mais_autoritativo("genero", "cin", "ficha_cadastral")
        assert autoridade.mais_autoritativo("genero", "crnm", "ficha_cadastral")
        assert not autoridade.mais_autoritativo("genero", "ficha_cadastral", "rne")

    def test_a_derived_only_source_is_outranked_by_any_ranked_reading(self):
        """A certidão de casamento's gênero is grammar, never printed
        (`GENERO_SO_DERIVADO`): a value stored from it gives way to any
        ranked reading — and never outranks anything itself."""
        assert autoridade.so_derivado("genero", "certidao_casamento")
        assert autoridade.mais_autoritativo("genero", "ficha_cadastral", "certidao_casamento")
        assert not autoridade.mais_autoritativo("genero", "certidao_casamento", "ficha_cadastral")
        assert not autoridade.mais_autoritativo("genero", "serasa_crednet", "certidao_casamento")
        assert not autoridade.so_derivado("nome", "certidao_casamento")

    def test_every_ranked_identity_type_may_emit_the_field(self):
        # A precedence tier never names a type `AUTORIDADE` forbids from
        # emitting that field — the two tables cannot contradict each other.
        for campo, tiers in autoridade.PRECEDENCIA.items():
            for tier in tiers:
                for tipo in tier:
                    autorizados = autoridade.AUTORIDADE.get(tipo)
                    if autorizados is None:
                        continue
                    base = "rg" if campo == "rg_orgao" else campo
                    assert base in autorizados, (campo, tipo)

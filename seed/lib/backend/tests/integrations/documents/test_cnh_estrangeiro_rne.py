"""A foreign national's CNH (new model): the 4c field prints an RNE, the
NACIONALIDADE field prints `ESTRANGEIRO(A)`. Owner rule 2026-10-10: store
exactly what the document prints; never derive or invent a document value.

All fixtures are invented.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.nacionalidade import canonico, feminino, find_nacionalidade
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.rg import find_rg, find_rg_orgao, find_rne, rg_shape_valido
from noctusai_lib.integrations.documents.types import TextSource, TitularEsperado

CNH_ESTRANGEIRO = """
REPUBLICA FEDERATIVA DO BRASIL
CARTEIRA NACIONAL DE HABILITACAO
DEPARTAMENTO ESTADUAL DE TRANSITO DETRAN/SP
2 NOME
MARIA EXEMPLO TESTE
3 DATA, LOCAL E UF DE NASCIMENTO
01/02/1980, ROMA, EX
4c DOC. IDENTIDADE / ORG. EMISSOR / UF
W123456ZDIREXEX
4d CPF
NACIONALIDADE
ESTRANGEIRO(A)
"""


class _Ladder:
    def __init__(self, texto: str) -> None:
        self.texto = texto

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        return (self.texto, TextSource.TEXT_LAYER, None)


class TestRne:
    def test_rne_is_read_whole_as_printed(self) -> None:
        valor, conf, _rot, orgao, tipo = find_rne(CNH_ESTRANGEIRO)
        assert valor == "W123456Z"
        assert conf == "alta"
        assert orgao == "DIREX"
        assert tipo == "rne"

    def test_plain_rg_does_not_swallow_the_rne_digits(self) -> None:
        assert find_rg(CNH_ESTRANGEIRO)[0] is None

    def test_a_cnh_header_detran_is_never_the_identity_issuer(self) -> None:
        assert find_rg_orgao(CNH_ESTRANGEIRO, "573678")[0] is None

    def test_no_issuer_printed_leaves_it_null(self) -> None:
        texto = "4c DOC. IDENTIDADE\nV123456-7\nDETRAN/SP"
        valor, _c, _r, orgao, tipo = find_rne(texto)
        assert valor == "V123456-7"
        assert orgao is None
        assert tipo is None  # shape alone does not decide RNE vs RNM

    def test_an_ordinary_rg_is_not_an_rne(self) -> None:
        texto = "4c DOC. IDENTIDADE / ORG. EMISSOR / UF\n13032360 SSP/SP"
        assert find_rne(texto)[0] is None
        assert find_rg(texto)[0] == "13032360"

    def test_unlabelled_letter_digits_run_is_not_read(self) -> None:
        assert find_rne("PLACA ABC1D23 PROTOCOLO W123456Z")[0] is None

    def test_rne_with_letter_check_has_a_valid_shape(self) -> None:
        assert rg_shape_valido("W573678-Z")


class TestNacionalidadeEstrangeiro:
    def test_printed_estrangeiro_is_read(self) -> None:
        assert find_nacionalidade(CNH_ESTRANGEIRO) == ("estrangeiro", "alta", "NACIONALIDADE")

    def test_canonical_and_agreement(self) -> None:
        assert canonico("ESTRANGEIRO(A)") == "estrangeiro"
        assert canonico("estrangeira") == "estrangeiro"
        assert feminino("estrangeiro") == "estrangeira"


class TestExtractor:
    @pytest.mark.asyncio
    async def test_end_to_end(self) -> None:
        out = await LadderIdentityExtractor(ladder=_Ladder(CNH_ESTRANGEIRO)).extract(
            b"%PDF", mimetype="application/pdf",
        )
        assert out.rg == "W123456Z"
        assert out.rg_orgao == "DIREX"
        assert out.identidade_tipo == "rne"
        assert out.nacionalidade == "estrangeiro"


CERTIDAO_DIVORCIO = """
CERTIDAO DE CASAMENTO
Consta o casamento celebrado em 05/06/2010.
ANA PAULA EXEMPLO, nascida no dia vinte de fevereiro de mil novecentos e oitenta e dois (20/02/1982), de nacionalidade brasileira, filha de MARCOS EXEMPLO e de LUCIA EXEMPLO, casada com JOSE CARLOS FICTICIO, nascido no dia dez de janeiro de mil novecentos e oitenta (10/01/1980), de nacionalidade brasileira. A contraente passou a assinar ANA PAULA EXEMPLO FICTICIO.
AVERBACAO: Divorcio decretado em 12/03/2020.
"""


class TestCertidaoDivorcio:
    @pytest.mark.asyncio
    async def test_titular_keeps_her_own_facts_not_the_ex_husbands(self) -> None:
        out = await LadderIdentityExtractor(ladder=_Ladder(CERTIDAO_DIVORCIO)).extract(
            b"%PDF", mimetype="application/pdf",
            titular=TitularEsperado(nome="Ana Paula Exemplo"),
        )
        assert len(out.conjuges) == 1
        c = out.conjuges[0]
        assert c.genero == "Feminino"
        assert c.data_nascimento is not None and c.data_nascimento.isoformat() == "1982-02-20"
        assert c.titular is True  # matched through her pre-adoption name
        assert out.genero == "Feminino"

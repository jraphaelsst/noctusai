"""`derivar_endereco` — the matrícula's own street + officialised número.

🔴 WHAT THESE PIN
------------------
1. Inline shape: "situada na Rua X, nº 100," — street + número from the SAME
   sentence.
2. A "situado na X, constituído pelo lote nº N" shape does NOT mistake the
   LOTE number for the street número (the qualifier between the comma and
   "nº" breaks the tight inline pattern) — falls through to the averbação
   scan instead.
3. THE ORDERING TRAP: two averbações both officialise a número — the
   HIGHEST-numbered one wins, regardless of which appears first in the text.
4. An explicit "s/nº", with no officialisation anywhere, is a CONFIRMED
   absence (`numero_confirmado_ausente=True`), never the same as "nothing
   found".
5. No officialisation AND no explicit "s/nº" is genuinely INCONCLUSIVE —
   `numero` and `numero_confirmado_ausente` both come back "no answer",
   never a guess.
6. Casing/accents of the PRINTED value are the ORIGINAL source's, never the
   folded/upper-cased matching copy's.
7. No "situad[oa] n[oa]" phrase anywhere → no logradouro, no crash.

All names, streets, lots and matrícula numbers are invented.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.matricula_endereco import (
    EnderecoMatricula,
    derivar_endereco,
)

# Inline shape: número right after the street, same sentence.
TEXTO_IMOVEL_INLINE = (
    "O apartamento nº 11 do Edifício Exemplo, situado na Rua Fictícia, nº 100, "
    "Bairro Modelo, com área privativa de 80,00m2."
)

# Real-shaped: street named in the abertura, número NOT inline — a qualifier
# ("constituído pelo lote nº 14") sits between the street and the next "nº".
TEXTO_IMOVEL_SEM_NUMERO_INLINE = (
    'Terreno situado na Alameda Inventada, constituído pelo lote nº 14 '
    '(quatorze) da quadra "D", no loteamento denominado "Bosque Modelo", '
    "nesta cidade, município e comarca de Cidade Exemplo, Estado de São Paulo."
)

# Two averbações both officialise a número — AV.5 (later) must win over AV.2
# (earlier), REGARDLESS of which one the text lists first.
TEXTO_ATOS_DUAS_OFICIALIZACOES_EM_ORDEM = (
    "R.1/9.999 - Prot. 500 - Por escritura pública, o imóvel foi transmitido a FULANO.\n"
    "AV.2/9.999 - Prot. 600 - Para ficar constando a oficialização do nº 300 "
    "referente ao prédio residencial s/nº situado na Alameda Inventada.\n"
    "AV.5/9.999 - Prot. 700 - Para ficar constando a oficialização do nº 535 "
    "referente ao prédio residencial s/nº situado na Alameda Inventada.\n"
)

# Same two acts, text order SCRAMBLED (AV.5 written before AV.2) — proves the
# choice is driven by act NUMERO, never by textual position.
TEXTO_ATOS_DUAS_OFICIALIZACOES_FORA_DE_ORDEM = (
    "AV.5/9.999 - Prot. 700 - Para ficar constando a oficialização do nº 535 "
    "referente ao prédio residencial s/nº situado na Alameda Inventada.\n"
    "AV.2/9.999 - Prot. 600 - Para ficar constando a oficialização do nº 300 "
    "referente ao prédio residencial s/nº situado na Alameda Inventada.\n"
)

TEXTO_ATOS_SEM_OFICIALIZACAO = (
    "R.1/1.111 - Prot. 1 - Por escritura pública, o imóvel foi transmitido a FULANO."
)

TEXTO_IMOVEL_SNUMERO_EXPLICITO = (
    'Terreno situado na Alameda Sem Numero, no loteamento denominado "Bosque", '
    "município de Cidade Exemplo, Estado de SP, prédio s/nº."
)

TEXTO_SEM_LOGRADOURO = "Nada aqui descreve um imóvel."


class TestFormaInline:
    def test_rua_e_numero_da_mesma_sentenca(self):
        r = derivar_endereco(TEXTO_IMOVEL_INLINE)
        assert r == EnderecoMatricula(
            logradouro="Rua Fictícia", numero="100", numero_confirmado_ausente=False
        )

    def test_a_casing_e_acentos_impressos_sao_os_do_texto_original(self):
        # A folded/upper-cased copy is used only for MATCHING — the printed
        # value must be the literal source slice.
        r = derivar_endereco(TEXTO_IMOVEL_INLINE)
        assert r.logradouro == "Rua Fictícia"
        assert "RUA" not in (r.logradouro or "")


class TestLoteNaoViraNumeroDaRua:
    def test_numero_do_lote_nao_e_confundido_com_numero_da_rua(self):
        # No número inline (the qualifier breaks the tight pattern) — only
        # the street resolves from the abertura alone.
        r = derivar_endereco(TEXTO_IMOVEL_SEM_NUMERO_INLINE)
        assert r.logradouro == "Alameda Inventada"
        assert r.numero is None


class TestArmadilhaDeOrdenacao:
    def test_a_averbacao_de_maior_numero_vence_em_ordem(self):
        r = derivar_endereco(
            TEXTO_IMOVEL_SEM_NUMERO_INLINE, TEXTO_ATOS_DUAS_OFICIALIZACOES_EM_ORDEM
        )
        assert r.numero == "535"
        assert r.numero_confirmado_ausente is False

    def test_a_averbacao_de_maior_numero_vence_fora_de_ordem(self):
        """THE REGRESSION THIS PINS: taking the FIRST officialisation found
        while scanning top-to-bottom would return '535' here too (it is
        listed first) for the WRONG reason — prove the selection is driven
        by act número, not by position, by checking the SAME pair the other
        way round lands on the SAME (correct) answer."""
        r = derivar_endereco(
            TEXTO_IMOVEL_SEM_NUMERO_INLINE, TEXTO_ATOS_DUAS_OFICIALIZACOES_FORA_DE_ORDEM
        )
        assert r.numero == "535"
        assert r.numero_confirmado_ausente is False


class TestSemNumeroConfirmado:
    def test_s_barra_no_explicito_sem_oficializacao_e_confirmado(self):
        r = derivar_endereco(TEXTO_IMOVEL_SNUMERO_EXPLICITO)
        assert r.logradouro == "Alameda Sem Numero"
        assert r.numero is None
        assert r.numero_confirmado_ausente is True


class TestInconclusivo:
    def test_sem_oficializacao_e_sem_s_barra_no_nao_e_confirmado(self):
        r = derivar_endereco(TEXTO_IMOVEL_SEM_NUMERO_INLINE, TEXTO_ATOS_SEM_OFICIALIZACAO)
        assert r.logradouro == "Alameda Inventada"
        assert r.numero is None
        assert r.numero_confirmado_ausente is False


class TestSemLogradouro:
    def test_texto_sem_marcador_situado_nao_derruba_nem_inventa(self):
        r = derivar_endereco(TEXTO_SEM_LOGRADOURO)
        assert r == EnderecoMatricula()


# ─── 876 audit (2026-10): averbação addresses, decree numbers, thousands ────

_ABERTURA_RUA_UM = (
    'IMÓVEL: UM TERRENO URBANO consistente no LOTE Nº19 DA QUADRA "A", do loteamento '
    'denominado "RESERVA EXEMPLO", situado no Bairro da Granja Exemplo, assim descrito: '
    "mede 11,32 metros de frente para a Rua Um; encerrando a área de 640,87 metros quadrados."
)
_ATOS_CONSTRUCAO = (
    _ABERTURA_RUA_UM + "\n"
    "AV.01 - Fica averbado o que consta.\n"
    "AV.06 - Pelo requerimento firmado em 2022, procede-se à presente para constar que sobre o "
    "imóvel desta matrícula foi edificada uma construção residencial com área total de 299,43 "
    "metros quadrados, situada na Alameda Exemplo, nº 81, (antiga Rua Um, oficializada através "
    "do Decreto nº 7746/2013 do Município), conforme prova o Habite-se.\n"
)


class TestEnderecoDaAverbacaoDeConstrucao:
    def test_a_construction_averbacao_states_the_address(self):
        e = derivar_endereco(_ABERTURA_RUA_UM, _ATOS_CONSTRUCAO)
        assert (e.logradouro, e.numero) == ("Alameda Exemplo", "81")

    def test_a_bairro_is_never_a_street(self):
        # Without the averbação: "situado no Bairro …" names no street at all.
        assert derivar_endereco(_ABERTURA_RUA_UM, _ABERTURA_RUA_UM).logradouro is None

    def test_a_decree_number_is_never_the_house_number(self):
        atos = _ABERTURA_RUA_UM + "\nAV.03 - Rua oficializada através do Decreto nº 7746/2013.\n"
        assert derivar_endereco(_ABERTURA_RUA_UM, atos).numero is None

    def test_number_followed_by_a_parenthesis(self):
        atos = _ATOS_CONSTRUCAO.replace("nº 81, (antiga", "nº 81 (antiga")
        assert derivar_endereco(_ABERTURA_RUA_UM, atos).numero == "81"


class TestNumeroComMilhar:
    def test_thousands_separator_is_part_of_the_number(self):
        texto = "IMÓVEL: CASA 24, sito à Estrada Exemplo, nº2.350, Jardim Exemplo, Cotia."
        assert derivar_endereco(texto).numero == "2.350"

    def test_a_rectification_averbacao_replaces_the_printed_number(self):
        texto = "IMÓVEL: CASA 24, sito à Estrada Exemplo, nº2.350, Jardim Exemplo, Cotia."
        atos = texto + (
            "\nAV.04 - para constar que o Condomínio faz frente para a Estrada Exemplo, "
            "nº2.530 e não 2.350 como constou.\n"
        )
        assert derivar_endereco(texto, atos).numero == "2.530"


def test_a_line_break_inside_the_street_is_layout():
    e = derivar_endereco("IMÓVEL: casa situada na Rua\nExemplar, nº 10, Cotia.")
    assert e.logradouro == "Rua Exemplar"


class TestNumeroPorAverbacaoDeConstrucao:
    """Deal 857 (2026-10): the abertura names the street, a later AV says the
    building "recebeu o número N da Rua X" — street + número combine."""

    ABERTURA = (
        "IMÓVEL: TERRENO situado na Rua Inventada Exemplar, constituído pelo "
        "lote 01 da quadra B, nesta cidade."
    )
    ATOS = (
        "R.1/9.999 - Prot. 500 - Por escritura pública, transmitido a FULANO.\n"
        "AV.2/9.999 - Prot. 600 - Fica averbado que foi construído sobre o terreno "
        "desta matrícula um prédio residencial, o qual recebeu o número 08 da Rua "
        "Inventada Exemplar.\n"
    )

    def test_street_from_abertura_and_number_from_construction_av(self):
        e = derivar_endereco(self.ABERTURA, self.ATOS)
        assert (e.logradouro, e.numero) == ("Rua Inventada Exemplar", "08")
        assert e.numero_confirmado_ausente is False

    def test_without_the_av_the_number_stays_unresolved(self):
        e = derivar_endereco(self.ABERTURA, self.ATOS.split("AV.2")[0])
        assert (e.logradouro, e.numero) == ("Rua Inventada Exemplar", None)

    def test_recebeu_without_a_digit_is_not_a_number(self):
        atos = self.ATOS.replace("o número 08", "o número de ordem")
        assert derivar_endereco(self.ABERTURA, atos).numero is None

    def test_highest_av_wins_when_renumbered(self):
        atos = self.ATOS + (
            "AV.4/9.999 - Prot. 700 - Renumerado: o prédio recebeu o número 12 da Rua "
            "Inventada Exemplar.\n"
        )
        assert derivar_endereco(self.ABERTURA, atos).numero == "12"


class TestLocalizadaNa:
    """Deal 874 — a condomínio unit's abertura says "localizada na", not
    "situada na"; the street and número must still be read (synthetic text)."""

    ABERTURA = (
        'CASA Nº "7" do Condomínio denominado "RESIDENCIAL EXEMPLO"\n'
        "localizada na Estrada Municipal Inventada, nº 321, neste Município e\n"
        "Comarca de Cidade Exemplo-SP, assim descrita: área privativa de 90,000 m2."
    )

    def test_localizada_na_reads_street_and_number(self):
        e = derivar_endereco(self.ABERTURA)
        assert (e.logradouro, e.numero) == ("Estrada Municipal Inventada", "321")

    def test_localizado_a_loose_form(self):
        e = derivar_endereco("Um terreno localizado à Rua Inventada Exemplar, conforme planta.")
        assert e.logradouro == "Rua Inventada Exemplar"

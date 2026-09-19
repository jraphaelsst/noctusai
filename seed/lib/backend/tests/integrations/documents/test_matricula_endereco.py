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

"""Regressions found scoring the extractor against a real deal's documents
(2026-10-13). Fixtures are invented; each reproduces the measured SHAPE.

- R1: a foreign holder's CNH — the RNE was read, and `rg` still got an
  11-digit form number printed at the card's foot.
- R2: a compromised first read ("CLELIER BASSO MERY") disagreeing with a
  clean escalated read ("CILENE …") kept the garbage.
- R3: a certidão de casamento whose divorce AVERBAÇÃO one transcription missed
  came out "casado" (the regime phrase alone implies casado).
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import mesclar
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

BAIXA = ExtractionConfidence.BAIXA
ALTA = ExtractionConfidence.ALTA


class _Ladder:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.chamadas = 0

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        self.chamadas += 1
        return (self.texto, TextSource.OCR, None)


# ─── R1 ─────────────────────────────────────────────────────────────────────

CNH_RNE_PRIMEIRA = """CARTEIRA NACIONAL DE HABILITACAO
NOME E SOBRENOME: ANA ESTRANGEIRA EXEMPLO
DOCUMENTO DE IDENTIDADE: (ilegível)
REGISTRO GERAL: 12346581446
LOCAL: COTIA, SP
"""
CNH_RNE_ESCALADA = """CARTEIRA NACIONAL DE HABILITACAO
2 e 1 NOME E SOBRENOME: ANA ESTRANGEIRA EXEMPLO
4c DOC. IDENTIDADE / ÓRG. EMISSOR / UF: W573678ZDIREXEX
5 Nº REGISTRO: 02954184886
4d CPF: 412.954.238-98
NACIONALIDADE: ESTRANGEIRO(A)
12346581446
"""


class TestR1RgNuncaComRne:
    def test_eleven_digit_run_is_never_an_rg(self) -> None:
        out = LadderIdentityExtractor()._ler(CNH_RNE_PRIMEIRA, TextSource.OCR, None, None, "cnh")
        assert out.rg is None
        assert ("rg", "12346581446") in out.leituras_alternativas
        assert "rg_descartado" in out.aviso.split("+")

    @pytest.mark.parametrize("valor", ["412.954.238-98", "41295423898", "02954184886"])
    def test_cpf_or_cnh_registro_shaped_rg_is_refused(self, valor: str) -> None:
        out = LadderIdentityExtractor()._ler(f"REGISTRO GERAL: {valor}\nNOME: ANA EXEMPLO", TextSource.OCR, None, None, "rg")
        assert out.rg is None

    def test_rg_and_rne_are_exclusive_in_one_read(self) -> None:
        texto = "RG: 52.179.965-X\nRNE: W-573.678-Z DIREX\nNOME: ANA EXEMPLO"
        out = LadderIdentityExtractor()._ler(texto, TextSource.OCR, None, None, "rg")
        assert out.rne == "W-573.678-Z" and out.rg is None

    def test_merge_drops_a_first_read_rg_when_the_re_read_finds_an_rne(self) -> None:
        original = IdentityFields(rg="52.179.965-X", rg_confianca=BAIXA, rg_orgao="SSP/SP", rg_orgao_confianca=BAIXA)
        escalada = IdentityFields(rne="W573678Z", rne_confianca=BAIXA, rne_orgao="DIREX", identidade_tipo="rne")
        out = mesclar(original, escalada, escalation_model="m")
        assert out.rne == "W573678Z" and out.rg is None and out.rg_orgao is None
        assert ("rg", "52.179.965-X") in out.leituras_alternativas

    @pytest.mark.asyncio
    async def test_end_to_end_rne_as_printed_no_rg_registro_kept(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CNH_RNE_PRIMEIRA),
            escalar_releitura=True,
            escalation_ladder=_Ladder(CNH_RNE_ESCALADA),
        ).extract(b"x", mimetype="image/jpeg", tipo_documento="cnh")
        assert out.rg is None
        assert out.rne == "W573678Z"  # as printed — no punctuation invented
        assert out.rne_orgao == "DIREX"
        assert out.registro_cnh == "02954184886"


# ─── R2 ─────────────────────────────────────────────────────────────────────


class TestR2LeituraComprometidaPerde:
    def test_clean_escalated_read_wins_over_a_compromised_first_read(self) -> None:
        original = IdentityFields(
            nome="CLELIER BASSO MERY", nome_confianca=BAIXA, aviso=AVISO_LEITURA_COMPROMETIDA
        )
        escalada = IdentityFields(nome="CILENE AFRA EXEMPLO NERY", nome_confianca=BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome == "CILENE AFRA EXEMPLO NERY"
        assert ("nome", "CLELIER BASSO MERY") in out.leituras_alternativas
        assert not out.leitura_comprometida

    def test_two_clean_reads_that_disagree_keep_the_first_pending(self) -> None:
        original = IdentityFields(nome="ANA EXEMPLO SILVA", nome_confianca=BAIXA)
        escalada = IdentityFields(nome="ANA EXEMPLO SILVEIRA", nome_confianca=BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome == "ANA EXEMPLO SILVA" and out.nome_confianca is BAIXA
        assert ("nome", "ANA EXEMPLO SILVEIRA") in out.leituras_alternativas


# ─── R3 ─────────────────────────────────────────────────────────────────────

CERTIDAO_SEM_AVERBACAO_LIDA = """CERTIDAO DE CASAMENTO
NOMES: JOAO EXEMPLO / ANA EXEMPLO
REGIME DE BENS DO CASAMENTO: COMUNHAO UNIVERSAL DE BENS
DATA DO CASAMENTO: 12/06/1975
AVERBACOES / ANOTACOES A ACRESCER: (ilegível)
"""
CERTIDAO_COM_DIVORCIO = """CERTIDAO DE CASAMENTO
NOMES: JOAO EXEMPLO / ANA EXEMPLO
REGIME DE BENS DO CASAMENTO: COMUNHAO UNIVERSAL DE BENS
DATA DO CASAMENTO: 12/06/1975
AVERBACOES / ANOTACOES A ACRESCER:
AVERBACAO DE DIVORCIO: POR SENTENCA DATADA DE 19/06/89, FOI HOMOLOGADO O DIVORCIO DO CASAL.
"""


class TestR3AverbacaoVence:
    def test_each_read_alone(self) -> None:
        ex = LadderIdentityExtractor()
        sem = ex._ler(CERTIDAO_SEM_AVERBACAO_LIDA, TextSource.OCR, None, None, "certidao_casamento")
        com = ex._ler(CERTIDAO_COM_DIVORCIO, TextSource.OCR, None, None, "certidao_casamento")
        assert sem.estado_civil == "casado"  # inferred from the regime phrase
        assert com.estado_civil == "divorciado"
        assert com.estado_civil_rotulo.startswith("AVERBACAO")

    @pytest.mark.parametrize("ordem", ["sem_primeiro", "com_primeiro"])
    def test_the_averbacao_reading_wins_either_way(self, ordem: str) -> None:
        ex = LadderIdentityExtractor()
        sem = ex._ler(CERTIDAO_SEM_AVERBACAO_LIDA, TextSource.OCR, None, None, "certidao_casamento")
        com = ex._ler(CERTIDAO_COM_DIVORCIO, TextSource.OCR, None, None, "certidao_casamento")
        a, b = (sem, com) if ordem == "sem_primeiro" else (com, sem)
        out = mesclar(a, b, escalation_model="m")
        assert out.estado_civil == "divorciado"
        assert out.regime_bens == "comunhao_universal"
        assert ("estado_civil", "casado") in out.leituras_alternativas

    @pytest.mark.asyncio
    async def test_end_to_end_divorced_no_gender(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_SEM_AVERBACAO_LIDA),
            escalar_releitura=True,
            escalation_ladder=_Ladder(CERTIDAO_COM_DIVORCIO),
        ).extract(b"x", mimetype="application/pdf", tipo_documento="certidao_casamento")
        assert out.estado_civil == "divorciado"
        assert out.regime_bens == "comunhao_universal"
        assert out.genero is None
        assert all(c.genero is None or c.genero_derivado for c in out.conjuges)

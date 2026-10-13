"""Regressions found scoring the extractor against a real deal's documents
(2026-10-13). Fixtures are invented; each reproduces the measured SHAPE.

- R1: a foreign holder's CNH — the RNE was read, and `rg` still got an
  11-digit form number printed at the card's foot.
- R2: a compromised first read ("CLELIER BASSO MERY") disagreeing with a
  clean escalated read ("CILENE …") kept the garbage.
- R3: a certidão de casamento whose divorce AVERBAÇÃO one transcription missed
  came out "casado" (the regime phrase alone implies casado).

🔴 SEMANTICS CHANGED 2026-10-13 (owner decision: ship only with an agreement
rule). These regressions were each "fixed" by a heuristic that PICKED A WINNER
between two disagreeing reads (compromised-loses, averbação-wins, wrong-shape-
RG-loses, implausible-name-loses) — whack-a-mole. They now assert the one
rule: a critical field is stored only when two valid reads AGREE; a
disagreement yields NO value, both readings in `leituras_alternativas`, and
the aviso `divergencia_leituras`. Never a winner, whichever order.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.civil_status import find_estado_civil
from noctusai_lib.integrations.documents.legibilidade import AVISO_LEITURA_COMPROMETIDA
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import AVISO_DIVERGENCIA, mesclar
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

BAIXA = ExtractionConfidence.BAIXA
ALTA = ExtractionConfidence.ALTA


class _Ladder:
    def __init__(self, texto) -> None:
        # a list = successive reads (the last repeats); up to 3 are taken
        self.textos = [texto] if isinstance(texto, str) else list(texto)
        self.chamadas = 0

    async def to_text(self, content, mimetype=None, filename=None, *, pular_camada_texto=False):
        i = min(self.chamadas, len(self.textos) - 1)
        self.chamadas += 1
        return (self.textos[i], TextSource.OCR, None)


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

    def test_merge_drops_a_stray_rg_when_both_reads_agree_on_an_rne(self) -> None:
        original = IdentityFields(
            rg="52.179.965-X", rg_confianca=BAIXA, rg_orgao="SSP/SP", rg_orgao_confianca=BAIXA,
            rne="W573678Z", rne_confianca=BAIXA, rne_orgao="DIREX", identidade_tipo="rne",
            source=TextSource.OCR,
        )
        escalada = IdentityFields(rne="W573678Z", rne_confianca=BAIXA, rne_orgao="DIREX", identidade_tipo="rne")
        out = mesclar(original, escalada, escalation_model="m")
        assert out.rne == "W573678Z" and out.rg is None and out.rg_orgao is None
        assert ("rg", "52.179.965-X") in out.leituras_alternativas

    def test_an_rne_only_one_read_found_is_not_stored(self) -> None:
        original = IdentityFields(source=TextSource.OCR)
        escalada = IdentityFields(rne="W573678Z", rne_confianca=BAIXA, rne_orgao="DIREX", identidade_tipo="rne")
        out = mesclar(original, escalada, escalation_model="m")
        assert out.rne is None and out.rg is None
        assert ("rne", "W573678Z") in out.leituras_alternativas
        assert AVISO_DIVERGENCIA in out.aviso.split("+")

    @pytest.mark.asyncio
    async def test_end_to_end_rne_as_printed_no_rg_registro_kept(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CNH_RNE_ESCALADA),
            escalar_releitura=True,
            escalation_ladder=_Ladder(CNH_RNE_ESCALADA),
        ).extract(b"x", mimetype="image/jpeg", tipo_documento="cnh")
        assert out.rg is None
        assert out.rne == "W573678Z"  # as printed — no punctuation invented
        assert out.rne_orgao == "DIREX"
        assert out.registro_cnh == "02954184886"


# ─── R2 ─────────────────────────────────────────────────────────────────────


class TestR2LeituraComprometidaNaoDecide:
    def test_a_compromised_first_read_neither_wins_nor_loses_it_just_does_not_count(self) -> None:
        original = IdentityFields(
            nome="CLELIER BASSO MERY", nome_confianca=BAIXA, aviso=AVISO_LEITURA_COMPROMETIDA,
            source=TextSource.OCR,
        )
        escalada = IdentityFields(nome="CILENE AFRA EXEMPLO NERY", nome_confianca=BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None
        assert {v for c, v in out.leituras_alternativas if c == "nome"} == {
            "CLELIER BASSO MERY", "CILENE AFRA EXEMPLO NERY",
        }

    def test_two_clean_reads_that_disagree_store_no_name(self) -> None:
        original = IdentityFields(nome="ANA EXEMPLO SILVA", nome_confianca=BAIXA, source=TextSource.OCR)
        escalada = IdentityFields(nome="ANA EXEMPLO SILVEIRA", nome_confianca=BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None and out.nome_confianca is ExtractionConfidence.NENHUMA
        assert out.leituras_alternativas == (
            ("nome", "ANA EXEMPLO SILVA"), ("nome", "ANA EXEMPLO SILVEIRA"),
        )
        assert AVISO_DIVERGENCIA in out.aviso.split("+")


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
    def test_no_estado_civil_when_the_reads_disagree_either_order(self, ordem: str) -> None:
        ex = LadderIdentityExtractor()
        sem = ex._ler(CERTIDAO_SEM_AVERBACAO_LIDA, TextSource.OCR, None, None, "certidao_casamento")
        com = ex._ler(CERTIDAO_COM_DIVORCIO, TextSource.OCR, None, None, "certidao_casamento")
        a, b = (sem, com) if ordem == "sem_primeiro" else (com, sem)
        out = mesclar(a, b, escalation_model="m")
        assert out.estado_civil is None  # no 'averbação wins' heuristic
        assert {v for c, v in out.leituras_alternativas if c == "estado_civil"} == {"casado", "divorciado"}
        assert out.regime_bens == "comunhao_universal"  # both reads agree
        assert AVISO_DIVERGENCIA in out.aviso.split("+")

    @pytest.mark.asyncio
    async def test_end_to_end_disagreement_leaves_estado_civil_for_review(self) -> None:
        obito = CERTIDAO_SEM_AVERBACAO_LIDA.replace(
            "(ilegível)", "AVERBACAO: OBITO DO CONJUGE VARAO, REGISTRADO NO LIVRO C-12."
        )
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_SEM_AVERBACAO_LIDA),
            escalar_releitura=True,
            escalation_ladder=_Ladder([CERTIDAO_COM_DIVORCIO, obito]),
        ).extract(b"x", mimetype="application/pdf", tipo_documento="certidao_casamento")
        # three reads, three different estados civis: no two agree, no winner
        assert out.estado_civil is None
        assert ("estado_civil", "casado") in out.leituras_alternativas
        assert ("estado_civil", "divorciado") in out.leituras_alternativas
        assert ("estado_civil", "viuvo") in out.leituras_alternativas
        assert out.regime_bens == "comunhao_universal"
        assert out.genero is None
        assert all(c.genero is None or c.genero_derivado for c in out.conjuges)

    @pytest.mark.asyncio
    async def test_end_to_end_two_reads_that_both_read_the_divorce_agree(self) -> None:
        out = await LadderIdentityExtractor(
            ladder=_Ladder(CERTIDAO_COM_DIVORCIO),
            escalar_releitura=True,
            escalation_ladder=_Ladder(CERTIDAO_COM_DIVORCIO),
        ).extract(b"x", mimetype="application/pdf", tipo_documento="certidao_casamento")
        assert out.estado_civil == "divorciado"
        assert out.regime_bens == "comunhao_universal"


class TestR3cNomeDeCasadaComParticula:
    def test_married_name_caught_with_a_leading_de_still_collapses(self) -> None:
        """Harness, real certidão: spouses 'X FRACASSO' and 'DE X FRACASSO
        PICCHI' (the tail of "passou a usar o nome DE …")."""
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido, _finalizar

        out = _finalizar((
            ConjugeLido(nome="ANA MARIA EXEMPLO", genero="Feminino", genero_confianca="baixa"),
            ConjugeLido(nome="DE ANA MARIA EXEMPLO PICCHI"),
        ))
        assert len(out) == 1
        assert out[0].nome_apos_casamento == "ANA MARIA EXEMPLO PICCHI"
        assert out[0].nome_anterior == "ANA MARIA EXEMPLO"
        assert out[0].genero_derivado is True


#: R4 (measured on a later harness run): a CNH's RG "18568536" read as
#: "1656536" — present, so no core field was missing and no re-read ran.
class TestR4RgTruncadoReleitura:
    def test_truncated_sp_rg_triggers_a_re_read(self) -> None:
        from noctusai_lib.integrations.documents.releitura import deve_escalar

        f = IdentityFields(
            nome="JOAO EXEMPLO", nome_confianca=BAIXA, cpf="412.954.238-98", cpf_confianca=ALTA,
            rg="1656536", rg_confianca=BAIXA, rg_orgao="SSP/SP", source=TextSource.OCR,
        )
        from noctusai_lib.integrations.documents.releitura import rg_anomalo

        assert deve_escalar(f, "cnh") is True
        assert rg_anomalo(f) is True
        assert rg_anomalo(f.__class__(**{**f.__dict__, "rg": "18568536"})) is False

    @pytest.mark.parametrize("ordem", ["truncado_primeiro", "truncado_depois"])
    def test_no_rg_is_stored_when_the_reads_disagree(self, ordem: str) -> None:
        ruim = IdentityFields(rg="1656536", rg_confianca=BAIXA, rg_orgao="SSP/SP",
                              rg_orgao_confianca=BAIXA, source=TextSource.OCR)
        bom = IdentityFields(rg="18568536", rg_confianca=BAIXA, rg_orgao="SSP/SP",
                             rg_orgao_confianca=BAIXA, source=TextSource.OCR)
        a, b = (ruim, bom) if ordem == "truncado_primeiro" else (bom, ruim)
        out = mesclar(a, b, escalation_model="m")
        assert out.rg is None and out.rg_orgao is None
        assert {v for c, v in out.leituras_alternativas if c == "rg"} == {"1656536", "18568536"}


#: R5 (measured on a later harness run): a CNH first read with no CPF/RG/
#: birthdate took a label / footer line as the holder's name, and the
#: "keep the first reading" rule kept it over the re-read's real name.
class TestR5NomeLixoPerde:
    @pytest.mark.parametrize("lixo", ["DATAS DE NASCIMENTO", "SE VOCE PRECISA DESTA INFORMACAO"])
    def test_label_and_footer_lines_are_not_names(self, lixo: str) -> None:
        from noctusai_lib.integrations.documents.name import find_name, looks_like_a_name

        assert looks_like_a_name(lixo) is False
        assert find_name(f"NOME: {lixo}")[0] is None

    def test_implausible_first_name_does_not_win_or_lose_by_rule(self) -> None:
        original = IdentityFields(nome="SOBRENOME LOCAL", nome_confianca=BAIXA, source=TextSource.OCR)
        escalada = IdentityFields(nome="ANA EXEMPLO SILVA", nome_confianca=BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None
        assert {v for c, v in out.leituras_alternativas if c == "nome"} == {
            "SOBRENOME LOCAL", "ANA EXEMPLO SILVA",
        }

    def test_an_incomplete_first_read_does_not_decide_a_disagreement(self) -> None:
        original = IdentityFields(nome="ANA EXEMPLO SOUZA", nome_confianca=BAIXA, source=TextSource.OCR)
        escalada = IdentityFields(
            nome="ANA EXEMPLO SILVA", nome_confianca=BAIXA,
            cpf="412.954.238-98", cpf_confianca=ALTA, rg="18568536", rg_confianca=BAIXA,
        )
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None
        assert {v for c, v in out.leituras_alternativas if c == "nome"} == {
            "ANA EXEMPLO SOUZA", "ANA EXEMPLO SILVA",
        }
        assert out.cpf == "412.954.238-98"  # its check digit verifies: stands alone


#: R3b (measured on a later harness run): the escalated transcription
#: rendered the matrícula appendix's book-type legend in a variant shape the
#: old "LIVRO X (Evento)" guard did not cover, and "Óbito" read as a death.
_DIVORCIO = (
    "CERTIDAO DE CASAMENTO\nREGIME DE BENS: COMUNHAO UNIVERSAL DE BENS\n"
    "AVERBACOES / ANOTACOES A ACRESCER: AVERBACAO DE DIVORCIO: FOI HOMOLOGADO O DIVORCIO DO CASAL.\n"
)


class TestR3bLegendaDeLivroNaoEObito:
    @pytest.mark.parametrize(
        "legenda",
        [
            "4: Livro C (Óbito)",
            "4: Livro C - Óbito",
            "4 - Livro C: Óbito",
            "4: Livro C (Óbito",
            "e (1): Tipo do livro, sendo: 1: Livro A (Nascimento) 4: Livro C Obito",
        ],
    )
    def test_book_type_legend_never_makes_a_widow(self, legenda: str) -> None:
        assert find_estado_civil(_DIVORCIO + legenda)[0] == "divorciado"

    def test_a_real_death_averbacao_is_still_read(self) -> None:
        texto = "CERTIDAO DE CASAMENTO\nAVERBACAO: OBITO DO CONJUGE VARAO, REGISTRADO NO LIVRO C-12."
        assert find_estado_civil(texto)[0] == "viuvo"

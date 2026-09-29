"""`conjuges._ler_narrativa_matrimonio` — both spouses named ONLY in an
old-narrative certidão's opening recital ("... foi feito assento do
matrimônio de A e B ..." / "... foi registrado o casamento (religioso) de A
com B ..."), never repeated anywhere else in the document.

🔴 THE BUGS THIS FILE CLOSES — real, measured (P2 corpus, 2026-09-28/29)

Across the P2 10-deal corpus, `find_conjuges` returned `()` on every
certidão of this family — `test_certidao_casamento_narrativa_antiga.py`'s
own `TestNubentesSemNomeNaoSaoAdivinhados` used to assert exactly that as a
"deliberate, known gap". Five distinct real-document wrinkles this reader
handles, one class each below:

1. **A PDF's own line-wrap falls MID-NAME**, not at a clause boundary — the
   text-layer extraction wraps "... de FULANO DE\\nTAL PAIEIS com CICLANA
   DA SILVA, contraído ..." between "DE" and "TAL". `_limites_candidatos`
   tries every terminator position, nearest first, rather than stopping at
   the first line break.
2. **The couple's names are wrapped in quotes** by one vision pass's own
   OCR ("matrimônio de "FULANO DE TAL" e "CICLANA DE TAL"").
3. **A pre-printed form's dotted blank-lines** ("de FULANO............
   com CICLANA............") are page-layout filler that must be stripped
   before any name candidate is validated, not treated as prose.
4. **The FIRST name genuinely embeds a bare "E"** as a compound-surname
   connector, while the TRUE couple-separator is "COM" further right — the
   real ambiguity `name.nomes_em_par`'s own docstring names; resolved here
   by trying "COM" before "E" when the caller (this reader) supplies both.
5. **Married-name adoption**, stated two different ways on two different
   real certidões — "A/O contra(ente|tante|tente) passou a assinar ..."
   (gender read off the clause's own article) and, on another certidão,
   inside the nubente's own qualification paragraph by anaphora ("... a
   qual passou assinar-se NOVO NOME", gender read off the nearest preceding
   "O/A contra..." marker).

Invented names/dates throughout; each shape mirrors a real masked
transcription from the corpus.
"""
from __future__ import annotations

from datetime import date

from noctusai_lib.integrations.documents.civil_status import find_data_casamento
from noctusai_lib.integrations.documents.conjuges import find_conjuges


class TestLineWrapMidNameIsNotATerminator:
    def test_both_names_are_read_despite_the_wrap(self) -> None:
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "CERTIFICO QUE FOI LAVRADO NO DIA VINTE E TRES DE OUTUBRO DE DOIS\n"
            "MIL E SETE, A ASSENTA DO MATRIMONIO DE FULANO DE\n"
            "TAL PAIEIS COM CICLANA DA SILVA,\n"
            "CONTRAIDO NO DIA VINTE E NOVE DE SETEMBRO DE DOIS MIL E SETE, NA\n"
            "IGREJA SAO FRANCISCO DE ASSIS\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL PAIEIS"
        assert ciclana.nome == "CICLANA DA SILVA"


class TestQuotedNames:
    def test_names_wrapped_in_quotes_are_stripped(self) -> None:
        texto = (
            'CERTIFICO QUE FOI FEITO ASSENTO DO MATRIMONIO DE "FULANO DE TAL '
            'SANTOS" E "CICLANA DE TAL PEREIRA"\n'
            "PARENTE O M. JUIZ DE CASAMENTOS SR. JOSE HONORIO DA SILVA\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL SANTOS"
        assert ciclana.nome == "CICLANA DE TAL PEREIRA"


class TestPrePrintedFormFillerDots:
    def test_dotted_blank_line_filler_does_not_break_the_split(self) -> None:
        texto = (
            "CERTIFICO QUE SOB N. 12345, FL. 100 DO LIVRO N. 5 DO REGISTRO DE "
            "CASAMENTO, VERIFIQUEI CONSTAR QUE AOS VINTE E OITO DE SETEMBRO DE "
            "MIL NOVECENTOS E NOVENTA E CINCO........\n"
            "FOI FEITO O CASAMENTO,\n"
            "DE FULANO DE TAL SANTOS.............................................\n"
            "COM CICLANA DE TAL PEREIRA..........................................\n"
            "CONTRAIDO PERANTE O MM. JUIZ DE CASAMENTOS FULANO HENRIQUE DE MENEZES,\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL SANTOS"
        assert ciclana.nome == "CICLANA DE TAL PEREIRA"


class TestEmbeddedEInTheFirstNameWithARealComSeparator:
    def test_com_is_tried_before_the_embedded_e(self) -> None:
        """The first name is "FULANO DE TAL E SOUZA" — a real compound
        surname carrying its own bare "E" — and the couple is actually
        joined by "COM" further right. Splitting on the FIRST bare "E"
        (inside the name) would wrongly cut it in half."""
        texto = (
            "FOI FEITO O CASAMENTO,\n"
            "DE FULANO DE TAL E SOUZA...\n"
            "COM CICLANA DE TAL PEREIRA...\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL E SOUZA"
        assert ciclana.nome == "CICLANA DE TAL PEREIRA"


class TestMarriedNameAdoptionByArticle:
    def test_no_change_states_o_mesmo_nome_and_keeps_the_recital_name(self) -> None:
        texto = (
            "A ASSENTA DO MATRIMONIO DE FULANO DE TAL COM CICLANA DE TAL, "
            "CONTRAIDO NO DIA VINTE E NOVE DE SETEMBRO DE DOIS MIL E SETE\n"
            "O CONTRAENTE PASSOU A ASSINAR O MESMO NOME.\n"
            "A CONTRAENTE PASSOU A ASSINAR CICLANA DE TAL PAIEIS.\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL"
        assert fulano.nome_anterior is None
        assert ciclana.nome == "CICLANA DE TAL PAIEIS"
        assert ciclana.nome_anterior == "CICLANA DE TAL"

    def test_the_groom_can_be_the_one_who_changes_names(self) -> None:
        texto = (
            "A ASSENTA DO MATRIMONIO DE FULANO DE TAL COM CICLANA DE TAL, "
            "CONTRAIDO NO DIA VINTE E NOVE DE SETEMBRO DE DOIS MIL E SETE\n"
            "O CONTRAENTE PASSOU A ASSINAR FULANO DE TAL PAIEIS.\n"
            "A CONTRAENTE CONTINUA A USAR O MESMO NOME.\n"
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL PAIEIS"
        assert fulano.nome_anterior == "FULANO DE TAL"
        assert ciclana.nome == "CICLANA DE TAL"
        assert ciclana.nome_anterior is None


class TestMarriedNameAdoptionByAnaphora:
    def test_a_qual_passou_assinar_se_is_routed_by_the_nearest_article(self) -> None:
        """A different real certidão states the SAME fact inside the
        nubente's own qualification paragraph, by anaphora ("a qual") rather
        than repeating "A contratante" — gender is read off the NEAREST
        preceding "O/A contra..." marker, not the recital's name order."""
        texto = (
            "CERTIFICO QUE FOI FEITO ASSENTO DO MATRIMONIO DE FULANO DE TAL "
            "E CICLANA DE TAL\n"
            "O CONTRATANTE NASCIDO EM SAO PAULO PROFISSAO COMERCIANTE ESTADO "
            "CIVIL SOLTEIRO\n"
            "A CONTRATANTE NASCIDA EM SAO PAULO PROFISSAO PROFESSORA ESTADO "
            "CIVIL SOLTEIRA FILHA DE ORLANDO DE TAL E DE IVANEZ DE TAL, A "
            'QUAL PASSOU ASSINAR-SE "CICLANA DE TAL PAIEIS":\n'
        )
        fulano, ciclana = find_conjuges(texto)
        assert fulano.nome == "FULANO DE TAL"
        assert fulano.nome_anterior is None
        assert ciclana.nome == "CICLANA DE TAL PAIEIS"
        assert ciclana.nome_anterior == "CICLANA DE TAL"


class TestCasamentoRealizadoHojeDateAlongsideTheRecital:
    """The old-narrative recital's own celebration note — read by
    `find_data_casamento` (see `test_civil_status_datas.py`'s own class for
    this label), exercised here end-to-end on the SAME fixture shape the
    conjuges reader above handles."""

    def test_data_casamento_is_read_from_the_same_document(self) -> None:
        texto = (
            "CERTIFICO QUE FOI FEITO ASSENTO DO MATRIMONIO DE FULANO DE TAL "
            "E CICLANA DE TAL\n"
            "O CONTRATANTE NASCIDO EM SAO PAULO ESTADO CIVIL SOLTEIRO\n"
            "A CONTRATANTE NASCIDA EM SAO PAULO ESTADO CIVIL SOLTEIRA\n"
            'OBSERVACOES: CASAMENTO REALIZADO HOJE (AOS 12 DE SETEMBRO DE 2010) '
            'SOB O REGIME DE "COMUNHAO PARCIAL DE BENS"\n'
        )
        assert len(find_conjuges(texto)) == 2
        valor, conf, _ = find_data_casamento(texto)
        assert (valor, conf) == (date(2010, 9, 12), "alta")

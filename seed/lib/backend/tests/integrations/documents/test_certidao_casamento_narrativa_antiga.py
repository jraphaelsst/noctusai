"""🔴 THE BUGS THIS FILE CLOSES — real, measured (P2 corpus, 2026-09-28)

Across a 10-deal real corpus of certidões de casamento, `find_conjuges`
returned `()` on ~10 of 13 documents, and `find_estado_civil` read a
nubente's PRE-marriage "solteiro" as the document's own verdict on at least
one. Three DISTINCT layouts explain most of it — none of them the
"Primeiro/Segundo Cônjuge" CNJ block `test_certidao_casamento_bloco_
estruturado.py` already covers:

1. **A modern CNJ-adjacent layout that repeats each spouse's name inside
   their own qualification clause, under the `ELE`/`ELA` pronoun label**
   (`ELE: FULANO DE TAL, nascido no dia ..., filho de ...`) — the name and
   the whole clause land on ONE transcribed line, with no institutional
   token to trim it at. `_candidatos`' pronoun branch correctly recognised
   `ELE:`/`ELA:` as a label already (P1/883), but tried the value only
   AS-IS or with `_strip_trailing_citation` — both fail on a 50-word
   qualification clause — so `find_name_conflitos` reported no candidates
   at all, and `find_conjuges` fell through to `()`.

2. **An "inteiro teor" holder list**, headed by a column-header phrase that
   still ends "... DOS CÔNJUGES" like the CNJ header variants already
   recognised, but each row under it prints the SAME shape — a full name
   glued to its own qualification clause on one line — which the existing
   multi-holder collector (`_coleta_titulares_multiplos`) rejected outright
   for the same reason.

3. **An old, pre-CNJ narrative certidão** with no `NOME`/`ELE`/`ELA` label
   anywhere: the couple's names appear ONCE, jointly, in the registration
   sentence ("... foi feito assento do matrimônio de X e Y ..."), and each
   nubente's own qualification paragraph opens with "O contratante" / "A
   contratante" instead of repeating either name — and states THEIR
   pre-marriage `ESTADO CIVIL` ("solteiro"), never the document's own
   verdict.

Shapes (1) and (2) are fixed in `name.py` (`_melhor_leitura_de_nome`, a
third fallback reading alongside `_strip_trailing_citation`'s two, plus one
new `_MULTI_HOLDER_LABELS` entry) and exercised here end-to-end through
`conjuges.find_conjuges` — no change to `conjuges.py` itself was needed,
since both layouts still repeat each spouse's name where the existing
name-conflict segmentation already looks for it. Shape (3)'s `estado_civil`
fix is in `civil_status.py` (`_dentro_de_qualificacao_de_nubente_narrativa`,
the same "nearest opener, no closer since" algorithm the CNJ block guard
already uses, against a different opener).

🔴 SHAPE (3)'S OWN NAME GAP, CLOSED SEPARATELY (P2 corpus, 2026-09-29) —
`TestNubentesSemNomeNaoSaoAdivinhados` below used to assert `find_conjuges`
DECLINES on this layout, reasoning that "X e Y" cannot safely be split (a
Brazilian surname may legitimately contain a bare "E",
`name._PARTICLES`). That reasoning still holds for a BARE "E" alone — what
changed is `conjuges._ler_narrativa_matrimonio`, a new independent reader for
this ONE recital, which now exists precisely because the real P2 corpus
proved the risk was worth taking with `name.nomes_em_par`'s strict
either-side `looks_like_a_name` validation as the backstop: a split that
lands mid-name (a genuine embedded "E") produces a malformed candidate on at
least one side and is rejected, not guessed. See
`test_certidao_casamento_narrativa_de_recital.py` for the full layout family
(quoted names, "casamento religioso de A com B, celebrado/contraído no dia
...", the "A/O contra(ente|tante|tente) passou a assinar" married-name note)
this reader now covers; `TestNubentesSemNomeNaoSaoAdivinhados` here is
updated to assert the NEW behaviour on this file's own fixture. Invented
names/dates throughout.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.civil_status import find_estado_civil
from noctusai_lib.integrations.documents.conjuges import find_conjuges

# ─── Layout 1: `ELE`/`ELA` pronoun label, name glued to its own
# qualification clause on one line ────────────────────────────────────────
CERTIDAO_ELE_ELA_COM_CLAUSULA = """
CERTIDAO DE CASAMENTO
NOME: RICARDO AUGUSTO FERREIRA LIMA
NOME: BEATRIZ CARDOSO NUNES
MATRICULA: 123456 01 55 2021 1 00045 001 1234567-89
ELE: RICARDO AUGUSTO FERREIRA LIMA, nascido no dia dez de marco de mil novecentos e noventa (10/03/1990), naturalizado brasileiro, filho de JOSE FERREIRA LIMA e de ANA FERREIRA LIMA
ELA: BEATRIZ CARDOSO NUNES, nascida no dia vinte de julho de mil novecentos e noventa e dois (20/07/1992), naturalizada brasileira, filha de PEDRO CARDOSO NUNES e de LUCIA CARDOSO NUNES
DATA DE REGISTRO DO CASAMENTO POR EXTENSO: QUATORZE DE JUNHO DE DOIS MIL E VINTE E UM
REGIME DE BENS DO CASAMENTO: COMUNHAO PARCIAL DE BENS, DE ACORDO COM A LEI VIGENTE
NOME QUE CADA UM DOS CONJUGES PASSOU A UTILIZAR (QUANDO HOUVER ALTERACAO): ELE: PASSOU A USAR O NOME DE RICARDO AUGUSTO FERREIRA LIMA. ELA: CONTINUOU A USAR O MESMO NOME.
"""


class TestPronomeComClausulaNaMesmaLinha:
    def test_exactly_two_holders_are_read(self) -> None:
        assert len(find_conjuges(CERTIDAO_ELE_ELA_COM_CLAUSULA)) == 2

    def test_each_spouse_is_named_correctly_and_in_document_order(self) -> None:
        ricardo, beatriz = find_conjuges(CERTIDAO_ELE_ELA_COM_CLAUSULA)
        assert ricardo.nome == "RICARDO AUGUSTO FERREIRA LIMA"
        assert beatriz.nome == "BEATRIZ CARDOSO NUNES"


# ─── Layout 2: "inteiro teor" holder list under a "... DOS CÔNJUGES"
# column header, one full qualification clause per line ───────────────────
CERTIDAO_INTEIRO_TEOR_LISTA = """
CERTIDAO DE CASAMENTO
FLAVIO HENRIQUE MOREIRA COSTA
GABRIELA ALMEIDA ROCHA
Matricula: 123456 01 55 1987 1 00098 004 0004567-12
Nomes completos de solteiro, datas e locais de nascimento, nacionalidade e filiacoes dos conjuges:
FLAVIO HENRIQUE MOREIRA COSTA, nascido aos dez de agosto de mil novecentos e cinquenta e nove, natural desta Capital, Bela Vista, filho de ANTONIO MOREIRA COSTA e de IRACEMA MOREIRA COSTA
GABRIELA ALMEIDA ROCHA, nascida aos vinte e cinco de dezembro de mil novecentos e sessenta, natural de Osvaldo Cruz-SP, filha de BENEDITO ALMEIDA ROCHA e de TEREZA ALMEIDA ROCHA
Data do registro do casamento (por extenso): sete de outubro de mil novecentos e oitenta e sete
Regime de bens do casamento: Comunhao Parcial de Bens
"""


class TestInteiroTeorListaDeTitulares:
    def test_exactly_two_holders_are_read(self) -> None:
        assert len(find_conjuges(CERTIDAO_INTEIRO_TEOR_LISTA)) == 2

    def test_each_spouse_is_named_correctly_and_in_document_order(self) -> None:
        flavio, gabriela = find_conjuges(CERTIDAO_INTEIRO_TEOR_LISTA)
        assert flavio.nome == "FLAVIO HENRIQUE MOREIRA COSTA"
        assert gabriela.nome == "GABRIELA ALMEIDA ROCHA"


# ─── Layout 3: old narrative, names given once jointly, each nubente's own
# paragraph opened by "O contratante" / "A contratante" — no name repeated ──
CERTIDAO_NARRATIVA_ANTIGA = """
CERTIDAO DE CASAMENTO
Certifico que a fls. 45 do livro B/12 de registro de casamentos foi feito assento do matrimonio de EDUARDO SANTOS PEREIRA e MARCIA OLIVEIRA COSTA
O contratante nascido em esta Capital, Subdistrito Capela do Socorro aos dez de agosto de mil novecentos e sessenta profissao comerciante estado civil solteiro
A contratante nascida em esta Capital, Subdistrito Cerqueira Cesar aos vinte de setembro de mil novecentos e sessenta e dois profissao professora estado civil solteira
Foram apresentados os documentos a que se refere o artigo 180 numeros I, II e IV do Codigo Civil
Observacoes: Casamento realizado hoje aos dez de outubro de mil novecentos e oitenta e cinco sob o regime de "COMUNHAO PARCIAL DE BENS"
"""


class TestEstadoCivilNaoLeAPreMariageDoNubente:
    def test_the_documents_own_verdict_is_casado_not_the_nubentes_pre_marriage_status(
        self,
    ) -> None:
        """Both nubentes' own "estado civil solteiro"/"solteira" clauses
        state their status BEFORE this marriage — the document's own verdict
        is "casado", inferred from the printed regime de bens, exactly like
        the CNJ block layout's own equivalent bug (P1/883)."""
        valor, confianca, _ = find_estado_civil(CERTIDAO_NARRATIVA_ANTIGA)
        assert (valor, confianca) == ("casado", "alta")


class TestNubentesSemNomeNaoSaoAdivinhados:
    """🔴 THE GAP THIS USED TO DOCUMENT IS NOW CLOSED (P2 corpus, 2026-09-29).

    This layout never repeats either spouse's name inside their own
    paragraph, so the ONLY place both names appear is the single sentence
    "... de EDUARDO SANTOS PEREIRA e MARCIA OLIVEIRA COSTA".
    `conjuges._ler_narrativa_matrimonio` now reads this recital directly and
    splits it via `name.nomes_em_par` — the class name survives (the risk
    this docstring used to describe is real and still guarded, just no
    longer by DECLINING outright): a Brazilian surname may legitimately
    contain a bare "E" as a compound-name particle (`name._PARTICLES`), so
    every candidate either side of the split is still independently
    validated by `looks_like_a_name` — a malformed half is what makes a
    wrong split self-rejecting, not a rule about which "e" is the
    separator. See `test_certidao_casamento_narrativa_de_recital.py` for the
    layout family (quoted names, an embedded "E" alongside a real "COM"
    separator, married-name adoption) this same reader also covers.
    """

    def test_exactly_two_holders_are_now_read(self) -> None:
        assert len(find_conjuges(CERTIDAO_NARRATIVA_ANTIGA)) == 2

    def test_each_spouse_is_named_correctly_and_in_document_order(self) -> None:
        eduardo, marcia = find_conjuges(CERTIDAO_NARRATIVA_ANTIGA)
        assert eduardo.nome == "EDUARDO SANTOS PEREIRA"
        assert marcia.nome == "MARCIA OLIVEIRA COSTA"


def test_ocr_slip_contratente_still_guards_pre_marriage_status() -> None:
    """P2 corpus (deal 895): the prod transcription spelled the opener
    "O contratente" — the pre-marriage "estado civil solteiro" must still be
    excluded from the document's verdict."""
    from noctusai_lib.integrations.documents.civil_status import find_estado_civil

    texto = (
        "CERTIDÃO DE CASAMENTO\n"
        "Certifico que foi feito assento do matrimônio de FULANO DE TAL e CICLANA DE TAL\n"
        "O contratente nascido em esta Capital aos 12 de agosto de 1980 profissão comerciante estado civil solteiro\n"
        "A contratante nascida em esta Capital aos 03 de junho de 1983 profissão professora estado civil solteira\n"
        'Observações: Casamento realizado hoje sob o regime de "COMUNHÃO PARCIAL DE BENS"\n'
    )
    assert find_estado_civil(texto)[0] == "casado"

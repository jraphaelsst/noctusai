"""🔴 THE BUG THIS FILE CLOSES — real, measured (live prod test, 2026-09-30)

A national CNJ-model certidão de casamento, delivered as a digital PDF WITH
its own text layer (not a scan), lays each field out differently from every
other certidão variant this package already reads:

- The "1º Cônjuge:" / "2º Cônjuge:" block opener carries no value of its
  own — its "Data de nascimento" and "Nome no momento da habilitação"
  sub-labels sit BETWEEN the opener and that spouse's own pre-marriage
  name, each alone on its own row. `conjuges._extrai_valor_apos`'s
  same-line/next-line read (built for the vision-model "Primeiro Cônjuge:
  JOAO..." layout) finds nothing there, and unguarded that failed the
  WHOLE structured-block reader — both spouses lost, not just this field.
- "Nome que passou a utilizar" (the post-marriage/current name) carries no
  ordinal at all, unlike the vision-model's own "Nome que o primeiro
  cônjuge passou a utilizar" — only its POSITION (inside one spouse's own
  block) says whose name it is.
- The property regime is stated with its modifier BEFORE the noun —
  "ABSOLUTA E COMPLETA SEPARAÇÃO DE BENS" — the opposite order every
  existing `_REGIME_BENS_PADROES` entry expects, so `find_regime_bens`
  returned nothing at all; that starved `find_estado_civil`'s own
  bare-regime inference too, in a document with no other estado-civil
  label of its own (the ONLY per-document verdict, since the two
  "Estado Civil: SOLTEIRO"/"SOLTEIRA" rows are each nubente's OWN
  pre-marriage status, already excluded by the existing
  "Primeiro/Segundo Cônjuge" per-spouse guard — that guard is confirmed
  STILL correct on this layout by this file, not re-implemented).

Before this fix, the live extraction reported `kind` unclassified by
content, `estado_civil`/`regime_bens`/`conjuges` all empty, and a single
flat, ambiguous `cpf` — which social-wiring then wrote onto the card's
titular even though it was the OTHER spouse's number (see
`test_identidade_extracao_two_person_certidao_cpf.py` in social-wiring
for the write-side half of this incident).

Invented names/CPFs below (the two CPFs are real, check-digit-valid, so the
Matrícula-decoy and adjacency logic are genuinely exercised — never real
people's data); the shape mirrors the real certidão's text layer.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.civil_status import find_estado_civil, find_regime_bens
from noctusai_lib.integrations.documents.conjuges import find_conjuges
from noctusai_lib.integrations.documents.misfile import classificar_tipo_provavel

#: `111.444.777-35` and `529.982.247-25` are both real, check-digit-valid
#: CPFs — deliberately, so the Matrícula-shaped decoy below must be excluded
#: on grounds of its LABEL, not because it happens to fail the checksum too.
CERTIDAO_CNJ_TEXTLAYER = """CERTIDÃO DE CASAMENTO
NOME ATUAL DOS CÔNJUGES:
NÚMERO DO CPF
RICARDO AUGUSTO TAVARES
111.444.777-35
FLAVIA REGINA TAVARES
529.982.247-25
Matrícula
123456 01 55 2024 2 00123 045 0012345 67
1º Cônjuge:
Data de nascimento
Nome no momento da habilitação
RICARDO AUGUSTO TAVARES
Dia
12
Mês
03
Ano
1990
Nacionalidade
BRASILEIRA
Estado Civil
SOLTEIRO
Município de nascimento
SÃO PAULO
UF
SP
Genitor(es)
JOSE TAVARES; MARIA TAVARES
Nome que passou a utilizar
RICARDO AUGUSTO TAVARES
2º Cônjuge:
Data de nascimento
Nome no momento da habilitação
FLAVIA REGINA MOURA
Dia / 25 / Mês / 07 / Ano / 1992
Nacionalidade
BRASILEIRA
Estado Civil
SOLTEIRA
Município de nascimento / SÃO PAULO / UF / SP
Genitor(es)
CARLOS MOURA; ANA MOURA
Nome que passou a utilizar
FLAVIA REGINA TAVARES
Data da celebração do casamento ou, se for o caso de conversão da união estável, data do registro
vinte e cinco de outubro de dois mil e vinte e quatro
Dia / 25 / Mês / 10 / Ano / 2024
Regime de bens
ABSOLUTA E COMPLETA SEPARAÇÃO DE BENS, conforme Escritura Pública de Pacto Antenupcial lavrada no
5º Tabelião de Notas, desta Comarca, aos 01/09/2024 (livro 123, páginas 45/46)
Data de registro do casamento
vinte e cinco de outubro de dois mil e vinte e quatro
Dia / 25 / Mês / 10 / Ano / 2024
Anotações/Averbações
Assento lavrado no livro B-100, fls. 50, termo nº 123456789. NADA MAIS ME CUMPRIA CERTIFICAR.
Anotações voluntárias de cadastro
NÃO CONSTA
"""


class TestContentClassification:
    def test_classified_as_certidao_de_casamento_by_content(self) -> None:
        assert classificar_tipo_provavel(CERTIDAO_CNJ_TEXTLAYER) == "certidao_casamento"


class TestEstadoCivilAndRegimeOnCnjTextLayer:
    def test_regime_reads_the_modifier_first_word_order(self) -> None:
        assert find_regime_bens(CERTIDAO_CNJ_TEXTLAYER) == (
            "separacao_total", "alta", "ABSOLUTA E COMPLETA SEPARACAO DE BENS",
        )

    def test_the_documents_own_verdict_is_casado_not_either_nubentes_pre_marriage_status(
        self,
    ) -> None:
        """Both "Estado Civil: SOLTEIRO"/"SOLTEIRA" rows are each nubente's
        OWN status before this marriage, inside their own "1º/2º Cônjuge:"
        block — never the document's own verdict, which is inferred from
        the (now-recognised) regime de bens phrase, same as any other
        certidão with no couple-level estado-civil label of its own."""
        assert find_estado_civil(CERTIDAO_CNJ_TEXTLAYER) == (
            "casado", "alta", "ABSOLUTA E COMPLETA SEPARACAO DE BENS",
        )


class TestFindConjugesOnCnjTextLayer:
    def test_exactly_two_holders_are_read(self) -> None:
        assert len(find_conjuges(CERTIDAO_CNJ_TEXTLAYER)) == 2

    def test_each_spouse_gets_their_own_cpf_from_the_nome_atual_table(self) -> None:
        ricardo, flavia = find_conjuges(CERTIDAO_CNJ_TEXTLAYER)
        assert ricardo.cpf == "111.444.777-35"
        assert flavia.cpf == "529.982.247-25"
        assert ricardo.cpf != flavia.cpf

    def test_the_current_post_marriage_name_is_preferred_and_the_habilitacao_name_survives(
        self,
    ) -> None:
        ricardo, flavia = find_conjuges(CERTIDAO_CNJ_TEXTLAYER)
        # Ricardo's habilitação and current names coincide — no secondary.
        assert ricardo.nome == "RICARDO AUGUSTO TAVARES"
        assert ricardo.nome_anterior is None
        # Flávia's CURRENT (post-marriage) name is the primary `nome`; her
        # own pre-marriage (habilitação) name rides as `nome_anterior`.
        assert flavia.nome == "FLAVIA REGINA TAVARES"
        assert flavia.nome_anterior == "FLAVIA REGINA MOURA"

    def test_nacionalidade_is_read_per_spouse(self) -> None:
        ricardo, flavia = find_conjuges(CERTIDAO_CNJ_TEXTLAYER)
        assert ricardo.nacionalidade and flavia.nacionalidade

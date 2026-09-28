"""🔴 THE BUG THIS FILE CLOSES — real, measured (P1/883, 2026-09-28)

A national CNJ-standardised certidão de casamento layout (Provimento CNJ
63/2017) prints neither a `NOMES` table nor a narrative "NOME, nascido ..."
qualification clause — instead each nubente owns a literal "Primeiro
Cônjuge:" / "Segundo Cônjuge:" block, and a separate "Nome atual dos
cônjuges" header lists both spouses' CURRENT (post-marriage) names with an
interleaved "Número do CPF" row.

Before this fix: `find_estado_civil` picked up the SECOND spouse's own
"Estado Civil: Solteira" (her status BEFORE this marriage, printed inside
her own block) as the document's verdict; `find_conjuges` returned `()`
(neither the block labels nor the header were recognised as naming two
co-equal holders); and the one real CPF printed got attributed
ambiguously, opening a spurious conflict — while a matrícula number,
CPF-shaped by OCR, sat right next to it as a decoy.

Invented names/numbers below; the shape mirrors the real certidão.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.civil_status import find_estado_civil
from noctusai_lib.integrations.documents.conjuges import _ler_bloco_estruturado, find_conjuges

#: `123.456.789-09` and `987.654.321-00` are both real, check-digit-valid
#: CPFs (deliberately — the matrícula decoy must be excluded on grounds of
#: its LABEL, not because it happens to fail the checksum too).
CERTIDAO_BLOCO_ESTRUTURADO = """
CERTIDAO DE CASAMENTO
Nome atual dos conjuges
JOAO DE SOUZA LIMA
Numero do CPF
123.456.789-09
MARIA CLARA ALVES DE SOUZA
Matricula
987.654.321-00
123456 01 55 2019 2 00123 045 0012345 67
Primeiro Conjuge: JOAO DE SOUZA LIMA
Data de nascimento: 04 / 10 / 1996
Nacionalidade: Brasileiro
Genitores: PEDRO DE SOUZA LIMA E ANA PAULA LIMA
Nome que o primeiro conjuge passou a utilizar: JOAO DE SOUZA LIMA
Segundo Conjuge: MARIA CLARA ALVES
Data de nascimento: 20 / 04 / 1998
Nacionalidade: Brasileira
Estado Civil: Solteira
Genitores: CARLOS ALVES E REGINA ALVES
Nome que o segundo conjuge passou a utilizar: MARIA CLARA ALVES DE SOUZA
Data da celebracao do casamento: Dia 15 / Mes 08 / Ano 2020
Regime de bens: Comunhao Parcial de Bens
Anotacoes / Averbacoes: Lavrado no livro B-12. Nada nela me cumpria certificar.
"""


class TestFindConjugesBlocoEstruturado:
    def test_exactly_two_holders_are_read(self) -> None:
        assert len(find_conjuges(CERTIDAO_BLOCO_ESTRUTURADO)) == 2

    def test_each_spouses_own_nome_atual_is_preferred_over_the_block_name(self) -> None:
        joao, maria = find_conjuges(CERTIDAO_BLOCO_ESTRUTURADO)
        # João's block name and his "nome atual" coincide — no secondary.
        assert joao.nome == "JOAO DE SOUZA LIMA"
        assert joao.nome_anterior is None
        # Maria's CURRENT (post-marriage) name is the primary `nome`; her
        # block's own (maiden) name rides as `nome_anterior`, never lost.
        assert maria.nome == "MARIA CLARA ALVES DE SOUZA"
        assert maria.nome_anterior == "MARIA CLARA ALVES"

    def test_birthdate_and_nationality_are_read_per_spouse(self) -> None:
        joao, maria = find_conjuges(CERTIDAO_BLOCO_ESTRUTURADO)
        assert joao.data_nascimento.isoformat() == "1996-10-04"
        assert maria.data_nascimento.isoformat() == "1998-04-20"
        assert joao.nacionalidade and maria.nacionalidade

    def test_cpf_is_attributed_to_the_right_spouse_and_the_matricula_is_ignored(self) -> None:
        joao, maria = find_conjuges(CERTIDAO_BLOCO_ESTRUTURADO)
        assert joao.cpf == "123.456.789-09"
        # The matrícula is CPF-shaped and check-digit-valid on purpose — it
        # must never be read as Maria's CPF just because it sits closer to
        # her name than João's real one does.
        assert maria.cpf is None

    def test_a_single_conjuge_block_alone_is_not_two_holders(self) -> None:
        """Isolates the structured-block reader itself: with no "Nome atual
        dos cônjuges" header to fall back on and only ONE block opener, it
        must decline rather than guess — never silently drop to a
        single-holder read."""
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "Primeiro Conjuge: JOAO DE SOUZA LIMA\n"
            "Data de nascimento: 04 / 10 / 1996\n"
            "Nacionalidade: Brasileiro\n"
            "Regime de bens: Comunhao Parcial de Bens\n"
        )
        assert _ler_bloco_estruturado(texto) == ()
        assert find_conjuges(texto) == ()


class TestEstadoCivilOnBlocoEstruturado:
    def test_the_documents_own_verdict_is_casado_not_the_nubentes_pre_marriage_status(
        self,
    ) -> None:
        """The second nubente's own "Estado Civil: Solteira" states HER
        status before this marriage — the document's own verdict is
        "casado", inferred from the printed regime de bens, same as any
        other certidão with no explicit couple-level label."""
        assert find_estado_civil(CERTIDAO_BLOCO_ESTRUTURADO) == (
            "casado", "alta", "COMUNHAO PARCIAL DE BENS",
        )

    def test_an_averbacao_de_divorcio_still_overrides_the_registro(self) -> None:
        texto = CERTIDAO_BLOCO_ESTRUTURADO.replace(
            "Anotacoes / Averbacoes: Lavrado no livro B-12. Nada nela me cumpria certificar.",
            "Averbacoes: Averbado o divorcio do casal, conforme sentenca judicial transitada em julgado.",
        )
        valor, confianca, _ = find_estado_civil(texto)
        assert (valor, confianca) == ("divorciado", "alta")

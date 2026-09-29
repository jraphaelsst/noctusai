"""`conjuges._ler_ancorada` — the ANCHORED fallback `find_conjuges` tries
only when NONE of the label-driven readers (`_ler_bloco_estruturado`,
`_ler_narrativa_matrimonio`, `_ler_rotulada`) recognise the document.

🔴 THE PROBLEM THIS CLOSES — measured, not assumed (P2 corpus, 2026-09-29)

On the SAME 13 certidões de casamento, two fresh vision-model
transcription runs resolved both spouses' names correctly on 7/13 and
5/13 — individual files flip between `conj=2` and `conj=0` run to run.
The label-driven readers all depend on a layout SIGNAL (a block opener, a
narrative connector, a `NOMES` label) surviving that run's own
transcription; the two spouses' actual NAMES usually survive even when
the signal that would let a label-driven reader recognise the layout does
not. `TitularEsperado.nome`/`conjuge_nome` — a name the PLATFORM already
knows, never a fresh guess — gives `find_conjuges` a third way in: confirm
each hinted name directly against the text instead of depending on the
label.

Every fixture below is fully invented.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.conjuges import (
    ConjugeLido,
    _ancora_nome,
    find_conjuges,
)

#: A layout `_ler_rotulada` DOES recognise on its own (an explicit `NOMES`
#: label followed by a bare comma-qualification clause per spouse) — used
#: to prove the anchored fallback never RUNS, let alone changes the
#: answer, when the label-driven path already succeeds.
CERTIDAO_ROTULADA = """
CERTIDAO DE CASAMENTO
NOMES
JOAO PEREIRA LIMA
CARLA MENDES ROCHA
JOAO PEREIRA LIMA, nascido no dia dez de janeiro de mil novecentos e oitenta (10/01/1980), de nacionalidade brasileira, profissao engenheiro, filho de PEDRO LIMA e de ANA LIMA.
CARLA MENDES ROCHA, nascida no dia vinte de fevereiro de mil novecentos e oitenta e dois (20/02/1982), de nacionalidade brasileira, profissao medica, filha de MARCOS ROCHA e de LUCIA ROCHA.
Data da celebracao do casamento: 05/06/2010
Regime de bens: comunhao parcial de bens
"""

#: NO recognisable label-driven layout at all — no `NOME`/`NOMES` label
#: (name.py's own "no unlabelled fallback" rule means `find_name_conflitos`
#: reports nothing here), no "Primeiro/Segundo Cônjuge" block opener, no
#: "casamento de X com Y" narrative recital. Mirrors the measured failure
#: mode: a vision transcription that garbled every layout signal while
#: leaving the qualification prose itself intact.
TEXTO_SEM_ROTULO = (
    "REGISTRO CIVIL DAS PESSOAS NATURAIS\n"
    "CERTIDAO\n"
    "Consta que compareceram perante o oficial as partes abaixo qualificadas, "
    "tendo sido celebrado o casamento na forma da lei.\n"
    "FULANO DE TAL SILVA, nascido no dia dez de maio de mil novecentos e noventa "
    "(10/05/1990), de nacionalidade brasileira, profissao engenheiro, "
    "filho de PEDRO DE TAL SILVA e de MARIA DE TAL SILVA.\n"
    "CICLANA DA COSTA, nascida no dia vinte de junho de mil novecentos e noventa e "
    "dois (20/06/1992), de nacionalidade brasileira, profissao advogada, "
    "filha de JOSE DA COSTA e de ANA DA COSTA.\n"
    "Data da celebracao do casamento: 15/03/2015\n"
    "Regime de bens: comunhao parcial de bens\n"
)

FULANO_ESPERADO = "FULANO DE TAL SILVA"
CICLANA_ESPERADA = "CICLANA DA COSTA"


class TestLabelDrivenReadIsUnaffectedByAHint:
    """No regression: a document the label-driven path already resolves
    must return the SAME answer whether or not the caller also supplies
    `esperados` — the anchored fallback is tried LAST, never instead of."""

    def test_same_result_with_or_without_the_hint(self) -> None:
        sem_hint = find_conjuges(CERTIDAO_ROTULADA)
        com_hint = find_conjuges(
            CERTIDAO_ROTULADA,
            esperados=("JOAO PEREIRA LIMA", "CARLA MENDES ROCHA"),
        )
        assert sem_hint == com_hint

    def test_a_hint_naming_someone_not_on_the_document_changes_nothing(self) -> None:
        """Even a hint that would anchor nowhere must not perturb a
        label-driven read that already succeeded."""
        resultado = find_conjuges(
            CERTIDAO_ROTULADA,
            esperados=("PESSOA TOTALMENTE DIFERENTE", "OUTRA PESSOA QUALQUER"),
        )
        assert resultado == find_conjuges(CERTIDAO_ROTULADA)


class TestNoHintIsTheHistoricalNoOpBehaviour:
    def test_no_recognisable_layout_and_no_hint_still_returns_empty(self) -> None:
        assert find_conjuges(TEXTO_SEM_ROTULO) == ()


class TestAnchoredFallbackConfirmsBothNames(object):
    def test_both_hinted_spouses_are_found_in_document_order(self) -> None:
        fulano, ciclana = find_conjuges(
            TEXTO_SEM_ROTULO, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert fulano.nome == FULANO_ESPERADO
        assert ciclana.nome == CICLANA_ESPERADA

    def test_each_spouses_own_facts_are_read_from_their_own_segment(self) -> None:
        fulano, ciclana = find_conjuges(
            TEXTO_SEM_ROTULO, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert fulano.data_nascimento.isoformat() == "1990-05-10"
        assert ciclana.data_nascimento.isoformat() == "1992-06-20"
        assert fulano.nacionalidade and ciclana.nacionalidade
        assert fulano.profissao == "engenheiro"
        assert ciclana.profissao == "advogada"
        # Positional attribution around a hinted name is an inference,
        # never a label-anchored read — every per-person fact is capped at
        # `media`, exactly like `_dados_tabulares`'s own posture.
        assert fulano.nacionalidade_confianca == "media"
        assert fulano.profissao_confianca == "media"

    def test_no_confusion_with_the_other_spouses_facts(self) -> None:
        """The bug this segmenting exists to prevent: without a bound, a
        wider window sees TWO labelled birthdates and `find_birthdate`
        collapses a genuine disagreement to absence (see its own
        docstring) — each spouse must get their OWN date, not neither."""
        fulano, ciclana = find_conjuges(
            TEXTO_SEM_ROTULO, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert fulano.data_nascimento != ciclana.data_nascimento
        assert fulano.data_nascimento is not None
        assert ciclana.data_nascimento is not None


class TestOnlyOneExpectedNameAnchors:
    """`esperados` names two people, but only ONE of them is actually
    printed on this document (a stale/garbled `conjuge_nome` hint, or a
    genuine single-holder document). The fallback must return what it
    found and NEVER fabricate the missing second spouse."""

    def test_the_found_spouse_is_returned_alone(self) -> None:
        resultado = find_conjuges(
            TEXTO_SEM_ROTULO,
            esperados=(FULANO_ESPERADO, "PESSOA QUE NAO ESTA NO DOCUMENTO"),
        )
        assert len(resultado) == 1
        assert resultado[0].nome == FULANO_ESPERADO

    def test_the_lone_spouses_own_facts_still_read_correctly(self) -> None:
        """Regression guard for the segment-bounding bug this fallback
        must avoid: with no second anchor to stop at, the read must still
        land on THIS spouse's own qualification clause, not run through
        an unaccounted-for second person's clause and collide."""
        (fulano,) = find_conjuges(
            TEXTO_SEM_ROTULO,
            esperados=(FULANO_ESPERADO, "PESSOA QUE NAO ESTA NO DOCUMENTO"),
        )
        assert fulano.data_nascimento.isoformat() == "1990-05-10"
        assert fulano.profissao == "engenheiro"


class TestHintedNameAbsentFromTheDocumentIsNeverFabricated:
    def test_neither_hint_anchors_anywhere_yields_nothing(self) -> None:
        assert (
            find_conjuges(
                "NADA A VER COM CASAMENTO AQUI, NENHUM NOME CONHECIDO.",
                esperados=("ALGUEM QUALQUER SILVA", "OUTRO ALGUEM COSTA"),
            )
            == ()
        )

    def test_a_single_absent_hint_alongside_a_present_one_only_returns_the_present_one(
        self,
    ) -> None:
        resultado = find_conjuges(
            TEXTO_SEM_ROTULO,
            esperados=("ALGUEM QUE NAO EXISTE NO TEXTO", CICLANA_ESPERADA),
        )
        assert len(resultado) == 1
        assert resultado[0].nome == CICLANA_ESPERADA


class TestNameSplitAcrossALineBreak:
    """A scan's line-wrap lands mid-name — the anchor must still confirm
    it, same `\\s+`-between-every-word tolerance `_padrao_nome` already
    gives the label-driven readers."""

    def test_anchors_despite_the_wrap(self) -> None:
        texto_com_quebra = TEXTO_SEM_ROTULO.replace(
            "FULANO DE TAL SILVA,", "FULANO DE TAL\nSILVA,"
        )
        fulano, ciclana = find_conjuges(
            texto_com_quebra, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert fulano.nome == FULANO_ESPERADO
        assert ciclana.nome == CICLANA_ESPERADA

    def test_ancora_nome_itself_tolerates_the_wrap(self) -> None:
        """Isolates `_ancora_nome` directly, without the surrounding
        segment-reading machinery."""
        from noctusai_lib.integrations.documents.matricula_atos import (
            normalized_with_offsets,
        )

        norm, _origem = normalized_with_offsets("FULANO DE TAL\nSILVA, nascido...")
        achado = _ancora_nome(norm, FULANO_ESPERADO)
        assert achado is not None
        _inicio, _fim, valor = achado
        assert valor == FULANO_ESPERADO


class TestMarriedNameAdoption:
    """The certidão prints the MAIDEN name in the qualification clause and
    states the MARRIED one separately ("passou a assinar" / "passou a
    utilizar") — the CURRENT (post-marriage) name is the primary `nome`,
    the maiden form rides as `nome_anterior`, never the other way round
    (same convention `_ler_bloco_estruturado`/`_ler_narrativa_matrimonio`
    already use for their own adoption clauses)."""

    def test_the_married_name_wins_and_the_maiden_name_survives_as_nome_anterior(
        self,
    ) -> None:
        texto = TEXTO_SEM_ROTULO.replace(
            "filha de JOSE DA COSTA e de ANA DA COSTA.\n",
            "filha de JOSE DA COSTA e de ANA DA COSTA. "
            "A contratante passou a assinar CICLANA DA COSTA SILVA.\n",
        )
        fulano, ciclana = find_conjuges(
            texto, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert fulano.nome == FULANO_ESPERADO
        assert fulano.nome_anterior is None
        assert ciclana.nome == "CICLANA DA COSTA SILVA"
        assert ciclana.nome_anterior == CICLANA_ESPERADA

    def test_utilizar_is_recognised_alongside_assinar(self) -> None:
        """The CNJ structured-block family's own clause verb is
        "utilizar", not "assinar"/"usar" — the fallback must recognise
        either, since it does not know in advance which family's own
        wording survived this run's transcription."""
        texto = TEXTO_SEM_ROTULO.replace(
            "filha de JOSE DA COSTA e de ANA DA COSTA.\n",
            "filha de JOSE DA COSTA e de ANA DA COSTA. "
            "Nome que passou a utilizar: CICLANA DA COSTA SILVA.\n",
        )
        _fulano, ciclana = find_conjuges(
            texto, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert ciclana.nome == "CICLANA DA COSTA SILVA"
        assert ciclana.nome_anterior == CICLANA_ESPERADA


class TestConjugeLidoShapeIsUnchanged:
    """The anchored path returns the SAME `ConjugeLido` shape the other
    three readers do — no new fields, no new confidence vocabulary."""

    def test_result_type(self) -> None:
        fulano, _ciclana = find_conjuges(
            TEXTO_SEM_ROTULO, esperados=(FULANO_ESPERADO, CICLANA_ESPERADA)
        )
        assert isinstance(fulano, ConjugeLido)
        assert fulano.titular is False
